from flask import Blueprint, jsonify, current_app, request
from transferarr.clients.deluge import DelugeClient
from transferarr.services.transfer_connection import TransferConnection
from transferarr.utils import connection_modal_browse
import logging

logger = logging.getLogger("transferarr")
api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route("/health")
def health_check():
    """Health check endpoint for Docker/monitoring.
    ---
    tags:
      - System
    responses:
      200:
        description: Service is healthy
        schema:
          type: object
          properties:
            status:
              type: string
              example: healthy
            torrent_manager:
              type: boolean
              example: true
            version:
              type: string
              example: "1.0.0"
      500:
        description: Service is unhealthy
    """
    try:
        torrent_manager = current_app.config.get('TORRENT_MANAGER')
        return jsonify({
            "status": "healthy",
            "torrent_manager": torrent_manager is not None,
            "version": "1.0.0"
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@api_bp.route("/config")
def get_config():
    """Get the current configuration (sanitized).
    ---
    tags:
      - System
    responses:
      200:
        description: Current configuration
        schema:
          type: object
          properties:
            download_clients:
              type: object
              description: Configured download clients
    """
    # Return a sanitized version of the config (without sensitive information if needed)
    torrent_manager = current_app.config['TORRENT_MANAGER']
    safe_config = {
        "download_clients": torrent_manager.config.get("download_clients", {})
    }
    return jsonify(safe_config)

@api_bp.route("/download_clients", methods=["GET"])
def get_download_clients():
    """Get all configured download clients.
    ---
    tags:
      - Download Clients
    responses:
      200:
        description: Dictionary of download clients
        schema:
          type: object
          additionalProperties:
            type: object
            properties:
              name:
                type: string
              type:
                type: string
                example: deluge
              host:
                type: string
              port:
                type: integer
              username:
                type: string
              password:
                type: string
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        download_clients_data = {}
        
        for client_name, client in torrent_manager.download_clients.items():
            download_clients_data[client_name] = {
                "name": client.name,
                "type": client.type,
                "host": client.host,
                "port": client.port,
                "username": client.username,
                "password": client.password
            }
        
        return jsonify(download_clients_data)
    except Exception as e:
        logger.error(f"Error getting download clients: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/download_clients", methods=["POST"])
def add_download_client():
    """Add a new download client.
    ---
    tags:
      - Download Clients
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - name
            - type
            - host
            - port
            - password
            - connection_type
          properties:
            name:
              type: string
              description: Unique name for the client
            type:
              type: string
              enum: [deluge]
              description: Client type
            host:
              type: string
              description: Hostname or IP address
            port:
              type: integer
              description: Port number (58846 for RPC, 8112 for Web)
            username:
              type: string
              description: Username (optional, RPC only)
            password:
              type: string
              description: Password
            connection_type:
              type: string
              enum: [rpc, web]
              description: Connection method
    responses:
      200:
        description: Client added successfully
      400:
        description: Invalid client data
      409:
        description: Client with this name already exists
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        client_data = request.json
        if not client_data or "name" not in client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "password", "connection_type"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        name = client_data.pop("name")
        
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # If download_clients doesn't exist, create it
        if "download_clients" not in updated_config:
            updated_config["download_clients"] = {}
        
        # Check if client with this name already exists
        if name in updated_config["download_clients"]:
            return jsonify({"error": f"Client with name '{name}' already exists"}), 409
        
        # Add the new client
        updated_config["download_clients"][name] = client_data
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Initialize the new client
            if client_data["type"] == "deluge":
                torrent_manager.download_clients[name] = DelugeClient(
                    name,
                    client_data["host"],
                    client_data["port"],
                    username=client_data.get("username", None),
                    password=client_data["password"],
                    connection_type=client_data.get("connection_type", "rpc")
                )
            
            return jsonify({"success": True, "message": f"Client '{name}' added successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error adding download client: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/download_clients/<name>", methods=["PUT"])
def edit_download_client(name):
    """Update an existing download client.
    ---
    tags:
      - Download Clients
    parameters:
      - in: path
        name: name
        type: string
        required: true
        description: Name of the client to update
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - type
            - host
            - port
            - password
            - connection_type
          properties:
            type:
              type: string
              enum: [deluge]
            host:
              type: string
            port:
              type: integer
            username:
              type: string
            password:
              type: string
            connection_type:
              type: string
              enum: [rpc, web]
    responses:
      200:
        description: Client updated successfully
      400:
        description: Invalid client data
      404:
        description: Client not found
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        client_data = request.json
        if not client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "password", "connection_type"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # Check if client exists
        if name not in updated_config.get("download_clients", {}):
            return jsonify({"error": f"Client with name '{name}' not found"}), 404
        
        # Update the client
        updated_config["download_clients"][name] = client_data
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Re-initialize the client
            if client_data["type"] == "deluge":
                # If client is already in connections, we need to stop and rebuild those connections
                existing_client = torrent_manager.download_clients.get(name)
                if existing_client:
                    # Remove client from connections
                    for connection in torrent_manager.connections[:]:
                        if connection.from_client.name == name or connection.to_client.name == name:
                            torrent_manager.connections.remove(connection)
                
                # Create new client
                torrent_manager.download_clients[name] = DelugeClient(
                    name,
                    client_data["host"],
                    client_data["port"],
                    username=client_data.get("username", None),
                    password=client_data["password"],
                    connection_type=client_data.get("connection_type", "rpc")
                )
            
            return jsonify({"success": True, "message": f"Client '{name}' updated successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error updating download client: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/download_clients/<name>", methods=["DELETE"])
def delete_download_client(name):
    """Delete a download client.
    ---
    tags:
      - Download Clients
    parameters:
      - in: path
        name: name
        type: string
        required: true
        description: Name of the client to delete
    responses:
      200:
        description: Client deleted successfully
      404:
        description: Client not found
      409:
        description: Client is used in connections and cannot be deleted
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # Check if client exists
        if name not in updated_config.get("download_clients", {}):
            return jsonify({"error": f"Client with name '{name}' not found"}), 404
        
        # Check if client is used in any connections
        for connection in torrent_manager.config.get("connections", []):
            if connection["from"] == name or connection["to"] == name:
                return jsonify({"error": f"Client '{name}' is used in connections and cannot be deleted"}), 409
        
        # Delete the client
        del updated_config["download_clients"][name]
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Remove the client from download_clients
            if name in torrent_manager.download_clients:
                del torrent_manager.download_clients[name]
            
            return jsonify({"success": True, "message": f"Client '{name}' deleted successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting download client: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/download_clients/test", methods=["POST"])
def test_download_client():
    """Test a download client connection.
    ---
    tags:
      - Download Clients
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - type
            - host
            - port
            - password
            - connection_type
          properties:
            type:
              type: string
              enum: [deluge]
            host:
              type: string
            port:
              type: integer
            username:
              type: string
            password:
              type: string
            connection_type:
              type: string
              enum: [rpc, web]
    responses:
      200:
        description: Connection test result
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid client data
      500:
        description: Server error
    """
    try:
        client_data = request.json
        if not client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "password", "connection_type"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Create a temporary client to test connection
        if client_data["type"] == "deluge":
            temp_client = DelugeClient(
                "temp_client",
                client_data["host"],
                client_data["port"],
                username=client_data.get("username", None),
                password=client_data["password"],
                connection_type=client_data.get("connection_type", "rpc")
            )
            
            # Test the connection
            result = temp_client.test_connection()
            
            # Return the result
            return jsonify(result)
        else:
            return jsonify({"error": f"Unsupported client type: {client_data['type']}"}), 400
    
    except Exception as e:
        logger.error(f"Error testing download client: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@api_bp.route("/connections")
def get_connections():
    """Get all configured transfer connections.
    ---
    tags:
      - Connections
    responses:
      200:
        description: List of connections
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: integer
              from:
                type: string
                description: Source client name
              to:
                type: string
                description: Destination client name
              source_dot_torrent_path:
                type: string
              source_torrent_download_path:
                type: string
              destination_dot_torrent_tmp_dir:
                type: string
              destination_torrent_download_path:
                type: string
              transfer_config:
                type: object
              active_transfers:
                type: integer
              max_transfers:
                type: integer
              total_transfers:
                type: integer
              status:
                type: string
    """
    # TODO, put this in connection class?
    torrent_manager = current_app.config['TORRENT_MANAGER']
    connections_data = []
    for idx, connection in enumerate(torrent_manager.connections):
        from_client = connection.from_client.name
        to_client = connection.to_client.name
        connection_data = {
            "id": idx,
            "from": from_client,
            "to": to_client,
            "source_dot_torrent_path": connection.source_dot_torrent_path,
            "source_torrent_download_path": connection.source_torrent_download_path,
            "destination_dot_torrent_tmp_dir": connection.destination_dot_torrent_tmp_dir,
            "destination_torrent_download_path": connection.destination_torrent_download_path,
            "transfer_config": connection.transfer_config,
            "active_transfers": connection.get_active_transfers_count(),
            "max_transfers": connection.max_transfers,
            "total_transfers": connection.get_total_transfers_count(),
            "status": "active"  # Assuming connections are always active for now
        }
        connections_data.append(connection_data)
    
    return jsonify(connections_data)

@api_bp.route("/connections", methods=["POST"])
def add_connection():
    """Add a new transfer connection.
    ---
    tags:
      - Connections
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - from
            - to
            - transfer_config
            - source_dot_torrent_path
            - source_torrent_download_path
            - destination_dot_torrent_tmp_dir
            - destination_torrent_download_path
          properties:
            from:
              type: string
              description: Source download client name
            to:
              type: string
              description: Destination download client name
            transfer_config:
              type: object
              description: Transfer method configuration
              properties:
                from:
                  type: object
                  properties:
                    type:
                      type: string
                      enum: [local, sftp]
                    sftp:
                      type: object
                      properties:
                        ssh_config_file:
                          type: string
                        ssh_config_host:
                          type: string
                        host:
                          type: string
                        port:
                          type: integer
                        username:
                          type: string
                        password:
                          type: string
                        private_key:
                          type: string
                to:
                  type: object
                  properties:
                    type:
                      type: string
                      enum: [local, sftp]
                    sftp:
                      type: object
                      properties:
                        ssh_config_file:
                          type: string
                        ssh_config_host:
                          type: string
                        host:
                          type: string
                        port:
                          type: integer
                        username:
                          type: string
                        password:
                          type: string
                        private_key:
                          type: string
            source_dot_torrent_path:
              type: string
              description: Path to .torrent files on source
            source_torrent_download_path:
              type: string
              description: Download path on source
            destination_dot_torrent_tmp_dir:
              type: string
              description: Temp directory for .torrent files on destination
            destination_torrent_download_path:
              type: string
              description: Download path on destination
    responses:
      200:
        description: Connection added successfully
      400:
        description: Invalid connection data
      404:
        description: One or both clients not found
      409:
        description: Connection already exists
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config", 
                          "source_dot_torrent_path", "source_torrent_download_path",
                          "destination_dot_torrent_tmp_dir", "destination_torrent_download_path"]
        
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in torrent_manager.download_clients:
            return jsonify({"error": f"Client '{from_client_name}' not found"}), 404
        
        if to_client_name not in torrent_manager.download_clients:
            return jsonify({"error": f"Client '{to_client_name}' not found"}), 404
        
        # Check if a connection already exists between these clients
        existing_connection = None
        for conn in torrent_manager.connections:
            if conn.from_client.name == from_client_name and conn.to_client.name == to_client_name:
                existing_connection = conn
                break
        
        if existing_connection:
            return jsonify({"error": f"A connection from '{from_client_name}' to '{to_client_name}' already exists"}), 409
        
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # If connections doesn't exist, create it
        if "connections" not in updated_config:
            updated_config["connections"] = []
        
        # Add the new connection
        updated_config["connections"].append(connection_data)
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Create and add the new connection object
            from_client = torrent_manager.download_clients[from_client_name]
            to_client = torrent_manager.download_clients[to_client_name]
            new_connection = TransferConnection(connection_data, from_client, to_client)
            from_client.add_connection(new_connection)
            to_client.add_connection(new_connection)
            torrent_manager.connections.append(new_connection)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{from_client_name}' to '{to_client_name}' added successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error adding connection: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/connections/test", methods=["POST"])
def test_connections():
    """Test a connection between two download clients.
    ---
    tags:
      - Connections
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - from
            - to
            - transfer_config
          properties:
            from:
              type: string
              description: Source client name
            to:
              type: string
              description: Destination client name
            transfer_config:
              type: object
              description: Transfer method configuration
    responses:
      200:
        description: Connection test result
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid connection data
      404:
        description: One or both clients not found
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config"]
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in torrent_manager.download_clients or to_client_name not in torrent_manager.download_clients:
            return jsonify({"error": "One or both clients do not exist"}), 404
        
        # Create a temporary connection for testing
        from_client = torrent_manager.download_clients[from_client_name]
        to_client = torrent_manager.download_clients[to_client_name]
        
        temp_connection = TransferConnection(
            connection_data,
            from_client,
            to_client
        )

        result = temp_connection.test_connection()
        
        # Return the result
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error testing connections: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@api_bp.route("/connections/<int:connection_id>", methods=["PUT"])
def edit_connection(connection_id):
    """Update an existing connection.
    ---
    tags:
      - Connections
    parameters:
      - in: path
        name: connection_id
        type: integer
        required: true
        description: Connection ID
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - from
            - to
            - transfer_config
            - source_dot_torrent_path
            - source_torrent_download_path
            - destination_dot_torrent_tmp_dir
            - destination_torrent_download_path
          properties:
            from:
              type: string
            to:
              type: string
            transfer_config:
              type: object
            source_dot_torrent_path:
              type: string
            source_torrent_download_path:
              type: string
            destination_dot_torrent_tmp_dir:
              type: string
            destination_torrent_download_path:
              type: string
    responses:
      200:
        description: Connection updated successfully
      400:
        description: Invalid connection data
      404:
        description: Connection or client not found
      409:
        description: A different connection with these clients already exists
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        if connection_id < 0 or connection_id >= len(torrent_manager.connections):
            return jsonify({"error": f"Connection with ID {connection_id} not found"}), 404
            
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config", 
                          "source_dot_torrent_path", "source_torrent_download_path",
                          "destination_dot_torrent_tmp_dir", "destination_torrent_download_path"]
        
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in torrent_manager.download_clients:
            return jsonify({"error": f"Client '{from_client_name}' not found"}), 404
        
        if to_client_name not in torrent_manager.download_clients:
            return jsonify({"error": f"Client '{to_client_name}' not found"}), 404
        
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # Check if a different connection already exists between these clients
        for i, conn in enumerate(updated_config.get("connections", [])):
            if i != connection_id and conn["from"] == from_client_name and conn["to"] == to_client_name:
                return jsonify({
                    "error": f"A different connection from '{from_client_name}' to '{to_client_name}' already exists"
                }), 409
        
        # Update the connection
        if connection_id < len(updated_config.get("connections", [])):
            updated_config["connections"][connection_id] = connection_data
        else:
            return jsonify({"error": f"Connection with ID {connection_id} not found in configuration"}), 404
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Remove the old connection
            old_connection = torrent_manager.connections[connection_id]
            from_client = old_connection.from_client
            to_client = old_connection.to_client
            
            # Clean up the old connection
            if hasattr(old_connection, 'shutdown') and callable(getattr(old_connection, 'shutdown')):
                old_connection.shutdown()
            
            # Create a new connection
            from_client = torrent_manager.download_clients[from_client_name]
            to_client = torrent_manager.download_clients[to_client_name]
            new_connection = TransferConnection(connection_data, from_client, to_client)
            
            # Replace the old connection
            torrent_manager.connections[connection_id] = new_connection
            
            # Update client connections
            for client in torrent_manager.download_clients.values():
                client.remove_connection(old_connection)
            
            from_client.add_connection(new_connection)
            to_client.add_connection(new_connection)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{from_client_name}' to '{to_client_name}' updated successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error updating connection: {e}")
        return jsonify({"error": str(e)}), 500
    
@api_bp.route("/connections/<int:connection_id>", methods=["DELETE"])
def delete_connection(connection_id):
    """Delete an existing connection.
    ---
    tags:
      - Connections
    parameters:
      - in: path
        name: connection_id
        type: integer
        required: true
        description: Connection ID
    responses:
      200:
        description: Connection deleted successfully
      404:
        description: Connection not found
      500:
        description: Server error
    """
    try:
        torrent_manager = current_app.config['TORRENT_MANAGER']
        if connection_id < 0 or connection_id >= len(torrent_manager.connections):
            return jsonify({"error": f"Connection with ID {connection_id} not found"}), 404
            
        # Create a copy of the config to modify
        updated_config = dict(torrent_manager.config)
        
        # Check if the connection exists in the configuration
        if connection_id >= len(updated_config.get("connections", [])):
            return jsonify({"error": f"Connection with ID {connection_id} not found in configuration"}), 404
        
        # Remove the connection from the configuration
        removed_connection_config = updated_config["connections"].pop(connection_id)
        
        # Save the updated config
        if torrent_manager.save_config(updated_config):
            # Update the global config
            torrent_manager.config.update(updated_config)
            
            # Remove the connection from the connections list
            old_connection = torrent_manager.connections[connection_id]
            
            # Clean up the old connection
            if hasattr(old_connection, 'shutdown') and callable(getattr(old_connection, 'shutdown')):
                old_connection.shutdown()
            
            # Remove connection from clients
            from_client = old_connection.from_client
            to_client = old_connection.to_client
            from_client.remove_connection(old_connection)
            to_client.remove_connection(old_connection)
            
            # Remove from connections list
            torrent_manager.connections.pop(connection_id)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{removed_connection_config['from']}' to '{removed_connection_config['to']}' deleted successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting connection: {e}")
        return jsonify({"error": str(e)}), 500

@api_bp.route("/torrents")
def get_torrents():
    """Get all tracked torrents and their states.
    ---
    tags:
      - Torrents
    responses:
      200:
        description: List of tracked torrents
        schema:
          type: array
          items:
            type: object
            properties:
              name:
                type: string
              id:
                type: string
                description: Torrent hash (lowercase)
              state:
                type: string
                description: Current torrent state (e.g., HOME_SEEDING, COPYING, TARGET_SEEDING)
              home_client_name:
                type: string
                description: Name of the source download client
              home_client_info:
                type: object
                description: Info from source client (progress, size, etc.)
              target_client_name:
                type: string
                description: Name of the destination download client
              target_client_info:
                type: object
                description: Info from destination client
              progress:
                type: number
                description: Download/transfer progress (0-100)
              size:
                type: integer
                description: Total size in bytes
              transfer_speed:
                type: number
                description: Current transfer speed in bytes/sec
              current_file:
                type: string
                description: Currently transferring file name
              current_file_count:
                type: integer
                description: Number of files transferred
              total_files:
                type: integer
                description: Total number of files to transfer
    """
    torrent_manager = current_app.config['TORRENT_MANAGER']
    return jsonify([torrent.to_dict() for torrent in torrent_manager.torrents])

@api_bp.route("/all_torrents")
def get_all_torrents():
    """Get all torrents from all connected download clients.
    ---
    tags:
      - Torrents
    responses:
      200:
        description: Dictionary of torrents by client
        schema:
          type: object
          additionalProperties:
            type: object
            description: Torrents from this client (keyed by torrent hash)
    """
    all_torrents = {}
    
    torrent_manager = current_app.config['TORRENT_MANAGER']

    for client_name, client in torrent_manager.download_clients.items():
        try:
            if isinstance(client, DelugeClient):
                # Handle disconnected clients gracefully
                if not client.is_connected():
                    logger.warning(f"Client {client_name} is not connected, skipping")
                    all_torrents[client_name] = {}
                    continue
                
                # Get safely decoded torrent data using client method
                processed_torrents = client.get_all_torrents_status()
                
                # If there's an error and we get back an empty dict,
                # at least return a valid response
                if not processed_torrents:
                    all_torrents[client_name] = {}
                    continue
                    
                all_torrents[client_name] = processed_torrents
        except Exception as e:
            # Log the error but don't crash the endpoint
            logger.error(f"Failed to get torrents from client {client_name}: {e}")
            all_torrents[client_name] = {}
    
    # Return whatever data we were able to collect
    return jsonify(all_torrents)

@api_bp.route("/browse", methods=["POST"])
def browse_directory():
    """Browse directories on local or remote (SFTP) filesystem.
    ---
    tags:
      - Utilities
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - type
          properties:
            type:
              type: string
              enum: [local, sftp]
              description: Connection type
            path:
              type: string
              description: Directory path to browse (default "/")
            config:
              type: object
              description: SFTP configuration (required if type is sftp)
              properties:
                ssh_config_file:
                  type: string
                ssh_config_host:
                  type: string
                host:
                  type: string
                port:
                  type: integer
                username:
                  type: string
                password:
                  type: string
                private_key:
                  type: string
    responses:
      200:
        description: Directory listing
        schema:
          type: object
          properties:
            entries:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                  path:
                    type: string
                  is_dir:
                    type: boolean
      400:
        description: Invalid request data
      500:
        description: Server error
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Validate required fields
        if "type" not in data:
            return jsonify({"error": "Missing required field: type"}), 400
        
        if data["type"] == "sftp":
            if "config" not in data:
                return jsonify({"error": "Missing required field: config"}), 400
        
        path = data.get("path", "/")
        connection_type = data.get("type", "local")
        connection_config = data.get("config", {})

        return connection_modal_browse(path, connection_type, connection_config)
            
    except Exception as e:
        logger.error(f"Error in browse_directory: {e}")
        return jsonify({
            "error": f"Server error: {str(e)}",
            "entries": []
        }), 500