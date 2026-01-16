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

class TransferConnection:
    max_transfers = 3
    
    def __init__(self, name, config, from_client, to_client):
        self.name = name
        self.config = config
        self.transfer_config = config.get("transfer_config")
        self.source_dot_torrent_path = config.get("source_dot_torrent_path")
        self.source_torrent_download_path = config.get("source_torrent_download_path")
        self.destination_dot_torrent_tmp_dir = config.get("destination_dot_torrent_tmp_dir")
        self.destination_torrent_download_path = config.get("destination_torrent_download_path")
        self.from_client = from_client
        self.to_client = to_client
        
        # Create instance-level thread pool and tracking variables
        self._transfer_executor = ThreadPoolExecutor(max_workers=self.max_transfers)
        self._active_transfers = {}
        self._lock = threading.Lock()
    
    def setup_transfer_clients(self):
        # This method is now a no-op, but kept for compatibility
        pass
    
    def get_transfer_client(self):
        """Create and return a new transfer client instance"""
        from_config = self.config["transfer_config"]["from"]
        to_config = self.config["transfer_config"]["to"]
        return get_transfer_client(from_config, to_config)
    
    def enqueue_copy_torrent(self, torrent):
        """Enqueue a torrent for copying in the background"""
        with self._lock:
            if torrent.name in self._active_transfers:
                logger.debug(f"Torrent {torrent.name} already queued for transfer, skipping")
                return False
            
            logger.info(f"Enqueueing torrent {torrent.name} for copying")
            torrent.state = TorrentState.COPYING
            self._active_transfers[torrent.name] = torrent
            self._transfer_executor.submit(self._do_copy_torrent_task, torrent)
            return True
    
    def _do_copy_torrent_task(self, torrent):
        """Background task to copy a torrent"""
        try:
            self._do_copy_torrent(torrent)
        finally:
            with self._lock:
                if torrent.name in self._active_transfers:
                    del self._active_transfers[torrent.name]
    
    def _do_copy_torrent(self, torrent):
        ## Copy .torrent file to tmp dir
        torrent.state = TorrentState.COPYING
        dot_torrent_file_path = str(Path(self.source_dot_torrent_path).joinpath(f"{torrent.id}.torrent"))

        # Create a new transfer client for this thread
        transfer_client = self.get_transfer_client()

        if not transfer_client.file_exists_on_source(dot_torrent_file_path):
            logger.error(f"Source .torrent file does not exist: {dot_torrent_file_path}")
            torrent.state = TorrentState.ERROR
            return
        
        file_dump = transfer_client.get_dot_torrent_file_dump(dot_torrent_file_path)

        torrent.current_file = os.path.basename(dot_torrent_file_path)
        success = transfer_client.upload(dot_torrent_file_path, self.destination_dot_torrent_tmp_dir, torrent)
        if not success:
            torrent.state = TorrentState.ERROR
            logger.error(f"Failed to copy .torrent file: {dot_torrent_file_path}")
            return
            
        dest_dot_torrent_path = str(Path(self.destination_dot_torrent_tmp_dir).joinpath(f"{torrent.id}.torrent"))
        paths_to_copy = get_paths_to_copy(torrent)
        for path in paths_to_copy:
            source_file_path = str(Path(self.source_torrent_download_path).joinpath(Path(path)))
            destination = self.destination_torrent_download_path

            success = transfer_client.upload(source_file_path, destination, torrent)
            if success:
                torrent.state = TorrentState.COPIED
            else:
                torrent.state = TorrentState.ERROR
                break
                
        torrent.current_file = ""  # Clear current file when all transfers are complete
                
        if torrent.state == TorrentState.COPIED:
            try:
                self.to_client.add_torrent_file(dest_dot_torrent_path, file_dump, {})
                self.to_client_info = self.to_client.get_torrent_info(torrent)
                torrent.state = self.to_client.get_torrent_state(torrent)
                logger.info(f"Torrent added successfully: {torrent.name}")
            except Exception as e:
                logger.error(f"Error adding torrent: {e}")
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
        """Test the connection to the transfer client"""
        try:
            self.get_transfer_client()
            return  {"success": True, "message": "Connection successful"}
        except TrasnferClientException as e:
            logger.debug(f"Connection test failed: {e}")
            return {"success": False, "message": str(e)}
        try:
            transfer_client = self.get_transfer_client()
            transfer_client.test_connection()
            logger.debug(f"Connection test successful for {self.from_client.name} to {self.to_client.name}")
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.debug(f"Connection test failed for {self.from_client.name} to {self.to_client.name}: {e}")
            return {"success": False, "message": str(e)}