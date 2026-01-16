"""
Download client routes for CRUD operations.
"""
from flask import current_app, request
from transferarr.web.schemas import DownloadClientSchema, DownloadClientUpdateSchema, DownloadClientTestSchema
from transferarr.web.services import (
    DownloadClientService, NotFoundError, ConflictError, ValidationError, ConfigSaveError
)
from .responses import (
    success_response, created_response, not_found_response,
    error_response, validation_error_response, server_error_response
)
from .validation import validate_json
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register download client routes with the given blueprint."""
    
    @bp.route("/download_clients", methods=["GET"])
    def get_download_clients():
        """Get all configured download clients.
        ---
        tags:
          - Download Clients
        responses:
          200:
            description: Dictionary of download clients wrapped in data envelope
            schema:
              type: object
              properties:
                data:
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
                        example: "***"
                      connection_type:
                        type: string
                        enum: [rpc, web]
                        description: Connection method (RPC or Web UI)
          500:
            description: Server error
        """
        try:
            service = DownloadClientService(current_app.config['TORRENT_MANAGER'])
            return success_response(service.list_clients())
        except Exception as e:
            logger.error(f"Error getting download clients: {e}")
            return server_error_response(str(e))

    @bp.route("/download_clients", methods=["POST"])
    @validate_json(DownloadClientSchema)
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
          201:
            description: Client added successfully
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    name:
                      type: string
                message:
                  type: string
          400:
            description: Invalid client data
          409:
            description: Client with this name already exists
          500:
            description: Server error
        """
        service = DownloadClientService(current_app.config['TORRENT_MANAGER'])
        data = dict(request.validated_data)
        name = data.pop("name")
        
        try:
            result = service.add_client(name, data)
            return created_response(result, f"Client '{name}' added successfully")
        except ConflictError:
            return error_response("DUPLICATE_CLIENT", f"Client '{name}' already exists", status_code=409)
        except ValidationError as e:
            return validation_error_response(str(e))
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error adding download client: {e}")
            return server_error_response(str(e))

    @bp.route("/download_clients/<name>", methods=["PUT"])
    @validate_json(DownloadClientUpdateSchema)
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
                  description: Leave blank to keep existing password
                connection_type:
                  type: string
                  enum: [rpc, web]
        responses:
          200:
            description: Client updated successfully
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    name:
                      type: string
                message:
                  type: string
          400:
            description: Invalid client data
          404:
            description: Client not found
          500:
            description: Server error
        """
        service = DownloadClientService(current_app.config['TORRENT_MANAGER'])
        
        try:
            result = service.update_client(name, dict(request.validated_data))
            return success_response(result, f"Client '{name}' updated successfully")
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error updating download client: {e}")
            return server_error_response(str(e))

    @bp.route("/download_clients/<name>", methods=["DELETE"])
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
            schema:
              type: object
              properties:
                data:
                  type: "null"
                message:
                  type: string
          404:
            description: Client not found
          409:
            description: Client is used in connections and cannot be deleted
          500:
            description: Server error
        """
        service = DownloadClientService(current_app.config['TORRENT_MANAGER'])
        
        try:
            service.delete_client(name)
            return success_response(None, f"Client '{name}' deleted successfully")
        except NotFoundError as e:
            return not_found_response(e.resource_type, e.identifier)
        except ConflictError as e:
            return error_response("CLIENT_IN_USE", str(e), status_code=409)
        except ConfigSaveError as e:
            return server_error_response(str(e))
        except Exception as e:
            logger.error(f"Error deleting download client: {e}")
            return server_error_response(str(e))

    @bp.route("/download_clients/test", methods=["POST"])
    @validate_json(DownloadClientTestSchema)
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
                - connection_type
              properties:
                name:
                  type: string
                  description: Client name (for edit mode - uses stored password if password not provided)
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
                  description: Required for new clients. Optional for existing clients (uses stored password if empty)
                connection_type:
                  type: string
                  enum: [rpc, web]
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
            description: Invalid client data
          500:
            description: Server error
        """
        service = DownloadClientService(current_app.config['TORRENT_MANAGER'])
        data = request.validated_data
        
        try:
            result = service.test_connection(data, existing_name=data.get("name"))
            return success_response(
                {"success": result.get("success", False)},
                result.get("message", "Connection test completed")
            )
        except ValidationError as e:
            return validation_error_response(str(e))
        except Exception as e:
            logger.error(f"Error testing download client: {e}")
            return success_response({"success": False}, str(e))
