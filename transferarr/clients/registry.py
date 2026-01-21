"""
Client registry for download client instantiation.

Provides a registry pattern for registering and creating download client
instances by type string.
"""
from typing import Callable, Dict, List, Type, Union

from transferarr.clients.download_client import DownloadClientBase
from transferarr.clients.config import ClientConfig


class ClientRegistry:
    """Registry for download client types.
    
    Allows registration of client classes by type string and provides
    factory methods for creating instances.
    
    Example:
        @ClientRegistry.register("deluge")
        class DelugeClient(DownloadClientBase):
            ...
        
        config = ClientConfig.from_dict("my-client", {"type": "deluge", ...})
        client = ClientRegistry.create(config)
    """
    
    _clients: Dict[str, Type[DownloadClientBase]] = {}
    
    @classmethod
    def register(cls, client_type: str) -> Callable[[Type[DownloadClientBase]], Type[DownloadClientBase]]:
        """Decorator to register a client class.
        
        Args:
            client_type: Type string for this client (e.g., "deluge")
            
        Returns:
            Decorator function
            
        Example:
            @ClientRegistry.register("deluge")
            class DelugeClient(DownloadClientBase):
                ...
        """
        def decorator(client_class: Type[DownloadClientBase]) -> Type[DownloadClientBase]:
            cls._clients[client_type] = client_class
            return client_class
        return decorator
    
    @classmethod
    def create(cls, config: ClientConfig) -> DownloadClientBase:
        """Create a client instance from a ClientConfig.
        
        Args:
            config: ClientConfig instance with all configuration
            
        Returns:
            Instantiated client object
            
        Raises:
            ValueError: If client_type is not registered
        """
        client_type = config.client_type
        if client_type not in cls._clients:
            supported = ", ".join(cls._clients.keys()) or "none"
            raise ValueError(
                f"Unknown client type: '{client_type}'. "
                f"Supported types: {supported}"
            )
        
        client_class = cls._clients[client_type]
        return client_class(config)
    
    @classmethod
    def create_from_dict(cls, name: str, config_dict: Dict) -> DownloadClientBase:
        """Create a client instance from a config dictionary.
        
        Convenience method that creates a ClientConfig and then the client.
        
        Args:
            name: Client name
            config_dict: Configuration dictionary
            
        Returns:
            Instantiated client object
        """
        config = ClientConfig.from_dict(name, config_dict)
        return cls.create(config)
    
    @classmethod
    def get_supported_types(cls) -> List[str]:
        """Get list of supported client types.
        
        Returns:
            List of registered client type strings
        """
        return list(cls._clients.keys())
    
    @classmethod
    def is_supported(cls, client_type: str) -> bool:
        """Check if a client type is supported.
        
        Args:
            client_type: Type string to check
            
        Returns:
            True if supported, False otherwise
        """
        return client_type in cls._clients


# Convenience decorator alias
register_client = ClientRegistry.register
