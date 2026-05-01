"""Handler for torrent-based file transfers.

Implements the torrent-based transfer states for transferring files
between Deluge instances using BitTorrent protocol.

States handled:
- TORRENT_CREATE_QUEUE: Waiting for creation slot (serialized)
- TORRENT_CREATING: Create transfer torrent on source
- TORRENT_TARGET_ADDING: Add transfer torrent to target via magnet
- TORRENT_DOWNLOADING: Monitor download progress on target
- TORRENT_SEEDING: Verify seeding, add original torrent to target
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.transfer_connection import TransferConnection
from transferarr.utils import (
    generate_transfer_id,
    build_transfer_torrent_name,
)

if TYPE_CHECKING:
    from transferarr.services.tracker import BitTorrentTracker

logger = logging.getLogger("transferarr")

# Keys accepted by SFTPClient.__init__()
_SFTP_CLIENT_KEYS = frozenset({
    'host', 'port', 'username', 'password', 'private_key',
    'ssh_config_host', 'ssh_config_file',
})


def _sftp_client_params(config: dict) -> dict:
    """Filter an SFTP config dict to only the keys SFTPClient accepts.
    
    Extra keys like ``state_dir`` are stripped so they don't cause
    a TypeError when passed as **kwargs to :class:`SFTPClient`.
    """
    return {k: v for k, v in config.items() if k in _SFTP_CLIENT_KEYS}


def is_transfer_torrent_name(name: str) -> bool:
    """Check if a torrent name is a transfer torrent.
    
    Args:
        name: Torrent name to check
        
    Returns:
        True if name starts with "[TR-" prefix
    """
    return name.startswith("[TR-")


def get_transfer_id_from_name(name: str) -> Optional[str]:
    """Extract transfer ID from a transfer torrent name.
    
    Args:
        name: Transfer torrent name
        
    Returns:
        6-character transfer ID or None if not a transfer torrent
    """
    if not is_transfer_torrent_name(name):
        return None
    try:
        # Format: "[TR-xxxxxx] Original Name"
        return name[4:10]  # Skip "[TR-" and get 6 chars
    except (IndexError, ValueError):
        return None


class TorrentTransferHandler:
    """Handles torrent-based transfer state machine.
    
    Manages the creation of transfer torrents on source, adding to target
    via magnet link, and tracking transfer progress.
    """
    
    MAX_RETRIES = 3
    STALL_THRESHOLD_SECONDS = 300  # 5 minutes without progress
    MAX_REANNOUNCE_ATTEMPTS = 3
    
    def __init__(
        self,
        tracker: "BitTorrentTracker",
        history_service=None,
        history_config: Optional[dict] = None
    ):
        """Initialize the transfer handler.
        
        Args:
            tracker: BitTorrentTracker instance for peer discovery
            history_service: Optional HistoryService for tracking transfers
            history_config: Optional history configuration dict
        """
        self.tracker = tracker
        self.history_service = history_service
        self.history_config = history_config or {}
        # Per-client creation slots: only one torrent may be in TORRENT_CREATING
        # per source client at a time.  Maps client name → torrent.id.
        self._creating_slots: dict[str, str] = {}
    
    def handle_create_queue(self, torrent: Torrent) -> bool:
        """Handle TORRENT_CREATE_QUEUE state.
        
        Checks whether the creation slot for this torrent's source client is
        free.  If so, acquires it and transitions the torrent to
        TORRENT_CREATING.  Otherwise the torrent stays queued and will be
        checked again on the next loop iteration.
        
        Slots are per-client so that different source Deluge instances can
        create transfer torrents concurrently — only concurrent RPCs to the
        *same* instance are serialized (Deluge hashes files serially anyway).
        
        Args:
            torrent: Torrent waiting to create a transfer torrent
            
        Returns:
            True if transitioned to TORRENT_CREATING, False if still queued
        """
        client_name = torrent.home_client.name
        current_holder = self._creating_slots.get(client_name)
        if current_holder is not None:
            logger.debug(
                f"Creation slot for {client_name} occupied (by {current_holder}), "
                f"{torrent.name} stays in TORRENT_CREATE_QUEUE"
            )
            return False
        
        self._creating_slots[client_name] = torrent.id
        torrent.state = TorrentState.TORRENT_CREATING
        logger.debug(f"Creation slot for {client_name} acquired by {torrent.name}")
        return True
    
    def _release_creation_slot(self, torrent: Torrent) -> None:
        """Release the creation slot for the torrent's source client.
        
        Only releases if the slot is currently held by this torrent.
        
        Args:
            torrent: The torrent releasing its slot
        """
        client_name = torrent.home_client.name
        if self._creating_slots.get(client_name) == torrent.id:
            del self._creating_slots[client_name]
            logger.debug(f"Creation slot for {client_name} released by {torrent.id}")
    
    def handle_creating(
        self,
        torrent: Torrent,
        connection: TransferConnection
    ) -> bool:
        """Handle TORRENT_CREATING state (non-blocking, two-phase).
        
        Called every ~2 seconds by the main loop.
        
        **Phase A** (first call): Fires the Deluge create_torrent RPC and
        stores a poll spec in ``torrent.transfer["creating"]``.  Returns
        False so the main loop can continue processing other torrents.
        
        **Phase B** (subsequent calls): Performs one poll to check whether
        Deluge has finished hashing.  Returns False if still waiting, True
        when the torrent is found and the state transitions to
        TORRENT_TARGET_ADDING.
        
        Args:
            torrent: Torrent being transferred
            connection: TransferConnection with source/target clients
            
        Returns:
            True if successful and state transitioned to TORRENT_TARGET_ADDING,
            False if still waiting or failed (stays in current state)
        """
        try:
            # Initialize transfer data if not present
            if not torrent.transfer:
                transfer_id = generate_transfer_id()
                transfer_name = build_transfer_torrent_name(torrent.name, transfer_id)
                torrent.transfer = {
                    "id": transfer_id,
                    "name": transfer_name,
                    "hash": None,  # Set after creation
                    "on_source": False,
                    "on_target": False,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "last_progress_at": None,
                    "bytes_downloaded": 0,
                    "total_size": torrent.size or 0,
                    "retry_count": 0
                }
            
            transfer_data = torrent.transfer
            transfer_name = transfer_data["name"]
            source_client = connection.from_client
            
            # --- Restart recovery: hash already known ---
            if transfer_data.get("hash") and transfer_data.get("on_source"):
                existing_info = self._get_torrent_by_hash(
                    source_client, transfer_data["hash"]
                )
                if existing_info:
                    logger.debug(f"Transfer torrent already exists on source: {transfer_name}")
                    self._register_with_tracker(transfer_data["hash"])
                    self._release_creation_slot(torrent)
                    torrent.state = TorrentState.TORRENT_TARGET_ADDING
                    return True
            
            # --- Phase A: Fire RPC (first call only) ---
            if "creating" not in transfer_data:
                torrent_info = source_client.get_torrent_info(torrent)
                if not torrent_info:
                    logger.error(f"Could not get torrent info for {torrent.name}")
                    self._release_creation_slot(torrent)
                    result = self._handle_retry(torrent, connection)
                    if torrent.transfer:  # Not at max retries, re-queue
                        torrent.state = TorrentState.TORRENT_CREATE_QUEUE
                    return result
                
                save_path = torrent_info.get("save_path", "")
                torrent_name = torrent_info.get("name", torrent.name)
                data_path = f"{save_path}/{torrent_name}".rstrip("/")
                total_size = torrent.size or torrent_info.get("total_size", 0)
                
                tracker_urls = self._get_tracker_urls()
                
                logger.debug(f"Creating transfer torrent '{transfer_name}' from {data_path}")
                logger.debug(f"Tracker URLs for transfer: {tracker_urls}")
                
                poll_spec = source_client.start_create_torrent(
                    path=data_path,
                    trackers=tracker_urls,
                    private=False,
                    add_to_session=True,
                    label="transferarr_tmp",
                    total_size=total_size,
                )
                
                # Store poll spec with wall-clock started_at for persistence
                poll_spec["started_at"] = datetime.now(timezone.utc).isoformat()
                transfer_data["creating"] = poll_spec
                transfer_data["total_size"] = total_size
                
                logger.debug(
                    f"RPC fired for '{transfer_name}', polling with "
                    f"timeout={poll_spec['timeout']}s"
                )
                return False  # Main loop continues to next torrent
            
            # --- Phase B: Poll (subsequent calls) ---
            creating = transfer_data["creating"]
            started_at = datetime.fromisoformat(creating["started_at"])
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            
            if elapsed >= creating["timeout"]:
                logger.warning(
                    f"Torrent creation timed out for {torrent.name} "
                    f"after {elapsed:.0f}s (timeout={creating['timeout']}s)"
                )
                # Clean up creating state so retry starts fresh
                del transfer_data["creating"]
                self._release_creation_slot(torrent)
                result = self._handle_retry(torrent, connection)
                if torrent.transfer:  # Not at max retries, re-queue
                    torrent.state = TorrentState.TORRENT_CREATE_QUEUE
                return result
            
            transfer_hash = source_client.poll_created_torrent(
                creating["expected_name"],
                creating["tracker_urls"],
                label="transferarr_tmp",
            )
            
            if not transfer_hash:
                return False  # Try again next iteration
            
            # --- Found! Complete the creation ---
            del transfer_data["creating"]
            transfer_data["hash"] = transfer_hash
            transfer_data["on_source"] = True
            
            self._register_with_tracker(transfer_hash)
            source_client.force_reannounce(transfer_hash)
            
            logger.info(
                f"Created transfer torrent: {transfer_name} "
                f"(hash: {transfer_hash[:8]}...) on {source_client.name}"
            )
            
            # Create history record
            if self.history_service:
                try:
                    history_id = self.history_service.create_transfer(
                        torrent=torrent,
                        source_client=connection.from_client.name,
                        target_client=connection.to_client.name,
                        connection_name=connection.name,
                        transfer_method='torrent'
                    )
                    torrent._transfer_id = history_id
                    self.history_service.start_transfer(history_id)
                except Exception as e:
                    logger.warning(f"Failed to create history record: {e}")
            
            self._release_creation_slot(torrent)
            torrent.state = TorrentState.TORRENT_TARGET_ADDING
            return True
            
        except Exception as e:
            logger.error(f"Error in TORRENT_CREATING for {torrent.name}: {e}")
            self._release_creation_slot(torrent)
            result = self._handle_retry(torrent, connection)
            if torrent.transfer:  # Not at max retries, re-queue
                torrent.state = TorrentState.TORRENT_CREATE_QUEUE
            return result
    
    def handle_target_adding(
        self,
        torrent: Torrent,
        connection: TransferConnection
    ) -> bool:
        """Handle TORRENT_TARGET_ADDING state.
        
        Gets magnet URI from source and adds transfer torrent to target.
        
        Args:
            torrent: Torrent being transferred
            connection: TransferConnection with source/target clients
            
        Returns:
            True if successful and state transitioned to TORRENT_DOWNLOADING,
            False if failed (stays in current state or ERROR)
        """
        transfer_data = torrent.transfer
        if not transfer_data or not transfer_data.get("hash"):
            logger.error(f"No transfer data/hash for {torrent.name}")
            return self._handle_retry(torrent, connection)
        
        transfer_hash = transfer_data["hash"]
        target_client = connection.to_client
        
        try:
            # Always check if transfer torrent already exists on target,
            # regardless of the on_target flag.  This handles two scenarios:
            # 1. Restart recovery: transfer data says on_target=True, verify it.
            # 2. Race condition: magnet was added on a previous attempt but
            #    on_target was never set (exception before the flag update).
            #    Without this check, a retry would call add_torrent_magnet
            #    again, Deluge returns None for the duplicate, and we'd
            #    incorrectly treat it as a failure.
            existing_info = self._get_torrent_by_hash(target_client, transfer_hash)
            if existing_info:
                logger.debug(f"Transfer torrent already on target: {transfer_hash[:8]}...")
                transfer_data["on_target"] = True
                transfer_data["last_progress_at"] = datetime.now(timezone.utc).isoformat()
                torrent.state = TorrentState.TORRENT_DOWNLOADING
                return True
            else:
                # Not on target (or was removed) - reset flag
                transfer_data["on_target"] = False
            
            # Get magnet URI from source
            source_client = connection.from_client
            magnet_uri = source_client.get_magnet_uri(transfer_hash)
            
            if not magnet_uri:
                logger.error(f"Failed to get magnet URI for {transfer_hash}")
                return self._handle_retry(torrent, connection)
            
            logger.debug(f"Adding transfer torrent to target via magnet: {transfer_hash[:8]}...")
            
            download_options = {}
            
            # Use target's default download path if available
            target_download_path = connection.destination_torrent_download_path
            if target_download_path:
                download_options["download_location"] = target_download_path
            
            # Add to target
            added_hash = target_client.add_torrent_magnet(
                magnet_uri, 
                download_options,
                label="transferarr_tmp"  # Label for easy identification in UI
            )
            
            if not added_hash:
                logger.error(f"Failed to add magnet to target: {transfer_hash}")
                return self._handle_retry(torrent, connection)
            
            # Verify the hash matches
            if added_hash.lower() != transfer_hash.lower():
                logger.warning(
                    f"Hash mismatch: expected {transfer_hash}, got {added_hash}"
                )
            
            # Update transfer data
            transfer_data["on_target"] = True
            transfer_data["last_progress_at"] = datetime.now(timezone.utc).isoformat()
            
            logger.info(
                f"Transfer torrent added to target {target_client.name}: "
                f"{transfer_hash[:8]}..."
            )
            
            # Force re-announce on source so it discovers the target as a peer.
            # Without this, the source won't learn about the target until its next
            # periodic announce (up to 60s). Critical when the source is behind
            # NAT/VPN and can't accept inbound connections — the source must
            # initiate the outbound connection to the target.
            source_client = connection.from_client
            source_client.force_reannounce(transfer_hash)
            
            # Transition to downloading state
            torrent.state = TorrentState.TORRENT_DOWNLOADING
            return True
            
        except Exception as e:
            logger.error(f"Error in TORRENT_TARGET_ADDING for {torrent.name}: {e}")
            return self._handle_retry(torrent, connection)
    
    def handle_downloading(
        self,
        torrent: Torrent,
        connection: TransferConnection
    ) -> bool:
        """Handle TORRENT_DOWNLOADING state.
        
        Monitors download progress on target, detects completion,
        and handles stall detection with re-announce.
        
        Args:
            torrent: Torrent being transferred
            connection: TransferConnection with source/target clients
            
        Returns:
            True if download complete and transitioned to TORRENT_SEEDING,
            False if still downloading or error
        """
        transfer_data = torrent.transfer
        if not transfer_data or not transfer_data.get("hash"):
            logger.error(f"No transfer data/hash for {torrent.name}")
            return self._handle_retry(torrent, connection)
        
        transfer_hash = transfer_data["hash"]
        target_client = connection.to_client
        
        try:
            # Get progress from target
            progress = target_client.get_transfer_progress(transfer_hash)
            
            if not progress:
                logger.warning(f"Could not get progress for {torrent.name} on target")
                # Torrent might have been removed - check if still exists
                existing = self._get_torrent_by_hash(target_client, transfer_hash)
                if not existing:
                    logger.error(f"Transfer torrent missing from target: {torrent.name}")
                    transfer_data["on_target"] = False
                    return self._handle_retry(torrent, connection)
                return False
            
            total_done = progress.get("total_done", 0)
            total_size = progress.get("total_size", 0)
            state = progress.get("state", "")
            download_rate = progress.get("download_payload_rate", 0)
            
            # Update transfer data
            old_bytes = transfer_data.get("bytes_downloaded", 0)
            transfer_data["bytes_downloaded"] = total_done
            transfer_data["total_size"] = total_size
            transfer_data["download_rate"] = download_rate  # Store for API display
            
            # Check for progress
            now = datetime.now(timezone.utc)
            if total_done > old_bytes:
                transfer_data["last_progress_at"] = now.isoformat()
                transfer_data["reannounce_count"] = 0  # Reset stall counter
                
                # Update history if enabled
                if self.history_service and self.history_config.get("track_progress", True):
                    transfer_id = torrent._transfer_id
                    if transfer_id:
                        try:
                            self.history_service.update_progress(transfer_id, total_done)
                        except Exception as e:
                            logger.debug(f"Failed to update history progress: {e}")
            
            # Log progress periodically
            if total_size > 0:
                pct = (total_done / total_size) * 100
                logger.debug(
                    f"Transfer progress for {torrent.name}: {pct:.1f}% "
                    f"({total_done}/{total_size}) rate={download_rate/1024:.1f} KB/s"
                )
            
            # Check if download complete
            if state == "Seeding" or (total_size > 0 and total_done >= total_size):
                logger.info(
                    f"Transfer download complete for {torrent.name}: "
                    f"{total_done} bytes"
                )
                
                # Log where the transfer torrent downloaded files to
                try:
                    logger.debug(
                        f"Transfer torrent location on target: "
                        f"save_path={progress.get('save_path')}, "
                        f"download_location={progress.get('download_location')}"
                    )
                except Exception as e:
                    logger.debug(f"Could not log transfer torrent path: {e}")
                
                torrent.state = TorrentState.TORRENT_SEEDING
                return True
            
            # Check for stall
            last_progress_str = transfer_data.get("last_progress_at")
            if last_progress_str:
                last_progress = datetime.fromisoformat(last_progress_str.replace('Z', '+00:00'))
                stall_seconds = (now - last_progress).total_seconds()
                
                if stall_seconds > self.STALL_THRESHOLD_SECONDS:
                    reannounce_count = transfer_data.get("reannounce_count", 0)
                    
                    if reannounce_count < self.MAX_REANNOUNCE_ATTEMPTS:
                        logger.warning(
                            f"Download stalled for {torrent.name} "
                            f"({stall_seconds:.0f}s), forcing re-announce "
                            f"({reannounce_count + 1}/{self.MAX_REANNOUNCE_ATTEMPTS})"
                        )
                        
                        # Force re-announce on both source and target
                        source_client = connection.from_client
                        source_client.force_reannounce(transfer_hash)
                        target_client.force_reannounce(transfer_hash)
                        
                        transfer_data["reannounce_count"] = reannounce_count + 1
                        transfer_data["last_progress_at"] = now.isoformat()
                    else:
                        logger.error(
                            f"Download stalled for {torrent.name} after "
                            f"{self.MAX_REANNOUNCE_ATTEMPTS} re-announce attempts, "
                            f"setting to TRANSFER_FAILED"
                        )
                        self._cleanup_failed_transfer(torrent, connection)
                        torrent.transfer = None
                        torrent.state = TorrentState.TRANSFER_FAILED
            
            return False
            
        except Exception as e:
            logger.error(f"Error in TORRENT_DOWNLOADING for {torrent.name}: {e}")
            return False
    
    def _fetch_torrent_file_via_sftp(
        self,
        torrent_hash: str,
        source_config: dict
    ) -> Optional[str]:
        """Fetch a .torrent file from the source via SFTP.
        
        Deluge stores .torrent files in its state directory as {hash}.torrent.
        The ``state_dir`` key in source_config provides the path to the state
        directory *as seen from the SFTP server*.
        
        Args:
            torrent_hash: Hash of the torrent to fetch
            source_config: Source access config dict with ``sftp`` (connection
                params) and ``state_dir`` (Deluge state directory path)
            
        Returns:
            Base64-encoded .torrent file data, or None on failure
        """
        import os
        import base64
        from transferarr.clients.ftp import SFTPClient
        
        try:
            state_dir = source_config.get("state_dir")
            if not state_dir:
                logger.error("No state_dir configured in source — cannot locate .torrent files")
                return None
            
            torrent_path = os.path.join(state_dir, f"{torrent_hash}.torrent")
            logger.debug(f"Torrent file path (from state_dir): {torrent_path}")
            
            # Read the file via SFTP using the sftp sub-dict
            sftp_params = source_config.get("sftp", {})
            sftp = SFTPClient(**sftp_params)
            file_data = sftp.read_file(torrent_path)
            
            if not file_data:
                logger.warning(f"Empty torrent file read from {torrent_path}")
                return None
            
            # Validate bencoded format (starts with 'd')
            if file_data[:1] != b'd':
                logger.warning(
                    f"Torrent file doesn't look bencoded (first byte: {file_data[:1]!r}): {torrent_path}"
                )
                return None
            
            encoded = base64.b64encode(file_data).decode('utf-8')
            logger.debug(f"Successfully fetched torrent file via SFTP ({len(file_data)} bytes)")
            return encoded
            
        except Exception as e:
            logger.warning(f"Failed to fetch torrent file via SFTP: {e}")
            return None

    def _fetch_torrent_file_locally(
        self,
        torrent_hash: str,
        state_dir: str
    ) -> Optional[str]:
        """Fetch a .torrent file from a locally-mounted state directory.
        
        Reads the torrent file directly from the filesystem. Used when
        Transferarr has local access to the Deluge state directory
        (Docker volume mount, NFS, same server, etc.).
        
        Args:
            torrent_hash: Hash of the torrent to fetch
            state_dir: Path to the Deluge state directory
            
        Returns:
            Base64-encoded .torrent file data, or None on failure
        """
        import os
        import base64
        
        try:
            torrent_path = os.path.join(state_dir, f"{torrent_hash}.torrent")
            logger.debug(f"Reading torrent file locally: {torrent_path}")
            
            if not os.path.isfile(torrent_path):
                logger.warning(f"Torrent file not found: {torrent_path}")
                return None
            
            with open(torrent_path, "rb") as f:
                file_data = f.read()
            
            if not file_data:
                logger.warning(f"Empty torrent file: {torrent_path}")
                return None
            
            # Validate bencoded format (starts with 'd')
            if file_data[:1] != b'd':
                logger.warning(
                    f"Torrent file doesn't look bencoded (first byte: {file_data[:1]!r}): {torrent_path}"
                )
                return None
            
            encoded = base64.b64encode(file_data).decode('utf-8')
            logger.debug(f"Successfully read torrent file locally ({len(file_data)} bytes)")
            return encoded
            
        except Exception as e:
            logger.warning(f"Failed to read torrent file locally: {e}")
            return None

    def handle_seeding(
        self,
        torrent: Torrent,
        connection: TransferConnection
    ) -> bool:
        """Handle TORRENT_SEEDING state.
        
        Verifies target is seeding the transfer torrent, then adds the
        original torrent to target (which will reuse the downloaded files).
        
        Args:
            torrent: Torrent being transferred
            connection: TransferConnection with source/target clients
            
        Returns:
            True if original added and transitioned to COPIED,
            False if still processing or error
        """
        transfer_data = torrent.transfer
        if not transfer_data or not transfer_data.get("hash"):
            logger.error(f"No transfer data/hash for {torrent.name}")
            return self._handle_retry(torrent, connection)
        
        transfer_hash = transfer_data["hash"]
        target_client = connection.to_client
        source_client = connection.from_client
        
        try:
            # Verify transfer torrent is seeding on target
            progress = target_client.get_transfer_progress(transfer_hash)
            if not progress:
                logger.error(f"Transfer torrent missing from target: {torrent.name}")
                transfer_data["on_target"] = False
                return self._handle_retry(torrent, connection)
            
            state = progress.get("state", "")
            if state != "Seeding":
                logger.debug(f"Transfer torrent not yet seeding: {state}")
                return False
            
            # Check if original already added to target
            if transfer_data.get("original_on_target"):
                # Verify it still exists
                if target_client.has_torrent(torrent):
                    logger.debug(f"Original torrent already on target: {torrent.name}")
                    # Mark history as complete
                    self._complete_history(torrent)
                    # Transition to COPIED - the normal state machine will then track
                    # TARGET_CHECKING → TARGET_SEEDING and handle cleanup
                    torrent.state = TorrentState.COPIED
                    return True
                else:
                    transfer_data["original_on_target"] = False
            
            # Get the actual .torrent file from source (if source access configured)
            # Magnet links require metadata download from peers, which won't work
            # for private torrents where the target can't reach the tracker.
            source_config = connection.source_config
            source_type = connection.source_type
            if source_type == "local":
                logger.debug(f"Fetching torrent file locally for: {torrent.name}")
                torrent_file_data = self._fetch_torrent_file_locally(
                    torrent.id, source_config["state_dir"]
                )
                if not torrent_file_data:
                    logger.error(
                        f"Failed to read .torrent file locally for '{torrent.name}'. "
                        f"Local source is configured — will not fall back to magnet."
                    )
                    return self._handle_retry(torrent, connection)
            elif source_type == "sftp":
                logger.debug(f"Fetching torrent file via SFTP for: {torrent.name}")
                torrent_file_data = self._fetch_torrent_file_via_sftp(
                    torrent.id, source_config
                )
                if not torrent_file_data:
                    logger.error(
                        f"Failed to fetch .torrent file via SFTP for '{torrent.name}'. "
                        f"Source SFTP is configured — will not fall back to magnet."
                    )
                    return self._handle_retry(torrent, connection)
            else:
                # Magnet-only mode — check if the torrent is private first
                try:
                    is_private = source_client.is_private_torrent(torrent.id)
                except Exception as e:
                    logger.warning(
                        f"Could not check private flag for {torrent.name}: {e}. "
                        f"Proceeding with magnet URI (may fail for private torrents)."
                    )
                    is_private = False
                
                if is_private:
                    logger.error(
                        f"Torrent '{torrent.name}' is a private tracker torrent but the "
                        f"connection '{connection.name}' has no source access configured. "
                        f"Private torrents cannot be transferred via magnet links — "
                        f"configure source access (SFTP or local) on the connection to enable .torrent file transfer."
                    )
                    self._cleanup_failed_transfer(torrent, connection)
                    torrent.transfer = None
                    torrent.state = TorrentState.TRANSFER_FAILED
                    return False
                
                torrent_file_data = None
                logger.debug(
                    f"No source access configured for torrent connection '{connection.name}'. "
                    f"Using magnet URI (torrent is not private)."
                )
            
            # Add to target with same download location as transfer torrent
            # The files are already there, so it will just verify/seed
            # Add paused to prevent download attempts before recheck
            download_path = connection.destination_torrent_download_path
            options = {"add_paused": True}
            if download_path:
                options["download_location"] = download_path
            
            if torrent_file_data:
                # Use torrent file - has full metadata, no peer discovery needed
                logger.debug(
                    f"Adding original torrent to target via .torrent file, "
                    f"download_path={download_path}, options={options}"
                )
                
                added_hash = target_client.add_torrent_file(
                    f"{torrent.name}.torrent",
                    torrent_file_data,
                    options
                )
            else:
                # Fallback to magnet (may not work for private torrents)
                original_magnet = source_client.get_magnet_uri(torrent.id)
                if not original_magnet:
                    logger.error(f"Could not get magnet URI for {torrent.name}")
                    return self._handle_retry(torrent, connection)
                
                logger.debug(
                    f"Adding original torrent to target via magnet: {original_magnet[:80]}..., "
                    f"download_path={download_path}, options={options}"
                )
                
                added_hash = target_client.add_torrent_magnet(
                    original_magnet,
                    options
                )
            
            if not added_hash:
                logger.error(f"Failed to add original torrent to target: {torrent.name}")
                return self._handle_retry(torrent, connection)
            
            transfer_data["original_on_target"] = True
            
            # Force recheck so Deluge finds the existing files from the transfer torrent
            # Without this, magnet-added torrents start downloading instead of checking
            logger.debug(f"Forcing recheck for original torrent: {added_hash[:8]}...")
            target_client.force_recheck(added_hash)
            
            # Resume the torrent now that recheck has been triggered
            # (it was added paused to prevent download attempts before recheck)
            target_client.resume_torrent(added_hash)
            
            # Get the actual path where target put the torrent for debugging
            try:
                temp_torrent = Torrent(id=added_hash)
                target_info = target_client.get_torrent_info(temp_torrent)
                logger.debug(
                    f"Original torrent on target: hash={added_hash[:8]}, "
                    f"save_path={target_info.get('save_path')}, "
                    f"download_location={target_info.get('download_location')}, "
                    f"state={target_info.get('state')}"
                )
            except Exception as e:
                logger.debug(f"Could not get original torrent info: {e}")
            
            logger.info(f"Original torrent added to target: {torrent.name}")
            
            # Mark history as complete
            self._complete_history(torrent)
            
            # Transition to COPIED - the normal state machine will then track
            # TARGET_CHECKING → TARGET_SEEDING and handle cleanup
            torrent.state = TorrentState.COPIED
            return True
            
        except Exception as e:
            logger.error(f"Error in TORRENT_SEEDING for {torrent.name}: {e}")
            return self._handle_retry(torrent, connection)
    
    def _complete_history(self, torrent: Torrent) -> None:
        """Mark transfer as complete in history."""
        transfer_id = torrent._transfer_id
        if transfer_id and self.history_service:
            try:
                total_size = torrent.transfer.get("total_size", 0) if torrent.transfer else 0
                self.history_service.complete_transfer(
                    transfer_id, final_bytes=total_size
                )
            except Exception as e:
                logger.warning(f"Failed to complete history record: {e}")
    
    def _get_torrent_by_hash(self, client, torrent_hash: str) -> Optional[dict]:
        """Get torrent info by hash from a client.
        
        Args:
            client: Download client instance
            torrent_hash: Torrent hash to look up
            
        Returns:
            Torrent info dict or None if not found
        """
        try:
            # Create a temporary Torrent object to use existing API
            temp_torrent = Torrent(id=torrent_hash)
            if client.has_torrent(temp_torrent):
                return client.get_torrent_info(temp_torrent)
        except Exception as e:
            logger.debug(f"Error checking torrent {torrent_hash} on {client.name}: {e}")
        return None
    
    def _get_tracker_urls(self) -> list[str]:
        """Build list of tracker URLs for transfer torrents.
        
        Includes both external and internal URLs (if configured) so clients
        on different networks can each reach the tracker. For example, a
        home Deluge behind a VPN can use the internal Docker network URL
        while a remote seedbox uses the external public URL.
        
        Returns:
            List of tracker announce URLs
        """
        urls = [self.tracker.external_url]
        if self.tracker.internal_url:
            urls.append(self.tracker.internal_url)
        return urls
    
    def _register_with_tracker(self, transfer_hash: str) -> None:
        """Register transfer hash with tracker.
        
        Args:
            transfer_hash: Hex string of torrent hash
        """
        try:
            # Convert hex string to bytes
            info_hash_bytes = bytes.fromhex(transfer_hash)
            self.tracker.register_transfer(info_hash_bytes)
            logger.debug(f"Registered with tracker: {transfer_hash[:8]}...")
        except Exception as e:
            logger.error(f"Failed to register with tracker: {e}")
    
    def _handle_retry(self, torrent: Torrent, connection: TransferConnection = None) -> bool:
        """Handle retry logic for failed operations.
        
        Args:
            torrent: Torrent that failed
            connection: TransferConnection for cleanup (needed for client removal)
            
        Returns:
            Always False to indicate failure
        """
        if torrent.transfer:
            torrent.transfer["retry_count"] = torrent.transfer.get("retry_count", 0) + 1
            
            if torrent.transfer["retry_count"] >= self.MAX_RETRIES:
                logger.error(
                    f"Max retries ({self.MAX_RETRIES}) reached for {torrent.name}, "
                    f"setting to TRANSFER_FAILED state"
                )
                # Cleanup and set to TRANSFER_FAILED (sticky state requiring user action)
                self._cleanup_failed_transfer(torrent, connection)
                torrent.transfer = None
                torrent.state = TorrentState.TRANSFER_FAILED
                return False
            
            logger.warning(
                f"Retry {torrent.transfer['retry_count']}/{self.MAX_RETRIES} "
                f"for {torrent.name}"
            )
        
        return False
    
    def _cleanup_failed_transfer(self, torrent: Torrent, connection: TransferConnection = None) -> None:
        """Clean up after a failed transfer.
        
        Removes transfer torrent from both source and target clients,
        and unregisters from tracker. Marks history as failed.
        
        Args:
            torrent: Torrent with failed transfer
            connection: TransferConnection for client access
        """
        if not torrent.transfer:
            return
        
        transfer_hash = torrent.transfer.get("hash")
        if not transfer_hash:
            return
        
        logger.info(f"Cleaning up failed transfer for {torrent.name}")
        
        source_client = connection.from_client if connection else None
        target_client = connection.to_client if connection else None
        
        self.cleanup_transfer_torrents(
            torrent,
            source_client=source_client,
            target_client=target_client,
        )
        
        # Mark history as failed
        transfer_id = torrent._transfer_id
        if transfer_id and self.history_service:
            try:
                self.history_service.fail_transfer(
                    transfer_id,
                    f"Max retries exceeded after {self.MAX_RETRIES} attempts"
                )
            except Exception as e:
                logger.warning(f"Failed to mark history as failed: {e}")
    
    def cleanup_transfer_torrents(
        self,
        torrent: Torrent,
        source_client=None,
        target_client=None,
    ) -> None:
        """Remove transfer torrent from clients and unregister from tracker.
        
        Shared cleanup logic used by both _cleanup_failed_transfer (error path)
        and torrent_service.py TARGET_SEEDING (success path).
        
        Args:
            torrent: Torrent with transfer data containing 'hash'
            source_client: Source download client (or None to skip)
            target_client: Target download client (or None to skip)
        """
        if not torrent.transfer:
            return
        
        transfer_hash = torrent.transfer.get("hash")
        if not transfer_hash:
            return
        
        # Remove transfer torrent from target
        if target_client and torrent.transfer.get("on_target", True):
            try:
                target_client.remove_torrent(transfer_hash, remove_data=False)
                logger.debug(f"Removed transfer torrent from target")
            except Exception as e:
                logger.warning(f"Failed to remove transfer torrent from target: {e}")
        
        # Remove transfer torrent from source
        if source_client and torrent.transfer.get("on_source", True):
            try:
                source_client.remove_torrent(transfer_hash, remove_data=False)
                logger.debug(f"Removed transfer torrent from source")
            except Exception as e:
                logger.warning(f"Failed to remove transfer torrent from source: {e}")
        
        # Unregister from tracker
        if self.tracker:
            try:
                info_hash_bytes = bytes.fromhex(transfer_hash)
                self.tracker.unregister_transfer(info_hash_bytes)
                logger.debug(f"Unregistered transfer hash from tracker")
            except Exception as e:
                logger.warning(f"Failed to unregister from tracker: {e}")
        
        torrent.transfer["cleaned_up"] = True
        torrent.mark_dirty()
