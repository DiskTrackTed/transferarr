"""
API routes for BitTorrent tracker settings.

These endpoints allow viewing and updating tracker configuration,
with optional live application of changes that require a tracker restart.
"""
import json

from flask import request, current_app

from transferarr.services.tracker import get_tracker_config, create_tracker_from_config
from transferarr.services.torrent_transfer import TorrentTransferHandler
from transferarr.web.routes.api.responses import success_response, error_response


def register_routes(api_bp):
    """Register tracker API routes on the given blueprint."""

    @api_bp.route('/tracker/settings', methods=['GET'])
    def get_tracker_settings():
        """Get current tracker settings and runtime status.
        ---
        tags:
          - Tracker
        responses:
          200:
            description: Tracker settings and status
            schema:
              type: object
              properties:
                data:
                  type: object
                  properties:
                    config:
                      type: object
                      properties:
                        enabled:
                          type: boolean
                        port:
                          type: integer
                        external_url:
                          type: string
                        announce_interval:
                          type: integer
                        peer_expiry:
                          type: integer
                    status:
                      type: object
                      properties:
                        running:
                          type: boolean
                        port:
                          type: integer
                        active_transfers:
                          type: integer
        """
        config = current_app.config['APP_CONFIG']
        tracker_cfg = get_tracker_config(config)

        # Get runtime status from the tracker instance
        torrent_manager = current_app.config.get('TORRENT_MANAGER')
        status = None
        if torrent_manager and torrent_manager.tracker:
            status = torrent_manager.tracker.get_status()
        else:
            status = {
                "enabled": tracker_cfg["enabled"],
                "running": False,
                "port": tracker_cfg["port"],
                "active_transfers": 0
            }

        return success_response({
            'config': tracker_cfg,
            'status': status
        })

    @api_bp.route('/tracker/settings', methods=['PUT'])
    def update_tracker_settings():
        """Update tracker settings with optional live application.

        When 'apply' is true, settings that require a tracker restart (port, enabled)
        will trigger a stop/start cycle. Settings that can be applied live
        (announce_interval, peer_expiry) are always updated on the running tracker.
        ---
        tags:
          - Tracker
        parameters:
          - in: body
            name: body
            required: true
            schema:
              type: object
              properties:
                enabled:
                  type: boolean
                  description: Enable or disable the tracker
                port:
                  type: integer
                  description: Tracker listen port
                external_url:
                  type: string
                  description: URL clients use to reach the tracker
                announce_interval:
                  type: integer
                  description: Seconds between peer announces
                peer_expiry:
                  type: integer
                  description: Seconds before a peer is considered expired
                apply:
                  type: boolean
                  description: If true, apply changes that require a tracker restart
        responses:
          200:
            description: Settings updated successfully
          400:
            description: Invalid request
          500:
            description: Failed to apply settings
        """
        data = request.get_json()
        if not data:
            return error_response('BAD_REQUEST', 'Request body required', status_code=400)

        config = current_app.config['APP_CONFIG']
        updates = {}

        if 'enabled' in data:
            updates['enabled'] = bool(data['enabled'])

        if 'port' in data:
            try:
                port = int(data['port'])
                if port < 1 or port > 65535:
                    return error_response('BAD_REQUEST', 'Port must be between 1 and 65535', status_code=400)
                updates['port'] = port
            except (ValueError, TypeError):
                return error_response('BAD_REQUEST', 'Invalid port value', status_code=400)

        if 'external_url' in data:
            url = data['external_url']
            if url is not None:
                url = str(url).strip()
                if url and not url.startswith(('http://', 'https://')):
                    return error_response('BAD_REQUEST', 'External URL must start with http:// or https://', status_code=400)
            updates['external_url'] = url if url else None

        if 'announce_interval' in data:
            try:
                interval = int(data['announce_interval'])
                if interval < 10:
                    return error_response('BAD_REQUEST', 'Announce interval must be at least 10 seconds', status_code=400)
                updates['announce_interval'] = interval
            except (ValueError, TypeError):
                return error_response('BAD_REQUEST', 'Invalid announce interval value', status_code=400)

        if 'peer_expiry' in data:
            try:
                expiry = int(data['peer_expiry'])
                if expiry < 30:
                    return error_response('BAD_REQUEST', 'Peer expiry must be at least 30 seconds', status_code=400)
                updates['peer_expiry'] = expiry
            except (ValueError, TypeError):
                return error_response('BAD_REQUEST', 'Invalid peer expiry value', status_code=400)

        if updates:
            _save_tracker_config(config, updates)

        # Apply live-updatable settings to running tracker
        torrent_manager = current_app.config.get('TORRENT_MANAGER')
        if torrent_manager and torrent_manager.tracker:
            if 'announce_interval' in updates:
                torrent_manager.tracker.announce_interval = updates['announce_interval']
                from transferarr.services.tracker import TrackerRequestHandler
                TrackerRequestHandler.announce_interval = updates['announce_interval']
            if 'peer_expiry' in updates:
                torrent_manager.tracker.state.peer_expiry = updates['peer_expiry']

        # If apply is requested, stop/start the tracker as needed
        should_apply = data.get('apply', False)
        status = None

        if should_apply and torrent_manager:
            try:
                tracker_cfg = get_tracker_config(config)

                # Stop existing tracker
                if torrent_manager.tracker:
                    torrent_manager.tracker.stop()
                    torrent_manager.tracker = None
                    torrent_manager.torrent_transfer_handler = None

                # Start new tracker if enabled
                if tracker_cfg['enabled']:
                    torrent_manager.tracker = create_tracker_from_config(config)
                    if torrent_manager.tracker:
                        torrent_manager.tracker.start()
                        torrent_manager.torrent_transfer_handler = TorrentTransferHandler(
                            tracker=torrent_manager.tracker,
                            history_service=torrent_manager.history_service,
                            history_config=torrent_manager.history_config
                        )

                # Get updated status
                if torrent_manager.tracker:
                    status = torrent_manager.tracker.get_status()
                else:
                    status = {
                        "enabled": tracker_cfg["enabled"],
                        "running": False,
                        "port": tracker_cfg["port"],
                        "active_transfers": 0
                    }
            except Exception as e:
                return error_response('SERVER_ERROR', f'Settings saved but failed to apply: {str(e)}', status_code=500)
        elif torrent_manager and torrent_manager.tracker:
            status = torrent_manager.tracker.get_status()

        response_data = {'message': 'Tracker settings updated'}
        if status:
            response_data['status'] = status
        if should_apply:
            response_data['applied'] = True

        return success_response(response_data)


def _save_tracker_config(config, updates):
    """Save tracker configuration to config.json.

    Args:
        config: The current config dict (will be updated in-place)
        updates: Dict with tracker settings to save
    """
    if "tracker" not in config:
        config["tracker"] = {}
    config["tracker"].update(updates)

    config_path = config.get("_config_path")
    if config_path:
        with open(config_path, "w") as f:
            save_config = {k: v for k, v in config.items() if not k.startswith("_")}
            json.dump(save_config, f, indent=4)
