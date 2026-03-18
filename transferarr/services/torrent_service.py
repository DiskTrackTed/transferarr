# services/torrent_service.py
import logging
import radarr
import json
import os
from threading import Thread
from typing import Optional
from transferarr.clients.base import load_download_clients
from transferarr.services.transfer_connection import TransferConnection
from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.media_managers import RadarrManager, SonarrManager
from transferarr.services.tracker import BitTorrentTracker, create_tracker_from_config
from transferarr.services.torrent_transfer import TorrentTransferHandler
from time import sleep

logger = logging.getLogger("transferarr")

class TorrentManager:
    def __init__(self, config, config_file, state_dir=None, history_service=None, history_config=None):
        self.torrents = []
        self.config = config
        self.config_file = config_file
        self.media_managers = []
        self.download_clients = {}
        self.connections = {}  # Dict keyed by connection name
        # Construct state file path from state_dir
        self.state_dir = state_dir or "/state"
        self.state_file = os.path.join(self.state_dir, "state.json")
        self.history_service = history_service
        self.history_config = history_config or {}
        self.running = False
        
        # Tracker and torrent transfer handler
        self.tracker: Optional[BitTorrentTracker] = None
        self.torrent_transfer_handler: Optional[TorrentTransferHandler] = None
        
        self.setup_media_managers(config)
        self.load_download_clients(config)
        # Migrate connections config if needed (array to dict)
        self._migrate_connections_config()
        self.load_connections(config)
        # Set up tracker if enabled
        self._setup_tracker(config)
        # Load saved torrent state (must be after media_managers and download_clients are loaded)
        self.torrents = self.load_torrents_state()
        # Re-register any pending transfer hashes with tracker (tracker state is in-memory only)
        self._reregister_pending_transfers()

    def setup_media_managers(self, config):
        """Set up the media managers."""
        if "media_managers" not in config:
            logger.warning("No media managers found in configuration.")
            return
        for manager in config["media_managers"]:
            try:
                if manager["type"] == "radarr":
                    radarr_manager = RadarrManager(manager)
                    self.media_managers.append(radarr_manager)
                elif manager["type"] == "sonarr":
                    sonarr_manager = SonarrManager(manager)
                    self.media_managers.append(sonarr_manager)
                else:
                    logger.warning(f"Unknown media manager type: {manager['type']}")
            except Exception as e:
                logger.error(f"Failed to set up media manager {manager['type']}: {e}")

    def load_download_clients(self, config):
        self.download_clients = load_download_clients(config)

    def load_connections(self, config):
        """Load the connections from the configuration."""
        connections_config = config.get("connections", {})
        if not isinstance(connections_config, dict):
            logger.warning("Connections config is not a dict - migration may have failed")
            return
        
        for name, connection in connections_config.items():
            try:
                from_client = self.download_clients[connection["from"]]
                to_client = self.download_clients[connection["to"]]
                new_connection = TransferConnection(
                    name, connection, from_client, to_client,
                    history_service=self.history_service,
                    history_config=self.history_config
                )
                from_client.add_connection(new_connection)
                to_client.add_connection(new_connection)
                self.connections[name] = new_connection
            except KeyError as e:
                logger.error(f"Failed to load connection '{name}': missing client {e}")
    
    def _setup_tracker(self, config):
        """Set up BitTorrent tracker and transfer handler if enabled.
        
        The tracker starts whenever enabled, even if no torrent connections
        exist yet. This avoids a chicken-and-egg problem where adding the
        first torrent connection would fail the test because the tracker
        isn't running.
        
        Args:
            config: Application configuration dict
        """
        tracker_config = config.get("tracker", {})
        if not tracker_config.get("enabled", False):
            logger.debug("BitTorrent tracker not enabled")
            return
        
        try:
            self.tracker = create_tracker_from_config(config)
            if self.tracker:
                self.tracker.start()
                self.torrent_transfer_handler = TorrentTransferHandler(
                    tracker=self.tracker,
                    history_service=self.history_service,
                    history_config=self.history_config
                )
                logger.info("BitTorrent tracker and transfer handler initialized")
        except Exception as e:
            logger.error(f"Failed to start tracker: {e}")
            self.tracker = None
            self.torrent_transfer_handler = None

    def _reregister_pending_transfers(self):
        """Re-register pending transfer hashes with tracker and restore creation slots.
        
        Tracker state is in-memory only, so after a restart (or tracker apply)
        all registered hashes are lost. This method scans loaded torrents for
        any in TORRENT_* states (or COPIED/TARGET_* with un-cleaned transfer
        data) and re-registers their transfer hashes with the tracker.
        
        Also restores _creating_slots on the handler for any torrent in
        TORRENT_CREATING state, preventing concurrent creation RPCs to the
        same Deluge instance.
        
        Also forces re-announce on both source and target clients so the
        tracker learns the peers again.
        """
        if not self.tracker or not self.torrent_transfer_handler:
            return
        
        torrent_states = {
            TorrentState.TORRENT_CREATE_QUEUE,
            TorrentState.TORRENT_CREATING,
            TorrentState.TORRENT_TARGET_ADDING,
            TorrentState.TORRENT_DOWNLOADING,
            TorrentState.TORRENT_SEEDING,
        }
        
        reregistered = 0
        for torrent in self.torrents:
            # Restore creation slot for TORRENT_CREATING torrents
            if (torrent.state == TorrentState.TORRENT_CREATING and
                    torrent.home_client and hasattr(torrent.home_client, 'name')):
                client_name = torrent.home_client.name
                self.torrent_transfer_handler._creating_slots[client_name] = torrent.id
                logger.debug(
                    f"Restored creation slot for {client_name} -> {torrent.id} "
                    f"({torrent.name})"
                )

            if not torrent.transfer or not torrent.transfer.get("hash"):
                continue
            
            transfer_hash = torrent.transfer["hash"]
            needs_registration = False
            
            # Torrents in active TORRENT_* states always need re-registration
            if torrent.state in torrent_states:
                needs_registration = True
            # COPIED or TARGET_* with un-cleaned transfer data need registration
            # so cleanup at TARGET_SEEDING can unregister properly
            elif (torrent.state and 
                  (torrent.state == TorrentState.COPIED or 
                   str(torrent.state.name).startswith("TARGET")) and
                  not torrent.transfer.get("cleaned_up")):
                needs_registration = True
            
            if needs_registration:
                try:
                    info_hash_bytes = bytes.fromhex(transfer_hash)
                    self.tracker.register_transfer(info_hash_bytes)
                    reregistered += 1
                    logger.debug(
                        f"Re-registered transfer hash {transfer_hash[:8]}... "
                        f"for {torrent.name} (state: {torrent.state.name})"
                    )
                    
                    # Force re-announce on source and target so tracker learns peers
                    if torrent.transfer.get("on_source") and torrent.home_client:
                        try:
                            torrent.home_client.force_reannounce(transfer_hash)
                        except Exception as e:
                            logger.debug(f"Failed to re-announce on source: {e}")
                    
                    if torrent.transfer.get("on_target") and torrent.target_client:
                        try:
                            torrent.target_client.force_reannounce(transfer_hash)
                        except Exception as e:
                            logger.debug(f"Failed to re-announce on target: {e}")
                    
                except Exception as e:
                    logger.error(
                        f"Failed to re-register transfer hash for {torrent.name}: {e}"
                    )
        
        if reregistered > 0:
            logger.info(f"Re-registered {reregistered} pending transfer(s) with tracker")

    def _migrate_connections_config(self):
        """Migrate connections config to latest format.
        
        Handles two migrations:
        1. Array → dict format (auto-generates names as "{from} -> {to}")
        2. source_sftp (flat) → source (nested) for torrent transfer configs
        """
        connections = self.config.get("connections")
        
        # Migration 1: array → dict
        if isinstance(connections, list):
            logger.info("Migrating connections from array to dict format...")
            migrated = {}
            name_counts = {}  # Track how many times each base name has been used
            
            for conn in connections:
                base_name = f"{conn['from']} -> {conn['to']}"
                
                # Check if this base name was already used
                if base_name in name_counts:
                    name_counts[base_name] += 1
                    name = f"{base_name} {name_counts[base_name]}"
                else:
                    name_counts[base_name] = 1
                    name = base_name
                
                migrated[name] = conn
                logger.debug(f"Migrated connection: {name}")
            
            self.config["connections"] = migrated
            connections = migrated
        
        # Migration 2: source_sftp → source for torrent transfer configs
        if isinstance(connections, dict):
            migrated_source = False
            for name, conn in connections.items():
                tc = conn.get("transfer_config", {})
                if tc.get("type") == "torrent" and "source_sftp" in tc:
                    old = tc.pop("source_sftp")
                    state_dir = old.pop("state_dir", None)
                    # Remaining keys (host, port, username, password, etc.) are SFTP connection params
                    new_source = {"type": "sftp", "sftp": old}
                    if state_dir:
                        new_source["state_dir"] = state_dir
                    tc["source"] = new_source
                    migrated_source = True
                    logger.debug(f"Migrated source_sftp → source for connection '{name}'")
            
            if migrated_source:
                logger.info("Migrated torrent connection(s) from source_sftp to source format")
        
        # Save the migrated config
        if isinstance(self.config.get("connections"), dict):
            if self.save_config(self.config):
                logger.info(f"Successfully saved migrated connections config")
            else:
                logger.error("Failed to save migrated connections config")

    def load_torrents_state(self):
        """Load the torrents state from a JSON file."""
        if not os.path.exists(self.state_file):
            logger.warning("State file not found. Starting with an empty torrents list.")
            return []
        try:
            with open(self.state_file, "r") as f:
                torrents_data = json.load(f)
            logger.info("Torrents state loaded successfully.")
            return [
                Torrent.from_dict(
                    data, 
                    self.download_clients, 
                    media_managers=self.media_managers,
                    save_callback=self.save_torrents_state
                ) 
                for data in torrents_data
            ]
        except Exception as e:
            logger.error(f"Failed to load torrents state: {e}")
            return []
    
    def save_torrents_state(self):
        """Save the torrents state to a JSON file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump([torrent.to_dict() for torrent in self.torrents], f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save torrents state: {e}")

    def _should_delete_cross_seeds(self, torrent):
        """Determine whether cross-seed siblings should be removed for a torrent.
        
        For manual transfers, the per-transfer `delete_source_cross_seeds` flag
        is checked. For automatic (media-manager) transfers, the per-client
        `delete_cross_seeds` config is checked.
        
        Uses the current client instance from self.download_clients (rather than
        the torrent's cached home_client reference) so that runtime config
        changes via the API are picked up immediately.
        
        Returns:
            bool: True if siblings should be removed.
        """
        if torrent.delete_source_cross_seeds is not None:
            # Manual transfer: per-transfer flag was explicitly set
            return torrent.delete_source_cross_seeds
        # Automatic transfer: look up current client config
        # (torrent.home_client may be a stale reference after API updates)
        client_name = getattr(torrent, 'home_client_name', None)
        if client_name and client_name in self.download_clients:
            return self.download_clients[client_name].delete_cross_seeds
        return torrent.home_client.delete_cross_seeds

    def _remove_source_cross_seeds(self, torrent):
        """Remove cross-seed siblings from the source client before removing
        the original torrent.
        
        Cross-seed siblings are identified as torrents on the same client with
        the same name and total_size but a different info_hash.
        
        Siblings that are currently being tracked for transfer (i.e. in
        self.torrents) are skipped — they will handle their own cleanup
        when their transfer completes.
        
        Siblings are removed with remove_data=True. This is safe because:
        - Hardlinked files: removing one set of paths doesn't affect the other
        - Symlinked files: removing symlinks doesn't affect the actual data
        """
        if not self._should_delete_cross_seeds(torrent):
            return
        
        try:
            all_torrents = torrent.home_client.get_all_torrents_status()
            if not all_torrents:
                return
            
            # Find the torrent's info in the full list
            torrent_info = all_torrents.get(torrent.id)
            if not torrent_info:
                return
            
            torrent_name = torrent_info.get("name")
            torrent_size = torrent_info.get("total_size")
            if not torrent_name or torrent_size is None:
                return
            
            # Build set of hashes currently tracked for transfer so we
            # don't remove a sibling that is mid-transfer.
            tracked_hashes = {t.id.lower() for t in self.torrents}
            
            # Find siblings: same name + total_size, different hash
            siblings = []
            for h, info in all_torrents.items():
                if h == torrent.id:
                    continue
                if (info.get("name") == torrent_name
                        and info.get("total_size") == torrent_size):
                    # Skip siblings that are currently being transferred
                    if h.lower() in tracked_hashes:
                        logger.debug(
                            f"Skipping cross-seed sibling {h[:8]} for "
                            f"'{torrent.name}' — currently tracked for transfer"
                        )
                        continue
                    siblings.append(h)
            
            if not siblings:
                return
            
            logger.info(
                f"Removing {len(siblings)} cross-seed sibling(s) for "
                f"'{torrent.name}' from {torrent.home_client.name}"
            )
            for sibling_hash in siblings:
                try:
                    torrent.home_client.remove_torrent(
                        sibling_hash, remove_data=True
                    )
                    logger.debug(
                        f"Removed cross-seed sibling {sibling_hash[:8]} "
                        f"for '{torrent.name}'"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to remove cross-seed sibling "
                        f"{sibling_hash[:8]} for '{torrent.name}': {e}"
                    )
        except Exception as e:
            logger.warning(
                f"Failed to query cross-seed siblings for "
                f"'{torrent.name}': {e}"
            )

    def save_config(self, updated_config):
        """Save the updated configuration to the config file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(updated_config, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def create_manual_transfers(self, hashes, source_client, dest_client,
                                connection, delete_source_cross_seeds=True):
        """Create and initiate manual transfers for the given torrent hashes.

        Creates Torrent objects from raw client data (no media manager),
        sets up home/target clients, and initiates transfers via the
        appropriate connection method (SFTP/local or torrent P2P).

        Args:
            hashes: List of torrent hashes to transfer
            source_client: Source DownloadClientBase instance
            dest_client: Target DownloadClientBase instance
            connection: TransferConnection instance to use
            delete_source_cross_seeds: Whether to remove cross-seed siblings
                when removing the source torrent after transfer (default True)

        Returns:
            Dict with transfer summary: initiated count, skipped, errors
        """
        initiated = []
        errors = []

        for torrent_hash in hashes:
            try:
                # Fetch full torrent info (includes 'files' needed by
                # get_paths_to_copy() during the file copy).
                torrent = Torrent(
                    name=torrent_hash,
                    id=torrent_hash,
                )
                torrent.set_home_client(source_client)
                info = source_client.get_torrent_info(torrent)
                if not info:
                    errors.append({
                        "hash": torrent_hash,
                        "error": "Could not fetch torrent info"
                    })
                    continue

                # Populate from fetched info
                torrent.name = info.get("name", torrent_hash)
                torrent.home_client_info = info
                torrent.set_target_client(dest_client)
                torrent.media_manager = None  # Manual transfer — no media manager
                torrent.size = int(info.get("total_size", 0))
                torrent.progress = int(info.get("progress", 0))
                torrent.delete_source_cross_seeds = delete_source_cross_seeds
                torrent.state = TorrentState.HOME_SEEDING  # no save_callback yet
                torrent.save_callback = self.save_torrents_state

                # Add to tracked torrents
                self.torrents.append(torrent)

                # Initiate transfer based on connection type
                if connection.is_torrent_transfer:
                    if self.torrent_transfer_handler:
                        # Early gate: reject private torrents in magnet-only mode
                        if connection.source_type is None:
                            try:
                                is_private = source_client.is_private_torrent(torrent_hash)
                            except Exception as e:
                                logger.warning(
                                    f"Could not check private flag for {torrent.name}: {e}. "
                                    f"Proceeding (will re-check in handle_seeding)."
                                )
                                is_private = False
                            if is_private:
                                self.torrents.remove(torrent)
                                torrent.state = TorrentState.TRANSFER_FAILED
                                errors.append({
                                    "hash": torrent_hash,
                                    "error": (
                                        "Private tracker torrent cannot be transferred "
                                        "via magnet links — configure source access "
                                        "(SFTP or local) on the connection."
                                    ),
                                })
                                continue
                        # Just set the state — the update_torrents() loop will
                        # call handle_create_queue() on its next cycle.  Calling it
                        # here would block the HTTP request for up to 120s while
                        # Deluge hashes the torrent.
                        torrent.state = TorrentState.TORRENT_CREATE_QUEUE
                        initiated.append({
                            "hash": torrent_hash,
                            "name": torrent.name,
                            "method": "torrent",
                        })
                    else:
                        self.torrents.remove(torrent)
                        torrent.state = TorrentState.ERROR
                        errors.append({
                            "hash": torrent_hash,
                            "error": "Tracker not available for torrent transfer"
                        })
                else:
                    # SFTP/local file transfer
                    connection.enqueue_copy_torrent(torrent)
                    initiated.append({
                        "hash": torrent_hash,
                        "name": torrent.name,
                        "method": connection.get_history_transfer_method(),
                    })

            except Exception as e:
                logger.error(
                    f"Error creating manual transfer for {torrent_hash}: {e}"
                )
                errors.append({"hash": torrent_hash, "error": str(e)})

        self.save_torrents_state()

        return {
            "initiated": initiated,
            "errors": errors,
            "total_initiated": len(initiated),
            "total_errors": len(errors),
        }
    
    def start(self):
        """Start the torrent manager background thread"""
        self.running = True
        self.thread = Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Stop the torrent manager background thread"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)
        self.save_torrents_state()

        for connection in self.connections.values():
            connection.shutdown()
        
        # Stop tracker if running
        if self.tracker:
            self.tracker.stop()
            self.tracker = None
    
    def _run_loop(self):
        """Main loop for the torrent manager"""
        while self.running:
            try:
                self.get_media_manager_updates()
                self.update_torrents()
                self.save_torrents_state()
                sleep(2)
            except Exception as e:
                logger.error(f"Error in torrent manager: {e}")
                sleep(10)  # Sleep longer on error

    def get_media_manager_updates(self):
        """Get updates from the media managers"""
        for media_manager in self.media_managers:
            try:
                media_manager.get_queue_updates(self.torrents, self.save_torrents_state)
            except Exception as e:
                logger.error(f"Error in media manager {media_manager}: {e}")

    def update_torrents(self):
        """Update the state of all torrents"""
        torrents_to_remove = []
        for torrent in self.torrents:
            # Skip TRANSFER_FAILED — requires explicit user action (Retry or Remove)
            if torrent.state == TorrentState.TRANSFER_FAILED:
                continue

            ### First case is a torrent that was just added to the radarr queue, state is RADARR_QUEUE
            if torrent.state in [TorrentState.MANAGER_QUEUED, TorrentState.UNCLAIMED, TorrentState.ERROR]:
                ### Check if this is one of our transfer torrents (picked up by Radarr/Sonarr)
                is_transfer = False
                for other in self.torrents:
                    if other is torrent:
                        continue
                    if other.transfer and other.transfer.get("hash", "").lower() == torrent.id.lower():
                        logger.debug(f"Torrent {torrent.name} is a transfer torrent for {other.name}, skipping")
                        is_transfer = True
                        break
                if is_transfer:
                    torrents_to_remove.append(torrent)
                    continue
                
                ### We need to find the home client for this torrent
                found = False
                for _, client in self.download_clients.items():
                    if client.has_torrent(torrent):
                        torrent.set_home_client_info(client.get_torrent_info(torrent))
                        torrent.set_home_client(client)
                        torrent.state = client.get_torrent_state(torrent)
                        logger.debug(f"Torrent {torrent.name} found home client: {client.name}, state: {torrent.state.name}")
                        found = True
                        break
                if not found:
                    torrent.not_found_attempts += 1
                    logger.debug(f"Torrent {torrent.name} not found on any client yet attempt {torrent.not_found_attempts}")
                    if torrent.state == TorrentState.ERROR:
                        logger.warning(f"Torrent {torrent.name} is in ERROR state, removing from list")
                        torrents_to_remove.append(torrent)
                    if torrent.not_found_attempts > 10:
                        logger.warning(f"Torrent {torrent.name} not found after 10 attempts, removing from list")
                        torrents_to_remove.append(torrent)
                    continue
                else:
                    ### Time to find it's target using our connections
                    for connection in self.connections.values():
                        found_connection = False
                        if connection.from_client.name == torrent.home_client.name:
                            torrent.set_target_client(connection.to_client)
                            found_connection = True
                            break
                    if not found_connection:
                        logger.debug(f"Torrent {torrent.name}: client {torrent.home_client.name} has no connection to any other client, not tracking")
                        # torrents.remove(torrent)
                        torrents_to_remove.append(torrent)
                        continue
            ### Next case is a torrent with any state that starts with HOME or COPYING (in which case we need to figure out what to do)
            elif str(torrent.state.name).startswith("HOME"):
                ### Gotta update its state first:
                if torrent.home_client.has_torrent(torrent):
                    torrent.state = torrent.home_client.get_torrent_state(torrent)
                    torrent.set_home_client_info(torrent.home_client.get_torrent_info(torrent))
                    torrent.set_progress_from_home_client_info()
                else:
                    logger.warning(f"Torrent {torrent.name} not found on home client {torrent.home_client.name}")
                    # torrents.remove(torrent)
                    torrents_to_remove.append(torrent)
                    continue
                logger.debug(f"Torrent {torrent.name} has home client {torrent.home_client.name}, state: {torrent.state.name}")
                # If there's no target client, there's nowhere to send this torrent
                if torrent.target_client is None:
                    logger.info(f"Torrent {torrent.name} in {torrent.state.name} has no target client, removing from tracked list")
                    torrents_to_remove.append(torrent)
                    continue
                ### Now we check if it's seeding
                if torrent.state == TorrentState.HOME_SEEDING:
                    logger.debug(f"Torrent {torrent.name} is seeding on home client: {torrent.home_client.name}, checking connection")
                    for connection in self.connections.values():
                        if connection.from_client.name == torrent.home_client.name and connection.to_client.name == torrent.target_client.name:
                            if torrent.target_client.has_torrent(torrent):
                                torrent.state = torrent.target_client.get_torrent_state(torrent)
                                torrent.set_target_client_info(torrent.target_client.get_torrent_info(torrent))
                                logger.debug(f"Torrent {torrent.name} already exists on {torrent.target_client.name}")
                            else:
                                logger.debug(f"Torrent {torrent.name} not found on {torrent.target_client.name}, ready to transfer")
                                # Check if this is a torrent-based transfer
                                if connection.is_torrent_transfer:
                                    if self.torrent_transfer_handler:
                                        # Early gate: reject private torrents in magnet-only mode
                                        # before creating any transfer torrents.
                                        if connection.source_type is None:
                                            try:
                                                is_private = torrent.home_client.is_private_torrent(torrent.id)
                                            except Exception as e:
                                                logger.warning(
                                                    f"Could not check private flag for {torrent.name}: {e}. "
                                                    f"Proceeding (will re-check in handle_seeding)."
                                                )
                                                is_private = False
                                            if is_private:
                                                logger.error(
                                                    f"Torrent '{torrent.name}' is a private tracker torrent but "
                                                    f"connection '{connection.name}' has no source access configured. "
                                                    f"Configure source access (SFTP or local) to transfer private torrents."
                                                )
                                                torrent.state = TorrentState.TRANSFER_FAILED
                                                break
                                        torrent.state = TorrentState.TORRENT_CREATE_QUEUE
                                    else:
                                        logger.error(
                                            f"Torrent {torrent.name} needs torrent transfer but tracker is disabled. "
                                            f"Enable the tracker or change connection '{connection.name}' to a file-based transfer."
                                        )
                                else:
                                    # SFTP/local file transfer
                                    connection.enqueue_copy_torrent(torrent)
            ### If the torrent is in COPYING state, check if it's in the connection queue
            elif torrent.state == TorrentState.COPYING:
                # Check if the torrent is in any connection's active transfers
                already_in_queue = False
                for connection in self.connections.values(): 
                    if any(t.id == torrent.id for t in connection.get_active_transfers()):
                        already_in_queue = True
                        logger.debug(f"Torrent {torrent.name} is already in the transfer queue")
                
                # If not in the queue, find the appropriate connection and enqueue it
                if not already_in_queue and torrent.home_client and torrent.target_client:
                    connection_found = False
                    for connection in self.connections.values():
                        if (connection.from_client.name == torrent.home_client.name and 
                            connection.to_client.name == torrent.target_client.name):
                            logger.debug(f"Re-enqueueing torrent {torrent.name} for copying with connection from {connection.from_client.name} to {connection.to_client.name}")
                            connection.enqueue_copy_torrent(torrent)
                            connection_found = True
                            break
                    
                    if not connection_found:
                        logger.warning(f"Could not find appropriate connection for torrent {torrent.name} from {torrent.home_client.name} to {torrent.target_client.name}")
            ### Handle torrent-based transfer states
            elif torrent.state in [TorrentState.TORRENT_CREATE_QUEUE, TorrentState.TORRENT_CREATING,
                                   TorrentState.TORRENT_TARGET_ADDING,
                                   TorrentState.TORRENT_DOWNLOADING, TorrentState.TORRENT_SEEDING]:
                if not self.torrent_transfer_handler:
                    logger.error(f"Torrent {torrent.name} in {torrent.state.name} but no transfer handler available")
                    torrent.state = TorrentState.ERROR
                    continue
                
                # Find the connection for this torrent
                connection = None
                for conn in self.connections.values():
                    if (conn.from_client.name == torrent.home_client.name and 
                        conn.to_client.name == torrent.target_client.name):
                        connection = conn
                        break
                
                if not connection:
                    logger.error(f"No connection found for torrent {torrent.name}")
                    torrent.state = TorrentState.ERROR
                    continue
                
                # Handle current state
                if torrent.state == TorrentState.TORRENT_CREATE_QUEUE:
                    self.torrent_transfer_handler.handle_create_queue(torrent)
                elif torrent.state == TorrentState.TORRENT_CREATING:
                    self.torrent_transfer_handler.handle_creating(torrent, connection)
                elif torrent.state == TorrentState.TORRENT_TARGET_ADDING:
                    self.torrent_transfer_handler.handle_target_adding(torrent, connection)
                elif torrent.state == TorrentState.TORRENT_DOWNLOADING:
                    self.torrent_transfer_handler.handle_downloading(torrent, connection)
                elif torrent.state == TorrentState.TORRENT_SEEDING:
                    self.torrent_transfer_handler.handle_seeding(torrent, connection)
            ### If state begins with TARGET
            elif str(torrent.state.name).startswith("TARGET") or torrent.state == TorrentState.COPIED:
                ### Gotta update its state first:
                if torrent.target_client.has_torrent(torrent):
                    torrent.state = torrent.target_client.get_torrent_state(torrent)
                    torrent.set_target_client_info(torrent.target_client.get_torrent_info(torrent))
                else:
                    logger.warning(f"Torrent {torrent.name} not found on target client {torrent.target_client.name}")
                    torrent.state = TorrentState.UNCLAIMED
                    continue
                logger.debug(f"Torrent {torrent.name} has target client {torrent.target_client.name}, state: {torrent.state.name}")
                ### If it's seeding on the target, we can remove it from the home and list
                if torrent.state == TorrentState.TARGET_SEEDING:
                    # Clean up transfer torrent immediately once original is seeding on target
                    # (Don't wait for ready_to_remove - transfer torrent is no longer needed)
                    if torrent.transfer and torrent.transfer.get("hash") and not torrent.transfer.get("cleaned_up"):
                        transfer_hash = torrent.transfer["hash"]
                        if self.torrent_transfer_handler:
                            logger.debug(f"Cleaning up transfer torrent {transfer_hash[:8]}...")
                            self.torrent_transfer_handler.cleanup_transfer_torrents(
                                torrent,
                                source_client=torrent.home_client,
                                target_client=torrent.target_client,
                            )
                            logger.info(f"Transfer torrent cleaned up for {torrent.name}")
                        else:
                            logger.warning(
                                f"Cannot clean up transfer torrent {transfer_hash[:8]} for {torrent.name}: "
                                f"no transfer handler (tracker disabled). Transfer torrent may remain on clients."
                            )
                            torrent.transfer["cleaned_up"] = True
                    
                    # Check if ready to remove - if media_manager is None (not in queue anymore),
                    # assume it's safe to remove since Radarr/Sonarr already finished with it
                    ready_to_remove = True
                    if torrent.media_manager:
                        ready_to_remove = torrent.media_manager.torrent_ready_to_remove(torrent)
                    else:
                        logger.info(f"Torrent {torrent.name} has no media_manager (not in queue), assuming safe to remove")
                    
                    if ready_to_remove:
                        if torrent.target_client.has_torrent(torrent):
                            if torrent.home_client.has_torrent(torrent):
                                # Remove cross-seed siblings from source before removing original
                                self._remove_source_cross_seeds(torrent)
                                torrent.home_client.remove_torrent(torrent.id, remove_data=True)
                                logger.debug(f"Torrent {torrent.name} removed from home client {torrent.home_client.name}, and from watchlist")
                            else:
                                logger.info(f"Torrent {torrent.name} not found on home client {torrent.home_client.name}, removing from watchlist")
                            torrents_to_remove.append(torrent)
                            continue
                        else:
                            logger.warning(f"Torrent {torrent.name} not found on target client {torrent.target_client.name}, but seeding somehow, removing from list")
                            torrents_to_remove.append(torrent)
                            continue
                    else:
                        logger.debug(f"Torrent {torrent.name} not ready to be removed from home client {torrent.home_client.name}, still in radarr queue")

        for torrent in torrents_to_remove:
            if torrent in self.torrents:
                self.torrents.remove(torrent)