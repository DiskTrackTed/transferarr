"""
Abstract base class for download clients.

All download client implementations must inherit from DownloadClientBase
and implement all abstract methods.
"""
from abc import ABC, abstractmethod
import threading
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from transferarr.clients.config import ClientConfig

if TYPE_CHECKING:
    from transferarr.models.torrent import Torrent, TorrentState


class DownloadClientBase(ABC):
    """Abstract base class defining the contract for download clients.
    
    All download clients (Deluge, qBittorrent, Transmission, etc.) must
    inherit from this class and implement the abstract methods.
    
    Attributes:
        config: ClientConfig instance with all configuration
        name: Instance name for this client (shortcut to config.name)
        type: Client type identifier (shortcut to config.client_type)
        host: Server hostname (shortcut to config.host)
        port: Server port (shortcut to config.port)
        username: Username for authentication (shortcut to config.username)
        password: Password for authentication (shortcut to config.password)
        connections: List of transfer connections using this client
        _lock: Thread lock for connection safety
    """
    
    def __init__(self, config: ClientConfig):
        """Initialize the base download client.
        
        Args:
            config: ClientConfig instance with all configuration
        """
        self.config = config
        # Expose common properties for convenience
        self.name = config.name
        self.type = config.client_type
        self.host = config.host
        self.port = config.port
        self.username = config.username
        self.password = config.password
        self.connections: list = []
        self._lock = threading.RLock()
    
    # -------------------------------------------------------------------------
    # Abstract methods - must be implemented by all subclasses
    # -------------------------------------------------------------------------
    
    @abstractmethod
    def ensure_connected(self) -> bool:
        """Ensure the client is connected, reconnect if needed.
        
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the client is currently connected.
        
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def has_torrent(self, torrent: "Torrent") -> bool:
        """Check if a torrent exists on this client.
        
        Args:
            torrent: Torrent object to check
            
        Returns:
            True if torrent exists, False otherwise
        """
        pass
    
    @abstractmethod
    def get_torrent_info(self, torrent: "Torrent") -> Optional[dict]:
        """Get torrent metadata.
        
        Args:
            torrent: Torrent object to get info for
            
        Returns:
            Dict with torrent info or None if not found
        """
        pass
    
    @abstractmethod
    def get_torrent_state(self, torrent: "Torrent") -> "TorrentState":
        """Get the current state of a torrent.
        
        Args:
            torrent: Torrent object to get state for
            
        Returns:
            TorrentState enum value
        """
        pass
    
    @abstractmethod
    def add_torrent_file(self, path: str, data: bytes, options: dict) -> None:
        """Add a torrent to the client.
        
        Args:
            path: Path/name for the torrent file
            data: Raw torrent file data
            options: Client-specific options (e.g., download_location)
            
        Raises:
            ConnectionError: If not connected
            Exception: If adding fails
        """
        pass
    
    @abstractmethod
    def remove_torrent(self, torrent_id: str, remove_data: bool = True) -> None:
        """Remove a torrent from the client.
        
        Args:
            torrent_id: Torrent identifier (usually info hash)
            remove_data: Whether to also delete downloaded data
            
        Raises:
            ConnectionError: If not connected
            Exception: If removal fails
        """
        pass
    
    @abstractmethod
    def get_all_torrents_status(self) -> dict:
        """Get status of all torrents on this client.
        
        Returns:
            Dict mapping torrent IDs to their status info
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to this client.
        
        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        pass
    
    # -------------------------------------------------------------------------
    # Optional methods - raise NotImplementedError by default
    # Subclasses can override these if the client supports the functionality
    # -------------------------------------------------------------------------
    
    def start_torrent(self, torrent_id: str) -> None:
        """Start/resume a torrent.
        
        Args:
            torrent_id: Torrent identifier (usually info hash)
            
        Raises:
            NotImplementedError: If client doesn't support this operation
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support start_torrent")
    
    def stop_torrent(self, torrent_id: str) -> None:
        """Stop/pause a torrent.
        
        Args:
            torrent_id: Torrent identifier (usually info hash)
            
        Raises:
            NotImplementedError: If client doesn't support this operation
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support stop_torrent")
    
    def verify_torrent(self, torrent_id: str) -> None:
        """Force recheck/verify a torrent.
        
        Args:
            torrent_id: Torrent identifier (usually info hash)
            
        Raises:
            NotImplementedError: If client doesn't support this operation
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support verify_torrent")
    
    # -------------------------------------------------------------------------
    # Concrete methods - shared implementation for all clients
    # -------------------------------------------------------------------------
    
    def add_connection(self, connection) -> None:
        """Add a transfer connection that uses this client.
        
        Args:
            connection: TransferConnection object
        """
        self.connections.append(connection)
    
    def remove_connection(self, connection) -> None:
        """Remove a transfer connection from this client.
        
        Args:
            connection: TransferConnection object
        """
        self.connections.remove(connection)
