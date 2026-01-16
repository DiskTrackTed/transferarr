"""
Service for torrent listing (read-only operations).
"""
import logging

logger = logging.getLogger("transferarr")


class TorrentService:
    """Service for torrent listing operations."""
    
    def __init__(self, torrent_manager):
        self.torrent_manager = torrent_manager
    
    def list_tracked_torrents(self) -> list:
        """Get all torrents tracked by transferarr."""
        return [torrent.to_dict() for torrent in self.torrent_manager.torrents]
    
    def get_all_client_torrents(self) -> dict:
        """Get all torrents from all download clients.
        
        Returns:
            Dict mapping client name to torrent dict
        """
        all_torrents = {}
        
        for client_name, client in self.torrent_manager.download_clients.items():
            try:
                # Use duck typing - check for methods instead of isinstance
                if hasattr(client, 'is_connected') and hasattr(client, 'get_all_torrents_status'):
                    if not client.is_connected():
                        logger.warning(f"Client {client_name} is not connected, skipping")
                        all_torrents[client_name] = {}
                        continue
                    
                    all_torrents[client_name] = client.get_all_torrents_status() or {}
                else:
                    logger.warning(f"Client {client_name} does not support torrent listing")
                    all_torrents[client_name] = {}
            except Exception as e:
                logger.error(f"Failed to get torrents from client {client_name}: {e}")
                all_torrents[client_name] = {}
        
        return all_torrents
