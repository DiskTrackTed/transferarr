import logging
import os
from pathlib import Path
from transferarr.utils import get_paths_to_copy
from transferarr.models.torrent import TorrentState
from transferarr.clients.transfer_client import get_transfer_client
from transferarr.exceptions import TrasnferClientException
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

# Transfer type constants
TRANSFER_TYPE_SFTP = "sftp"
TRANSFER_TYPE_TORRENT = "torrent"
DEFAULT_TRANSFER_TYPE = TRANSFER_TYPE_SFTP


def test_torrent_client_connectivity(from_client, to_client) -> list:
    """Test that both download clients are reachable for a torrent transfer.
    
    Shared helper used by both TransferConnection.test_connection() (runtime)
    and ConnectionService.test_connection() (settings UI).
    
    Args:
        from_client: Source download client instance
        to_client: Target download client instance
        
    Returns:
        List of dicts with component, success, and message for each client.
    """
    details = []
    
    for role, client in [("Source", from_client), ("Target", to_client)]:
        try:
            if client.ensure_connected():
                details.append({"component": f"{role}: {client.name}", "success": True, "message": "Connected"})
            else:
                details.append({"component": f"{role}: {client.name}", "success": False, "message": "Could not connect — check host, port, and credentials"})
        except Exception as e:
            details.append({"component": f"{role}: {client.name}", "success": False, "message": str(e)})
    
    return details


def _test_sftp_connectivity(sftp_config: dict) -> list:
    """Test SFTP connectivity for source SFTP configuration.
    
    Creates a temporary SFTPClient, attempts to connect, and returns
    a result list compatible with the test_connection details format.
    
    Args:
        sftp_config: Dict with SFTP connection params (host, port, username, password, etc.)
        
    Returns:
        List with a single dict: component, success, and message.
    """
    from transferarr.clients.ftp import SFTPClient
    from transferarr.services.torrent_transfer import _sftp_client_params

    try:
        client = SFTPClient(**_sftp_client_params(sftp_config))
        # SFTPClient connects in __init__ and immediately closes,
        # so reaching here means connection succeeded.
        return [{"component": "Source SFTP", "success": True, "message": "Connected"}]
    except Exception as e:
        return [{"component": "Source SFTP", "success": False, "message": str(e)}]


def _test_local_state_dir(source_config: dict) -> list:
    """Test local access to the Deluge state directory.
    
    Verifies the state_dir path exists and is readable.
    
    Args:
        source_config: Source config dict with at least ``state_dir``.
        
    Returns:
        List with a single dict: component, success, and message.
    """
    import os
    
    state_dir = source_config.get("state_dir")
    if not state_dir:
        return [{"component": "Source Local", "success": False, "message": "No state_dir configured"}]
    
    if not os.path.isdir(state_dir):
        return [{"component": "Source Local", "success": False, "message": f"Directory not found: {state_dir}"}]
    
    if not os.access(state_dir, os.R_OK):
        return [{"component": "Source Local", "success": False, "message": f"Directory not readable: {state_dir}"}]
    
    return [{"component": "Source Local", "success": True, "message": f"Directory accessible: {state_dir}"}]


def get_transfer_type(transfer_config: dict) -> str:
    """Get the transfer type from config, defaulting to SFTP for backward compatibility.
    
    Args:
        transfer_config: The transfer_config dict from connection config
        
    Returns:
        Transfer type string ("sftp" or "torrent")
    """
    if not transfer_config:
        return DEFAULT_TRANSFER_TYPE
    return transfer_config.get("type", DEFAULT_TRANSFER_TYPE)


def is_torrent_transfer(transfer_config: dict) -> bool:
    """Check if the transfer config specifies torrent-based transfer.
    
    Args:
        transfer_config: The transfer_config dict from connection config
        
    Returns:
        True if torrent-based transfer, False for SFTP
    """
    return get_transfer_type(transfer_config) == TRANSFER_TYPE_TORRENT


class TransferConnection:
    max_transfers = 3
    
    def __init__(self, name, config, from_client, to_client, history_service=None, history_config=None):
        self.name = name
        self.config = config
        self.transfer_config = config.get("transfer_config")
        self.source_dot_torrent_path = config.get("source_dot_torrent_path")
        self.source_torrent_download_path = config.get("source_torrent_download_path")
        self.destination_dot_torrent_tmp_dir = config.get("destination_dot_torrent_tmp_dir")
        self.destination_torrent_download_path = config.get("destination_torrent_download_path")
        self.from_client = from_client
        self.to_client = to_client
        self.history_service = history_service
        self.history_config = history_config or {}
        self.track_progress = self.history_config.get("track_progress", True)
        
        # Transfer type (sftp or torrent)
        self.transfer_type = get_transfer_type(self.transfer_config)
        logger.debug(f"Connection '{name}' transfer_config={self.transfer_config}, transfer_type={self.transfer_type}")
        
        # For torrent transfers, read destination_path from transfer_config
        if self.is_torrent_transfer and self.transfer_config:
            torrent_dest = self.transfer_config.get("destination_path")
            if torrent_dest:
                self.destination_torrent_download_path = torrent_dest
        
        # Create instance-level thread pool and tracking variables
        self._transfer_executor = ThreadPoolExecutor(max_workers=self.max_transfers)
        self._active_transfers = {}
        self._lock = threading.Lock()
    
    @property
    def is_torrent_transfer(self) -> bool:
        """Check if this connection uses torrent-based transfer."""
        return self.transfer_type == TRANSFER_TYPE_TORRENT
    
    @property
    def source_config(self) -> dict:
        """Get source access config for torrent connections, if configured.
        
        Returns:
            Dict with source access config (type, sftp, state_dir)
            or None if not configured or not a torrent connection.
        """
        if not self.is_torrent_transfer or not self.transfer_config:
            return None
        return self.transfer_config.get("source")
    
    @property
    def source_type(self) -> str:
        """Get source access type for torrent connections.
        
        Returns:
            "sftp", "local", or None (magnet-only).
        """
        config = self.source_config
        if not config:
            return None
        return config.get("type")
    
    def get_history_transfer_method(self) -> str:
        """Get the transfer method string for history records.
        
        Returns:
            'torrent' for torrent transfers, 'sftp' if any side uses SFTP,
            'local' if both sides are local.
        """
        if self.is_torrent_transfer:
            return 'torrent'
        
        # File transfer: check from/to types
        if self.transfer_config:
            from_type = self.transfer_config.get('from', {}).get('type', 'local')
            to_type = self.transfer_config.get('to', {}).get('type', 'local')
            if from_type == 'sftp' or to_type == 'sftp':
                return 'sftp'
        
        return 'local'
    
    def get_transfer_client(self):
        """Create and return a new transfer client instance.
        
        Raises:
            RuntimeError: If called on a torrent-type connection (no filesystem access)
        """
        if self.is_torrent_transfer:
            raise RuntimeError(
                f"Cannot create transfer client for torrent connection '{self.name}'. "
                "Torrent transfers use BitTorrent P2P, not filesystem access."
            )
        from_config = self.config["transfer_config"]["from"]
        to_config = self.config["transfer_config"]["to"]
        return get_transfer_client(from_config, to_config)
    
    def enqueue_copy_torrent(self, torrent):
        """Enqueue a torrent for copying in the background"""
        with self._lock:
            if torrent.id in self._active_transfers:
                logger.debug(f"Torrent {torrent.name} ({torrent.id[:8]}) already queued for transfer, skipping")
                return False
            
            logger.info(f"Enqueueing torrent {torrent.name} for copying")
            torrent.state = TorrentState.COPYING
            
            # Create history record for this transfer
            if self.history_service:
                transfer_id = self.history_service.create_transfer(
                    torrent=torrent,
                    source_client=self.from_client.name,
                    target_client=self.to_client.name,
                    connection_name=self.name,
                    transfer_method=self.get_history_transfer_method()
                )
                torrent._transfer_id = transfer_id  # Attach for later updates
                torrent.mark_dirty()
            
            self._active_transfers[torrent.id] = torrent
            self._transfer_executor.submit(self._do_copy_torrent_task, torrent)
            return True
    
    def _do_copy_torrent_task(self, torrent):
        """Background task to copy a torrent"""
        try:
            self._do_copy_torrent(torrent)
        except Exception as e:
            logger.error(f"Unexpected error copying torrent {torrent.name}: {e}")
            torrent.state = TorrentState.ERROR
        finally:
            with self._lock:
                if torrent.id in self._active_transfers:
                    del self._active_transfers[torrent.id]
    
    def _do_copy_torrent(self, torrent):
        ## Copy .torrent file to tmp dir
        torrent.state = TorrentState.COPYING
        dot_torrent_file_path = str(Path(self.source_dot_torrent_path).joinpath(f"{torrent.id}.torrent"))
        
        # Get transfer_id for history tracking
        transfer_id = torrent._transfer_id

        # Create a new transfer client for this thread
        transfer_client = self.get_transfer_client()
        
        # Mark transfer as started in history
        if transfer_id and self.history_service:
            self.history_service.start_transfer(transfer_id)

        if not transfer_client.file_exists_on_source(dot_torrent_file_path):
            logger.error(f"Source .torrent file does not exist: {dot_torrent_file_path}")
            torrent.state = TorrentState.ERROR
            if transfer_id and self.history_service:
                self.history_service.fail_transfer(transfer_id, f"Source .torrent file not found: {dot_torrent_file_path}")
            return
        
        file_dump = transfer_client.get_dot_torrent_file_dump(dot_torrent_file_path)

        torrent.current_file = os.path.basename(dot_torrent_file_path)
        success = transfer_client.upload(dot_torrent_file_path, self.destination_dot_torrent_tmp_dir, torrent)
        if not success:
            torrent.state = TorrentState.ERROR
            logger.error(f"Failed to copy .torrent file: {dot_torrent_file_path}")
            if transfer_id and self.history_service:
                self.history_service.fail_transfer(transfer_id, f"Failed to copy .torrent file: {dot_torrent_file_path}")
            return
            
        dest_dot_torrent_path = str(Path(self.destination_dot_torrent_tmp_dir).joinpath(f"{torrent.id}.torrent"))
        paths_to_copy = get_paths_to_copy(torrent)
        bytes_transferred = 0
        
        for path in paths_to_copy:
            source_file_path = str(Path(self.source_torrent_download_path).joinpath(Path(path)))
            destination = self.destination_torrent_download_path
            
            # Get file size for progress tracking
            file_size = transfer_client.get_file_size(source_file_path) if hasattr(transfer_client, 'get_file_size') else 0

            success = transfer_client.upload(source_file_path, destination, torrent)
            if success:
                torrent.state = TorrentState.COPIED
                bytes_transferred += file_size
                # Update progress in history (if track_progress enabled)
                if transfer_id and self.history_service and file_size > 0 and self.track_progress:
                    self.history_service.update_progress(transfer_id, bytes_transferred)
            else:
                torrent.state = TorrentState.ERROR
                if transfer_id and self.history_service:
                    # Record partial progress before marking as failed
                    if bytes_transferred > 0:
                        self.history_service.update_progress(transfer_id, bytes_transferred, force=True)
                    self.history_service.fail_transfer(transfer_id, f"Failed to upload: {source_file_path}")
                break
                
        torrent.current_file = ""  # Clear current file when all transfers are complete
                
        if torrent.state == TorrentState.COPIED:
            try:
                self.to_client.add_torrent_file(dest_dot_torrent_path, file_dump, {})
                self.to_client_info = self.to_client.get_torrent_info(torrent)
                torrent.state = self.to_client.get_torrent_state(torrent)
                logger.info(f"Torrent added successfully: {torrent.name}")
                # Mark transfer as completed in history
                if transfer_id and self.history_service:
                    # Force final progress update to ensure bytes are accurate
                    total_size = getattr(torrent, 'size', bytes_transferred) or bytes_transferred
                    self.history_service.update_progress(transfer_id, total_size, force=True)
                    self.history_service.complete_transfer(transfer_id)
            except Exception as e:
                logger.error(f"Error adding torrent: {e}")
                if transfer_id and self.history_service:
                    self.history_service.fail_transfer(transfer_id, f"Error adding torrent to target client: {e}")
                torrent.state = TorrentState.ERROR

    
    def get_active_transfers(self):
        """Get a list of currently transferring torrents"""
        with self._lock:
            return list(self._active_transfers.values())
    
    def shutdown(self):
        """Shutdown the transfer executor"""
        self._transfer_executor.shutdown(wait=True)

    def get_active_transfers_count(self):
        active_count = len(self._active_transfers)
        return active_count
    
    def get_total_transfers_count(self):
        """Get the total number of transfers for this connection."""
        # This is a placeholder - you might want to implement historical transfer tracking
        # For now, return the queue length plus active transfers
        total_count = self.get_active_transfers_count()
        return total_count
    
    def test_connection(self):
        """Test the connection to the transfer client.
        
        For torrent connections: tests that both download clients are reachable.
        For file connections: tests SFTP/local filesystem connectivity.
        """
        if self.is_torrent_transfer:
            return self._test_torrent_connection()
        
        try:
            transfer_client = self.get_transfer_client()
            transfer_client.test_connection()
            logger.debug(f"Connection test successful for {self.from_client.name} to {self.to_client.name}")
            return {"success": True, "message": "Connection successful"}
        except TrasnferClientException as e:
            logger.debug(f"Connection test failed: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.debug(f"Connection test failed for {self.from_client.name} to {self.to_client.name}: {e}")
            return {"success": False, "message": str(e)}
    
    def _test_torrent_connection(self):
        """Test a torrent-type connection by verifying clients and source access."""
        details = test_torrent_client_connectivity(self.from_client, self.to_client)
        
        # Test source access if configured
        source_type = self.source_type
        source_config = self.source_config
        if source_type == "sftp" and source_config.get("sftp"):
            details.extend(_test_sftp_connectivity(source_config["sftp"]))
        elif source_type == "local":
            details.extend(_test_local_state_dir(source_config))
        
        failed = [d for d in details if not d["success"]]
        if failed:
            summary = "; ".join(f"{d['component']}: {d['message']}" for d in failed)
            return {"success": False, "message": summary, "details": details}
        
        return {"success": True, "message": "Clients reachable", "details": details}