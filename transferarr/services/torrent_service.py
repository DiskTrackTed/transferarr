# services/torrent_service.py
import logging
import radarr
import json
import os
from threading import Thread
from transferarr.clients.base import load_download_clients
from transferarr.services.transfer_connection import TransferConnection
from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.media_managers import RadarrManager
from time import sleep

logger = logging.getLogger("transferarr")

class TorrentManager:
    def __init__(self, config, config_file):
        self.torrents = []
        self.config = config
        self.config_file = config_file
        self.media_managers = []
        self.download_clients = {}
        self.connections = []
        self.state_file = config.get("state_file")
        self.running = False
        self.setup_media_managers(config)
        self.load_download_clients(config)
        self.load_connections(config)

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
                else:
                    logger.warning(f"Unknown media manager type: {manager['type']}")
            except Exception as e:
                logger.error(f"Failed to set up media manager {manager['type']}: {e}")

    def load_download_clients(self, config):
        self.download_clients = load_download_clients(config)

    def load_connections(self, config):
        """Load the connections from the configuration."""
        for connection in config["connections"]:
            from_client = self.download_clients[connection["from"]]
            to_client = self.download_clients[connection["to"]]
            new_connection = TransferConnection(connection, from_client, to_client)
            from_client.add_connection(new_connection)
            to_client.add_connection(new_connection)
            self.connections.append(new_connection)

    def load_torrents_state(self):
        """Load the torrents state from a JSON file."""
        if not os.path.exists(self.state_file):
            logger.warning("State file not found. Starting with an empty torrents list.")
            return []
        try:
            with open(self.state_file, "r") as f:
                torrents_data = json.load(f)
            logger.info("Torrents state loaded successfully.")
            return [Torrent.from_dict(data, self.download_clients, save_callback=self.save_torrents_state) for data in torrents_data]
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

    def save_config(self, updated_config):
        """Save the updated configuration to the config file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(updated_config, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
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

        for connection in self.connections:
            connection.shutdown()
    
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
            ### First case is a torrent that was just added to the radarr queue, state is RADARR_QUEUE
            if torrent.state in [TorrentState.RADARR_QUEUED, TorrentState.UNCLAIMED, TorrentState.ERROR]:
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
                    for connection in self.connections:
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
                ### Now we check if it's seeding
                if torrent.state == TorrentState.HOME_SEEDING:
                    logger.debug(f"Torrent {torrent.name} is seeding on home client: {torrent.home_client.name}, checking connection")
                    ### Does the torrent have a to_client
                    if torrent.target_client is not None:
                        for connection in self.connections:
                            if connection.from_client.name == torrent.home_client.name and connection.to_client.name == torrent.target_client.name:
                                if torrent.target_client.has_torrent(torrent):
                                    torrent.state = torrent.target_client.get_torrent_state(torrent)
                                    torrent.set_target_client_info(torrent.target_client.get_torrent_info(torrent))
                                    logger.debug(f"Torrent {torrent.name} already exists on {torrent.target_client.name}")
                                else:
                                    logger.debug(f"Torrent {torrent.name} not found on {torrent.target_client.name}, ready to copy")
                                    connection.enqueue_copy_torrent(torrent)
            ### If the torrent is in COPYING state, check if it's in the connection queue
            elif torrent.state == TorrentState.COPYING:
                # Check if the torrent is in any connection's active transfers
                already_in_queue = False
                for connection in self.connections: 
                    if any(t.name == torrent.name for t in connection.get_active_transfers()):
                        already_in_queue = True
                        logger.debug(f"Torrent {torrent.name} is already in the transfer queue")
                
                # If not in the queue, find the appropriate connection and enqueue it
                if not already_in_queue and torrent.home_client and torrent.target_client:
                    connection_found = False
                    for connection in self.connections:
                        if (connection.from_client.name == torrent.home_client.name and 
                            connection.to_client.name == torrent.target_client.name):
                            logger.debug(f"Re-enqueueing torrent {torrent.name} for copying with connection from {connection.from_client.name} to {connection.to_client.name}")
                            connection.enqueue_copy_torrent(torrent)
                            connection_found = True
                            break
                    
                    if not connection_found:
                        logger.warning(f"Could not find appropriate connection for torrent {torrent.name} from {torrent.home_client.name} to {torrent.target_client.name}")
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
                    if torrent.media_manager.torrent_ready_to_remove(torrent):
                        if torrent.target_client.has_torrent(torrent):
                            if torrent.home_client.has_torrent(torrent):
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

        for torrent in torrents_to_remove:
            if torrent in self.torrents:
                self.torrents.remove(torrent)