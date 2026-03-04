"""Handler for torrent-based file transfers.

Implements the torrent-based transfer states for transferring files
between Deluge instances using BitTorrent protocol.

States handled:
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
from transferarr.utils import generate_transfer_id, build_transfer_torrent_name

if TYPE_CHECKING:
    from transferarr.services.tracker import BitTorrentTracker

logger = logging.getLogger("transferarr")


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
    
    def handle_creating(
        self,
        torrent: Torrent,
        connection: TransferConnection
    ) -> bool:
        """Handle TORRENT_CREATING state.
        
        Creates a transfer torrent on the source client with a unique name
        that produces a different hash from the original.
        
        Args:
            torrent: Torrent being transferred
            connection: TransferConnection with source/target clients
            
        Returns:
            True if successful and state transitioned to TORRENT_TARGET_ADDING,
            False if failed (stays in current state or ERROR)
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
            
            # Check if transfer torrent already exists on source (restart scenario)
            source_client = connection.from_client
            if transfer_data.get("hash") and transfer_data.get("on_source"):
                # Verify it still exists
                existing_info = self._get_torrent_by_hash(
                    source_client, transfer_data["hash"]
                )
                if existing_info:
                    logger.info(f"Transfer torrent already exists on source: {transfer_name}")
                    # Ensure tracker registration
                    self._register_with_tracker(transfer_data["hash"])
                    torrent.state = TorrentState.TORRENT_TARGET_ADDING
                    return True
            
            # Get the data path from the original torrent
            torrent_info = source_client.get_torrent_info(torrent)
            if not torrent_info:
                logger.error(f"Could not get torrent info for {torrent.name}")
                return self._handle_retry(torrent, connection)
            
            # The path to create torrent from
            # For single file: save_path/name, for directory: save_path/name
            save_path = torrent_info.get("save_path", "")
            torrent_name = torrent_info.get("name", torrent.name)
            data_path = f"{save_path}/{torrent_name}".rstrip("/")
            
            # Create the transfer torrent with unique name
            tracker_url = self.tracker.external_url
            
            logger.info(f"Creating transfer torrent '{transfer_name}' from {data_path}")
            
            # Deluge 2.x create_torrent doesn't take a name parameter -
            # the torrent name comes from the path. So we create with original path
            # and get a unique hash because of the tracker URL.
            # private=False allows BEP 9 (ut_metadata) metadata exchange so the
            # target can resolve the torrent info dict from the magnet URI.
            
            transfer_hash = source_client.create_torrent(
                path=data_path,
                name=transfer_name,  # This doesn't affect hash, just for logging
                trackers=[tracker_url],
                private=False,
                add_to_session=True,
                label="transferarr_tmp"
            )
            
            if not transfer_hash:
                logger.error(f"Failed to create transfer torrent for {torrent.name}")
                return self._handle_retry(torrent, connection)
            
            # Update transfer data with the new hash
            transfer_data["hash"] = transfer_hash
            transfer_data["on_source"] = True
            transfer_data["total_size"] = torrent.size or torrent_info.get("total_size", 0)
            
            # Register with tracker for peer discovery
            self._register_with_tracker(transfer_hash)
            
            # Force re-announce so source's peer info gets stored.
            # The source already announced immediately after create_torrent,
            # but the hash wasn't registered yet so the tracker ignored it.
            source_client.force_reannounce(transfer_hash)
            
            logger.info(
                f"Created transfer torrent: {transfer_name} "
                f"(hash: {transfer_hash[:8]}...) on {source_client.name}"
            )
            
            # Create history record
            if self.history_service:
                try:
                    transfer_id = self.history_service.create_transfer(
                        torrent=torrent,
                        source_client=connection.from_client.name,
                        target_client=connection.to_client.name,
                        connection_name=connection.name,
                        transfer_method='torrent'
                    )
                    torrent._transfer_id = transfer_id
                    self.history_service.start_transfer(transfer_id)
                except Exception as e:
                    logger.warning(f"Failed to create history record: {e}")
            
            # Transition to next state
            torrent.state = TorrentState.TORRENT_TARGET_ADDING
            return True
            
        except Exception as e:
            logger.error(f"Error in TORRENT_CREATING for {torrent.name}: {e}")
            return self._handle_retry(torrent, connection)
    
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
            # Check if already on target (restart scenario)
            if transfer_data.get("on_target"):
                existing_info = self._get_torrent_by_hash(target_client, transfer_hash)
                if existing_info:
                    logger.info(f"Transfer torrent already on target: {transfer_hash[:8]}...")
                    torrent.state = TorrentState.TORRENT_DOWNLOADING
                    return True
                else:
                    # Was marked on_target but not actually there - reset flag
                    transfer_data["on_target"] = False
            
            # Get magnet URI from source
            source_client = connection.from_client
            magnet_uri = source_client.get_magnet_uri(transfer_hash)
            
            if not magnet_uri:
                logger.error(f"Failed to get magnet URI for {transfer_hash}")
                return self._handle_retry(torrent, connection)
            
            logger.info(f"Adding transfer torrent to target via magnet: {transfer_hash[:8]}...")
            
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
                            f"{self.MAX_REANNOUNCE_ATTEMPTS} re-announce attempts"
                        )
                        # Mark as stalled but don't fail yet - user can cancel
                        transfer_data["stalled"] = True
            
            return False
            
        except Exception as e:
            logger.error(f"Error in TORRENT_DOWNLOADING for {torrent.name}: {e}")
            return False
    
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
                    logger.info(f"Original torrent already on target: {torrent.name}")
                    # Mark history as complete
                    self._complete_history(torrent)
                    # Transition to COPIED - the normal state machine will then track
                    # TARGET_CHECKING → TARGET_SEEDING and handle cleanup
                    torrent.state = TorrentState.COPIED
                    return True
                else:
                    transfer_data["original_on_target"] = False
            
            # Get magnet URI from source for the original torrent
            # (We can't access the .torrent file since it's inside the Deluge container)
            logger.info(f"Adding original torrent to target via magnet: {torrent.name}")
            
            original_magnet = source_client.get_magnet_uri(torrent.id)
            if not original_magnet:
                logger.error(f"Could not get magnet URI for {torrent.name}")
                return self._handle_retry(torrent, connection)
            
            # Add to target with same download location as transfer torrent
            # The files are already there, so it will just verify/seed
            download_path = connection.destination_torrent_download_path
            options = {}
            if download_path:
                options["download_location"] = download_path
            
            added_hash = target_client.add_torrent_magnet(
                original_magnet,
                options
            )
            
            if not added_hash:
                logger.error(f"Failed to add original torrent magnet to target: {torrent.name}")
                return self._handle_retry(torrent, connection)
            
            transfer_data["original_on_target"] = True
            
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
                    f"resetting to HOME_SEEDING"
                )
                # Cleanup and reset
                self._cleanup_failed_transfer(torrent, connection)
                torrent.transfer = None
                torrent.state = TorrentState.HOME_SEEDING
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
