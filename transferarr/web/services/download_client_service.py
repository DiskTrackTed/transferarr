"""
Service for download client CRUD operations.
"""
from transferarr.clients.registry import ClientRegistry
from transferarr.clients.download_client import DownloadClientBase
from transferarr.clients.config import ClientConfig
from . import NotFoundError, ConflictError, ValidationError, ConfigSaveError


class DownloadClientService:
    """Service for managing download clients."""
    
    def __init__(self, torrent_manager):
        self.torrent_manager = torrent_manager
    
    def _serialize_client(self, client: DownloadClientBase) -> dict:
        """Serialize a client to dict with masked password."""
        result = {
            "name": client.name,
            "type": client.type,
            "host": client.host,
            "port": client.port,
            "username": client.username,
            "password": "***",
        }
        # Include connection_type if the client has it (Deluge-specific)
        if hasattr(client, 'connection_type'):
            result["connection_type"] = client.connection_type
        return result
    
    def _create_client_config(self, name: str, data: dict) -> ClientConfig:
        """Create a ClientConfig from API data.
        
        Args:
            name: Client name
            data: API request data (may contain 'name' and 'type')
            
        Returns:
            ClientConfig instance
        """
        return ClientConfig.from_dict(name, data)
    
    def _create_client_instance(self, name: str, data: dict) -> DownloadClientBase:
        """Create a client instance from API data.
        
        Args:
            name: Client name
            data: API request data
            
        Returns:
            DownloadClientBase instance
        """
        config = self._create_client_config(name, data)
        return ClientRegistry.create(config)
    
    def list_clients(self) -> dict:
        """Get all download clients with masked passwords."""
        return {
            name: self._serialize_client(client)
            for name, client in self.torrent_manager.download_clients.items()
        }
    
    def get_client(self, name: str) -> dict:
        """Get a single client by name (with masked password).
        
        Raises:
            NotFoundError: Client not found
        """
        if name not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", name)
        return self._serialize_client(self.torrent_manager.download_clients[name])
    
    def add_client(self, name: str, client_data: dict) -> dict:
        """Add a new download client.
        
        Args:
            name: Client name
            client_data: Dict with type, host, port, username, password, connection_type
            
        Returns:
            Created client info with masked password
            
        Raises:
            ConflictError: Client with name already exists
            ValidationError: Unsupported client type
            ConfigSaveError: Failed to save config
        """
        if name in self.torrent_manager.download_clients:
            raise ConflictError(f"Client with name '{name}' already exists")
        
        client_type = client_data.get("type", "deluge")
        if not ClientRegistry.is_supported(client_type):
            supported = ", ".join(ClientRegistry.get_supported_types())
            raise ValidationError(f"Unsupported client type: {client_type}. Supported: {supported}")
        
        # Update config
        updated_config = dict(self.torrent_manager.config)
        if "download_clients" not in updated_config:
            updated_config["download_clients"] = {}
        updated_config["download_clients"][name] = client_data
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        # Update runtime state
        self.torrent_manager.config.update(updated_config)
        self.torrent_manager.download_clients[name] = self._create_client_instance(name, client_data)
        
        return {"name": name, **client_data, "password": "***"}
    
    def update_client(self, name: str, client_data: dict) -> dict:
        """Update an existing download client.
        
        Args:
            name: Client name (cannot be changed)
            client_data: Updated client config (password optional - keeps existing if empty)
            
        Returns:
            Updated client info with masked password
            
        Raises:
            NotFoundError: Client not found
            ConfigSaveError: Failed to save config
        """
        updated_config = dict(self.torrent_manager.config)
        
        if name not in updated_config.get("download_clients", {}):
            raise NotFoundError("Client", name)
        
        # Preserve password if not provided
        if not client_data.get("password"):
            client_data["password"] = updated_config["download_clients"][name].get("password", "")
        
        updated_config["download_clients"][name] = client_data
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        self.torrent_manager.config.update(updated_config)
        
        # Find connections that use this client (need to rebuild them)
        connections_to_rebuild = []
        existing_client = self.torrent_manager.download_clients.get(name)
        if existing_client:
            for conn_name, conn in list(self.torrent_manager.connections.items()):
                if conn.from_client.name == name or conn.to_client.name == name:
                    connections_to_rebuild.append(conn_name)
                    # Cleanup old connection
                    if hasattr(conn, 'shutdown') and callable(conn.shutdown):
                        conn.shutdown()
                    conn.from_client.remove_connection(conn)
                    conn.to_client.remove_connection(conn)
                    del self.torrent_manager.connections[conn_name]
        
        # Create new client instance
        self.torrent_manager.download_clients[name] = self._create_client_instance(name, client_data)
        
        # Rebuild connections that used this client
        from transferarr.services.transfer_connection import TransferConnection
        for conn_name in connections_to_rebuild:
            conn_config = updated_config["connections"][conn_name]
            from_client = self.torrent_manager.download_clients[conn_config["from"]]
            to_client = self.torrent_manager.download_clients[conn_config["to"]]
            new_conn = TransferConnection(conn_name, conn_config, from_client, to_client)
            self.torrent_manager.connections[conn_name] = new_conn
            from_client.add_connection(new_conn)
            to_client.add_connection(new_conn)
        
        return {"name": name, **client_data, "password": "***"}
    
    def delete_client(self, name: str) -> None:
        """Delete a download client.
        
        Raises:
            NotFoundError: Client not found
            ConflictError: Client is used in connections
            ConfigSaveError: Failed to save config
        """
        updated_config = dict(self.torrent_manager.config)
        
        if name not in updated_config.get("download_clients", {}):
            raise NotFoundError("Client", name)
        
        # Check if client is used in connections
        for conn_name, connection in self.torrent_manager.config.get("connections", {}).items():
            if connection["from"] == name or connection["to"] == name:
                raise ConflictError(f"Client '{name}' is used in connections and cannot be deleted")
        
        del updated_config["download_clients"][name]
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        self.torrent_manager.config.update(updated_config)
        if name in self.torrent_manager.download_clients:
            del self.torrent_manager.download_clients[name]
    
    def test_connection(self, client_data: dict, existing_name: str = None) -> dict:
        """Test a client connection without saving.
        
        Args:
            client_data: Client config to test
            existing_name: If editing, name of existing client for password lookup
            
        Returns:
            Dict with success (bool) and message (str)
            
        Raises:
            ValidationError: Missing password or unsupported type
        """
        password = client_data.get("password") or ""
        
        # Edit mode: use stored password if not provided
        if not password and existing_name:
            stored_client = self.torrent_manager.config.get("download_clients", {}).get(existing_name)
            if stored_client:
                password = stored_client.get("password", "")
        
        if not password:
            raise ValidationError("Password is required (provide password or existing client name)")
        
        client_type = client_data.get("type", "deluge")
        if not ClientRegistry.is_supported(client_type):
            supported = ", ".join(ClientRegistry.get_supported_types())
            raise ValidationError(f"Unsupported client type: {client_type}. Supported: {supported}")
        
        # Build data dict with resolved password for helper
        test_data = dict(client_data)
        test_data["password"] = password
        temp_client = self._create_client_instance("temp_client", test_data)
        
        return temp_client.test_connection()
