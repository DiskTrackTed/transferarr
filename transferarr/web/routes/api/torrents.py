"""
Torrent routes for listing and status information.
"""
from flask import current_app
from transferarr.web.services import TorrentService
from .responses import success_response, server_error_response
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register torrent routes with the given blueprint."""
    
    @bp.route("/torrents")
    def get_torrents():
        """Get all tracked torrents and their states.
        ---
        tags:
          - Torrents
        responses:
          200:
            description: List of tracked torrents
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
          500:
            description: Server error
        """
        try:
            service = TorrentService(current_app.config['TORRENT_MANAGER'])
            return success_response(service.list_tracked_torrents())
        except Exception as e:
            logger.error(f"Error getting torrents: {e}")
            return server_error_response(str(e))

    @bp.route("/all_torrents")
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
              properties:
                data:
                  type: object
                  additionalProperties:
                    type: object
                    description: Torrents from this client (keyed by torrent hash)
          500:
            description: Server error
        """
        try:
            service = TorrentService(current_app.config['TORRENT_MANAGER'])
            return success_response(service.get_all_client_torrents())
        except Exception as e:
            logger.error(f"Error getting all torrents: {e}")
            return server_error_response(str(e))
