"""
Service for transfer connection CRUD operations.
"""
from transferarr.services.transfer_connection import TransferConnection
from . import NotFoundError, ConflictError, ConfigSaveError
import copy


def _mask_sftp_passwords(transfer_config: dict) -> dict:
    """Deep copy transfer_config and mask any SFTP passwords."""
    safe_config = copy.deepcopy(transfer_config)
    if safe_config.get("from", {}).get("sftp", {}).get("password"):
        safe_config["from"]["sftp"]["password"] = "***"
    if safe_config.get("to", {}).get("sftp", {}).get("password"):
        safe_config["to"]["sftp"]["password"] = "***"
    return safe_config


def _find_connection_by_name(connections: dict, name: str) -> tuple:
    """Case-insensitive connection lookup.
    
    Returns:
        (actual_name, connection) or (None, None) if not found
    """
    for conn_name, conn in connections.items():
        if conn_name.lower() == name.lower():
            return conn_name, conn
    return None, None


class ConnectionService:
    """Service for managing transfer connections."""
    
    def __init__(self, torrent_manager):
        self.torrent_manager = torrent_manager
    
    def list_connections(self) -> list:
        """Get all connections with masked passwords and runtime stats."""
        connections_data = []
        for name, connection in self.torrent_manager.connections.items():
            connections_data.append({
                "name": name,
                "from": connection.from_client.name,
                "to": connection.to_client.name,
                "source_dot_torrent_path": connection.source_dot_torrent_path,
                "source_torrent_download_path": connection.source_torrent_download_path,
                "destination_dot_torrent_tmp_dir": connection.destination_dot_torrent_tmp_dir,
                "destination_torrent_download_path": connection.destination_torrent_download_path,
                "transfer_config": _mask_sftp_passwords(connection.transfer_config),
                "active_transfers": connection.get_active_transfers_count(),
                "max_transfers": connection.max_transfers,
                "total_transfers": connection.get_total_transfers_count(),
                "status": "active"
            })
        return connections_data
    
    def add_connection(self, data: dict) -> dict:
        """Add a new connection.
        
        Args:
            data: Dict containing name, from, to, transfer_config, and path settings
                   
        Returns:
            Created connection summary
            
        Raises:
            ConflictError: Connection name already exists
            NotFoundError: Client not found
            ConfigSaveError: Failed to save config
        """
        name = data["name"].strip()
        from_client = data["from"]
        to_client = data["to"]
        transfer_config = data["transfer_config"]
        
        # Case-insensitive uniqueness check
        existing_names = {n.lower() for n in self.torrent_manager.connections.keys()}
        if name.lower() in existing_names:
            raise ConflictError(f"Connection '{name}' already exists")
        
        # Validate clients exist
        if from_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", from_client)
        if to_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", to_client)
        
        # Build connection config
        connection_config = {
            "from": from_client,
            "to": to_client,
            "transfer_config": transfer_config,
            "source_dot_torrent_path": data["source_dot_torrent_path"],
            "source_torrent_download_path": data["source_torrent_download_path"],
            "destination_dot_torrent_tmp_dir": data["destination_dot_torrent_tmp_dir"],
            "destination_torrent_download_path": data["destination_torrent_download_path"]
        }
        
        # Update config
        updated_config = dict(self.torrent_manager.config)
        if "connections" not in updated_config or not isinstance(updated_config["connections"], dict):
            updated_config["connections"] = {}
        updated_config["connections"][name] = connection_config
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        # Update runtime
        self.torrent_manager.config.update(updated_config)
        from_client_obj = self.torrent_manager.download_clients[from_client]
        to_client_obj = self.torrent_manager.download_clients[to_client]
        new_connection = TransferConnection(name, connection_config, from_client_obj, to_client_obj)
        from_client_obj.add_connection(new_connection)
        to_client_obj.add_connection(new_connection)
        self.torrent_manager.connections[name] = new_connection
        
        return {"name": name, "from": from_client, "to": to_client}
    
    def update_connection(self, name: str, data: dict) -> dict:
        """Update an existing connection.
        
        Args:
            name: Current connection name (case-insensitive lookup)
            data: Dict containing from, to, transfer_config, paths, and optional new name
            
        Returns:
            Updated connection summary
            
        Raises:
            NotFoundError: Connection or client not found
            ConflictError: New name conflicts with existing
            ConfigSaveError: Failed to save config
        """
        actual_name, connection = _find_connection_by_name(self.torrent_manager.connections, name)
        if not connection:
            raise NotFoundError("Connection", name)
        
        from_client = data["from"]
        to_client = data["to"]
        transfer_config = data["transfer_config"]
        new_name = data.get("name")
        
        # Handle renaming
        final_name = new_name.strip() if new_name else actual_name
        if final_name.lower() != actual_name.lower():
            for existing_name in self.torrent_manager.connections.keys():
                if existing_name.lower() == final_name.lower():
                    raise ConflictError(f"Connection '{final_name}' already exists")
        
        # Validate clients
        if from_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", from_client)
        if to_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", to_client)
        
        updated_config = dict(self.torrent_manager.config)
        existing_conn_config = updated_config.get("connections", {}).get(actual_name, {})
        
        # Preserve SFTP passwords if masked/empty
        transfer_config = self._preserve_sftp_passwords(transfer_config, existing_conn_config)
        
        # Build config
        connection_config = {
            "from": from_client,
            "to": to_client,
            "transfer_config": transfer_config,
            "source_dot_torrent_path": data["source_dot_torrent_path"],
            "source_torrent_download_path": data["source_torrent_download_path"],
            "destination_dot_torrent_tmp_dir": data["destination_dot_torrent_tmp_dir"],
            "destination_torrent_download_path": data["destination_torrent_download_path"]
        }
        
        # Handle rename
        if actual_name != final_name:
            del updated_config["connections"][actual_name]
        updated_config["connections"][final_name] = connection_config
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        # Update runtime
        self.torrent_manager.config.update(updated_config)
        self._cleanup_connection(actual_name)
        
        # Create new connection
        from_client_obj = self.torrent_manager.download_clients[from_client]
        to_client_obj = self.torrent_manager.download_clients[to_client]
        new_connection = TransferConnection(final_name, connection_config, from_client_obj, to_client_obj)
        self.torrent_manager.connections[final_name] = new_connection
        from_client_obj.add_connection(new_connection)
        to_client_obj.add_connection(new_connection)
        
        return {"name": final_name, "from": from_client, "to": to_client}
    
    def delete_connection(self, name: str) -> str:
        """Delete a connection.
        
        Returns:
            The actual name that was deleted
            
        Raises:
            NotFoundError: Connection not found
            ConfigSaveError: Failed to save config
        """
        actual_name, connection = _find_connection_by_name(self.torrent_manager.connections, name)
        if not connection:
            raise NotFoundError("Connection", name)
        
        updated_config = dict(self.torrent_manager.config)
        del updated_config["connections"][actual_name]
        
        if not self.torrent_manager.save_config(updated_config):
            raise ConfigSaveError("Failed to save configuration")
        
        self.torrent_manager.config.update(updated_config)
        self._cleanup_connection(actual_name)
        
        return actual_name
    
    def test_connection(self, data: dict) -> dict:
        """Test a connection without saving.
        
        Args:
            data: Dict containing from, to, transfer_config, and optional connection_name
            
        Returns:
            Dict with success (bool) and message (str)
            
        Raises:
            NotFoundError: Client not found
        """
        from_client = data["from"]
        to_client = data["to"]
        transfer_config = data["transfer_config"]
        existing_name = data.get("connection_name")
        
        if from_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", from_client)
        if to_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", to_client)
        
        # Look up stored passwords if editing
        if existing_name:
            actual_name, _ = _find_connection_by_name(self.torrent_manager.connections, existing_name)
            if actual_name:
                stored_config = self.torrent_manager.config.get("connections", {}).get(actual_name, {})
                transfer_config = self._preserve_sftp_passwords(transfer_config, stored_config)
        
        from_client_obj = self.torrent_manager.download_clients[from_client]
        to_client_obj = self.torrent_manager.download_clients[to_client]
        
        test_config = {"from": from_client, "to": to_client, "transfer_config": transfer_config}
        temp_connection = TransferConnection("test-connection", test_config, from_client_obj, to_client_obj)
        
        return temp_connection.test_connection()
    
    def _preserve_sftp_passwords(self, transfer_config: dict, existing_config: dict) -> dict:
        """Preserve SFTP passwords if new value is masked or empty."""
        existing_transfer = existing_config.get("transfer_config", {})
        
        for side in ["from", "to"]:
            if transfer_config.get(side, {}).get("sftp"):
                new_password = transfer_config[side]["sftp"].get("password", "")
                if not new_password or new_password == "***":
                    existing_password = existing_transfer.get(side, {}).get("sftp", {}).get("password", "")
                    if existing_password:
                        transfer_config[side]["sftp"]["password"] = existing_password
        
        return transfer_config
    
    def _cleanup_connection(self, name: str) -> None:
        """Remove connection from runtime state."""
        if name not in self.torrent_manager.connections:
            return
        
        connection = self.torrent_manager.connections[name]
        
        if hasattr(connection, 'shutdown') and callable(connection.shutdown):
            connection.shutdown()
        
        connection.from_client.remove_connection(connection)
        connection.to_client.remove_connection(connection)
        del self.torrent_manager.connections[name]
