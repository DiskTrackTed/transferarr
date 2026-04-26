"""
Torrent routes for listing and status information.
"""
from flask import current_app
from transferarr.web.services import TorrentService
from .responses import success_response, server_error_response, error_response
import logging

logger = logging.getLogger("transferarr")


def register_routes(bp):
    """Register torrent routes with the given blueprint."""
    
    def _find_torrent_by_hash(torrent_hash: str):
        """Find a torrent by hash (case-insensitive)."""
        torrent_manager = current_app.config['TORRENT_MANAGER']
        hash_lower = torrent_hash.lower()
        for t in torrent_manager.torrents:
            if t.id and t.id.lower() == hash_lower:
                return t
        return None

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

    @bp.route("/torrents/<torrent_hash>/retry", methods=["POST"])
    def retry_transfer(torrent_hash):
        """Retry a failed transfer.
        ---
        tags:
          - Torrents
        parameters:
          - in: path
            name: torrent_hash
            type: string
            required: true
            description: Hash of the torrent to retry
        responses:
          200:
            description: Transfer retry initiated
          400:
            description: Torrent is not in TRANSFER_FAILED state
          404:
            description: Torrent not found
        """
        torrent_manager = current_app.config['TORRENT_MANAGER']
        torrent = _find_torrent_by_hash(torrent_hash)
        
        if not torrent:
            return error_response("NOT_FOUND", "Torrent not found", status_code=404)

        result, state_name = torrent_manager.retry_tracked_torrent_if_failed(torrent)

        if result == "not_found":
          return error_response("NOT_FOUND", "Torrent not found", status_code=404)

        if result == "invalid_state":
            return error_response(
                "INVALID_STATE",
            f"Cannot retry: torrent is in {state_name} state, not TRANSFER_FAILED"
            )

        logger.info(f"User initiated retry for {torrent.name}")
        return success_response({
            "message": f"Transfer retry initiated for {torrent.name}",
          "new_state": state_name
        })

    @bp.route("/torrents/<torrent_hash>", methods=["DELETE"])
    def remove_torrent(torrent_hash):
        """Remove a failed torrent from tracking.
        ---
        tags:
          - Torrents
        parameters:
          - in: path
            name: torrent_hash
            type: string
            required: true
            description: Hash of the torrent to remove
        responses:
          200:
            description: Torrent removed from tracking
          400:
            description: Torrent is not in TRANSFER_FAILED state
          404:
            description: Torrent not found
        """
        torrent = _find_torrent_by_hash(torrent_hash)
        
        if not torrent:
            return error_response("NOT_FOUND", "Torrent not found", status_code=404)

        torrent_manager = current_app.config['TORRENT_MANAGER']
        result, state_name = torrent_manager.remove_tracked_torrent_if_failed(torrent)

        if result == "not_found":
          return error_response("NOT_FOUND", "Torrent not found", status_code=404)

        if result == "invalid_state":
            return error_response(
                "INVALID_STATE",
            f"Cannot remove: torrent is in {state_name} state, not TRANSFER_FAILED"
            )

        torrent_name = torrent.name
        
        logger.info(f"User removed failed transfer: {torrent_name}")
        return success_response({
            "message": f"Torrent '{torrent_name}' removed from tracking"
        })
