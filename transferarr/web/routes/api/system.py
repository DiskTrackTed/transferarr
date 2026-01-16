"""
System routes for health checks and configuration.
"""
from flask import current_app
from .responses import success_response, error_response
from transferarr import __version__
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register system routes with the given blueprint."""
    
    @bp.route("/health")
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
                data:
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
                      example: "0.1.0"
          500:
            description: Service is unhealthy
        """
        try:
            torrent_manager = current_app.config.get('TORRENT_MANAGER')
            return success_response({
                "status": "healthy",
                "torrent_manager": torrent_manager is not None,
                "version": __version__
            })
        except Exception as e:
            return error_response("UNHEALTHY", str(e), status_code=500)

    @bp.route("/config")
    def get_config():
        """Get the current configuration (sanitized).
        ---
        tags:
          - System
        responses:
          200:
            description: Current configuration wrapped in data envelope
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    download_clients:
                      type: object
                      description: Configured download clients
        """
        # Return a sanitized version of the config (without sensitive information)
        torrent_manager = current_app.config['TORRENT_MANAGER']
        
        # Deep copy and mask passwords in download_clients
        safe_download_clients = {}
        for name, client_config in torrent_manager.config.get("download_clients", {}).items():
            safe_client = dict(client_config)
            safe_client["password"] = "***"  # Mask password
            safe_download_clients[name] = safe_client
        
        safe_config = {
            "download_clients": safe_download_clients
        }
        return success_response(safe_config)
