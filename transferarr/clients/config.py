"""
Configuration dataclasses for download clients.

These dataclasses provide a clean, typed interface for client configuration
that separates config parsing from client instantiation.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class ClientConfig:
    """Base configuration for all download clients.
    
    This dataclass represents the common configuration fields shared by
    all download client types. Client-specific fields are handled via
    the extra_config dict.
    
    Attributes:
        name: Unique identifier for this client instance
        client_type: Type of client (e.g., "deluge", "qbittorrent")
        host: Server hostname or IP address
        port: Server port number
        password: Password for authentication
        username: Username for authentication (optional)
        extra_config: Additional client-specific configuration
    """
    name: str
    client_type: str  # Named client_type to avoid shadowing built-in 'type'
    host: str
    port: int
    password: str
    username: Optional[str] = None
    extra_config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, name: str, config: Dict[str, Any]) -> "ClientConfig":
        """Create a ClientConfig from a config dictionary.
        
        Args:
            name: Client name (usually from config dict key)
            config: Configuration dict (may contain 'type', 'name', and other fields)
            
        Returns:
            ClientConfig instance
            
        Example:
            config = {"type": "deluge", "host": "localhost", "port": 8112, ...}
            client_config = ClientConfig.from_dict("my-client", config)
        """
        # Extract known fields
        client_type = config.get("type", "deluge")
        host = config.get("host", "localhost")
        port = config.get("port", 8112)
        password = config.get("password", "")
        username = config.get("username")
        
        # Collect extra fields (client-specific like connection_type)
        known_fields = {"type", "name", "host", "port", "password", "username"}
        extra_config = {k: v for k, v in config.items() if k not in known_fields}
        
        return cls(
            name=name,
            client_type=client_type,
            host=host,
            port=port,
            password=password,
            username=username,
            extra_config=extra_config,
        )
    
    def to_storage_dict(self) -> Dict[str, Any]:
        """Convert to dict for config file storage.
        
        Returns a dict suitable for storing in config.json.
        Note: 'name' is NOT included as it's used as the dict key.
        
        Returns:
            Dict with type, host, port, password, username, and extra fields
        """
        result = {
            "type": self.client_type,
            "host": self.host,
            "port": self.port,
            "password": self.password,
        }
        if self.username is not None:
            result["username"] = self.username
        # Merge extra config (client-specific fields like connection_type)
        result.update(self.extra_config)
        return result
    
    def get_extra(self, key: str, default: Any = None) -> Any:
        """Get a client-specific configuration value.
        
        Args:
            key: Configuration key (e.g., "connection_type")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.extra_config.get(key, default)
