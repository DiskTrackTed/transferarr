"""
Connection routes for transfer connection CRUD operations.
"""
from flask import current_app, request
from transferarr.web.services import (
    ConnectionService, NotFoundError, ConflictError, ConfigSaveError
)
from .responses import (
    success_response, created_response, not_found_response,
    error_response, server_error_response
)
from .validation import validate_json
from transferarr.web.schemas import ConnectionSchema, ConnectionUpdateSchema, ConnectionTestSchema
import logging

logger = logging.getLogger("transferarr")


def _convert_marshmallow_keys(data: dict) -> dict:
    """Convert marshmallow's from_ back to from for service layer.
    
    Marshmallow uses from_ because 'from' is a Python reserved word.
    This converts it back for the service/config layer.
    """
    if "from_" in data:
        data["from"] = data.pop("from_")
    if "transfer_config" in data and "from_" in data["transfer_config"]:
        data["transfer_config"]["from"] = data["transfer_config"].pop("from_")
    return data


def register_routes(bp):
    """Register connection routes with the given blueprint."""
    
    @bp.route("/connections")
    def get_connections():
        """Get all configured transfer connections.
        ---
        tags:
          - Connections
        responses:
          200:
            description: List of connections
            schema:
              type: object
              properties:
                data:
                  type: array
                  items:
                    type: object
                    properties:
                      name:
                        type: string
                        description: Unique connection name
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
        try:
            service = ConnectionService(current_app.config['TORRENT_MANAGER'])
            return success_response(service.list_connections())
        except Exception as e:
            logger.error(f"Error getting connections: {e}")
            return server_error_response(str(e))

    @bp.route("/connections", methods=["POST"])
    @validate_json(ConnectionSchema)
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
                - name
                - from
                - to
                - transfer_config
                - source_dot_torrent_path
                - source_torrent_download_path
                - destination_dot_torrent_tmp_dir
                - destination_torrent_download_path
              properties:
                name:
                  type: string
                  description: Unique connection name (cannot contain '/')
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
          201:
            description: Connection added successfully
          400:
            description: Invalid connection data or name contains '/'
          404:
            description: One or both clients not found
          409:
            description: Connection name already exists
          500:
            description: Server error
        """
        service = ConnectionService(current_app.config['TORRENT_MANAGER'])
        
        # Convert marshmallow format (from_ -> from) for service
        data = _convert_marshmallow_keys(dict(request.validated_data))
        
        try:
            result = service.add_connection(data)
            return created_response(result, f"Connection '{data['name']}' added successfully")
        except ConflictError as e:
            return error_response("DUPLICATE_CONNECTION", str(e), status_code=409)
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error adding connection: {e}")
            return server_error_response(str(e))

    @bp.route("/connections/test", methods=["POST"])
    @validate_json(ConnectionTestSchema)
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
                connection_name:
                  type: string
                  description: Optional - existing connection name for stored password lookup when editing
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
                data:
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
        service = ConnectionService(current_app.config['TORRENT_MANAGER'])
        
        # Convert marshmallow format (from_ -> from) for service
        data = _convert_marshmallow_keys(dict(request.validated_data))
        
        try:
            result = service.test_connection(data)
            return success_response(
                {"success": result.get("success", False)},
                result.get("message", "Connection test completed")
            )
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except Exception as e:
            logger.error(f"Error testing connections: {e}")
            return server_error_response(str(e))

    @bp.route("/connections/<connection_name>", methods=["PUT"])
    @validate_json(ConnectionUpdateSchema)
    def edit_connection(connection_name):
        """Update an existing connection.
        ---
        tags:
          - Connections
        parameters:
          - in: path
            name: connection_name
            type: string
            required: true
            description: Connection name (URL-encoded if contains special characters)
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
                name:
                  type: string
                  description: New connection name (optional, for renaming)
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
            description: Invalid connection data or new name contains '/'
          404:
            description: Connection or client not found
          409:
            description: New connection name already exists
          500:
            description: Server error
        """
        service = ConnectionService(current_app.config['TORRENT_MANAGER'])
        
        # Convert marshmallow format (from_ -> from) for service
        data = _convert_marshmallow_keys(dict(request.validated_data))
        
        try:
            result = service.update_connection(connection_name, data)
            new_name = data.get("name", connection_name)
            return success_response(result, f"Connection '{new_name}' updated successfully")
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except ConflictError as e:
            return error_response("DUPLICATE_CONNECTION", str(e), status_code=409)
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error updating connection: {e}")
            return server_error_response(str(e))
        
    @bp.route("/connections/<connection_name>", methods=["DELETE"])
    def delete_connection(connection_name):
        """Delete an existing connection.
        ---
        tags:
          - Connections
        parameters:
          - in: path
            name: connection_name
            type: string
            required: true
            description: Connection name (URL-encoded if contains special characters)
        responses:
          200:
            description: Connection deleted successfully
          404:
            description: Connection not found
          500:
            description: Server error
        """
        service = ConnectionService(current_app.config['TORRENT_MANAGER'])
        
        try:
            service.delete_connection(connection_name)
            return success_response(None, f"Connection '{connection_name}' deleted successfully")
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error deleting connection: {e}")
            return server_error_response(str(e))
