"""
Utility routes for file browsing and other helpers.
"""
from flask import request
from transferarr.utils import connection_modal_browse
from .responses import success_response, validation_error_response, server_error_response
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register utility routes with the given blueprint."""
    
    @bp.route("/browse", methods=["POST"])
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
                data:
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
                return validation_error_response("Invalid request data")
            
            # Validate required fields
            if "type" not in data:
                return validation_error_response("Missing required field: type", {"field": "type"})
            
            if data["type"] == "sftp":
                if "config" not in data:
                    return validation_error_response("Missing required field: config", {"field": "config"})
            
            path = data.get("path", "/")
            connection_type = data.get("type", "local")
            connection_config = data.get("config", {})

            # connection_modal_browse returns Flask Response objects (jsonify)
            # We need to extract the data and wrap it in our envelope
            result = connection_modal_browse(path, connection_type, connection_config)
            
            # Handle tuple (response, status_code) for errors
            if isinstance(result, tuple):
                response_obj, status_code = result
                response_data = response_obj.get_json()
                if status_code >= 400:
                    error_msg = response_data.get("error", "Unknown error")
                    if status_code == 404:
                        from .responses import not_found_response
                        return not_found_response(error_msg)
                    return validation_error_response(error_msg)
                return success_response(response_data)
            
            # Single Response object - success case
            return success_response(result.get_json())
                
        except Exception as e:
            logger.error(f"Error in browse_directory: {e}")
            return server_error_response(f"Server error: {str(e)}")
