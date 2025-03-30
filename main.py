#pylint: disable=too-many-nested-blocks
import os
import logging
import json
import radarr
from time import sleep
from transferarr.radarr_utils import get_radarr_queue_updates
from transferarr.deluge import get_local_deluge_info, get_sb_deluge_info, DelugeClient
from transferarr.torrent import Torrent, TorrentState
from transferarr.config import load_config, parse_args
from transferarr.transfer_connection import TransferConnection

# Parse command-line arguments
args = parse_args()

# Load configuration
try:
    config = load_config(args.config)
except Exception as e:
    print(f"Error loading configuration: {e}")
    exit(1)

log_level = config.get("log_level", "INFO").upper()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transferarr")
logger.setLevel(log_level)

logging.getLogger("transferarr.utils").setLevel(log_level)
logging.getLogger("transferarr.radarr_utils").setLevel(log_level)
logging.getLogger("transferarr.deluge").setLevel(log_level)
logging.getLogger("transferarr.ftp").setLevel(log_level)
logging.getLogger("transferarr.deluge").setLevel(log_level)

STATE_FILE = config.get("state_file")

radarr_config = radarr.Configuration(
    host=config["radarr_host"]
)
radarr_config.api_key['apikey'] = config["radarr_api_key"]
radarr_config.api_key['X-Api-Key'] = config["radarr_api_key"]

download_clients = {}

for download_client in config["download_clients"].keys():
    download_client_config = config["download_clients"][download_client]
    if download_client_config["type"] == "deluge":
        download_clients[download_client] = DelugeClient(
            download_client,
            download_client_config["host"],
            download_client_config["port"],
            download_client_config["username"],
            download_client_config["password"]
        )

connections = []
for connection in config["connections"]:
    from_client = download_clients[connection["from"]]
    to_client = download_clients[connection["to"]]
    new_connection = TransferConnection(connection, from_client, to_client)
    from_client.add_connection(new_connection)
    to_client.add_connection(new_connection)
    connections.append(new_connection)

def save_torrents_state():
    """Save the torrents state to a JSON file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump([torrent.to_dict() for torrent in torrents], f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save torrents state: {e}")

def load_torrents_state():
    """Load the torrents state from a JSON file."""
    if not os.path.exists(STATE_FILE):
        logger.warning("State file not found. Starting with an empty torrents list.")
        return []
    try:
        with open(STATE_FILE, "r") as f:
            torrents_data = json.load(f)
        logger.info("Torrents state loaded successfully.")
        return [Torrent.from_dict(data, download_clients, save_callback=save_torrents_state) for data in torrents_data]
    except Exception as e:
        logger.error(f"Failed to load torrents state: {e}")
        return []

def update_torrents(torrents, download_clients, connections):
    for torrent in torrents:
        ### First case is a torrent that was just added to the radarr queue, state is RADARR_QUEUE
        if torrent.state == TorrentState.RADARR_QUEUED or torrent.state == TorrentState.UNCLAIMED:
            ### We need to find the home client for this torrent
            found = False
            for _, client in download_clients.items():
                if client.has_torrent(torrent):
                    torrent.set_home_client_info(client.get_torrent_info(torrent))
                    torrent.set_home_client(client)
                    torrent.state = client.get_torrent_state(torrent)
                    logger.debug(f"Torrent {torrent.name} found home client: {client.name}, state: {torrent.state.name}")
                    found = True
                    break
            if not found:
                logger.warning(f"Torrent {torrent.name} not found on any client yet")
                continue
            else:
                ### Time to find it's target using our connections
                for connection in connections:
                    found_connection = False
                    if connection.from_client.name == torrent.home_client.name:
                        torrent.set_target_client(connection.to_client)
                        found_connection = True
                        break
                if not found_connection:
                    logger.debug(f"Torrent {torrent.name}: client {torrent.home_client.name} has no connection to any other client, not tracking")
                    torrents.remove(torrent)
                    continue
        ### Next case is a torrent with any state that starts with HOME or COPYING (in which case we need to figure out what to do)
        elif str(torrent.state.name).startswith("HOME") or torrent.state == TorrentState.COPYING:
            ### Gotta update its state first:
            if torrent.home_client.has_torrent(torrent):
                torrent.state = torrent.home_client.get_torrent_state(torrent)
                torrent.set_home_client_info(torrent.home_client.get_torrent_info(torrent))
            else:
                logger.warning(f"Torrent {torrent.name} not found on home client {torrent.home_client.name}")
                torrents.remove(torrent)
                continue
            logger.debug(f"Torrent {torrent.name} has home client {torrent.home_client.name}, state: {torrent.state.name}")
            ### Now we check if it's seeding
            if torrent.state == TorrentState.HOME_SEEDING:
                logger.debug(f"Torrent {torrent.name} is seeding on home client: {torrent.home_client.name}, checking connection")
                ### Does the torrent have a to_client
                if torrent.target_client is not None:
                    for connection in connections:
                        if connection.from_client.name == torrent.home_client.name and connection.to_client.name == torrent.target_client.name:
                            if torrent.target_client.has_torrent(torrent):
                                torrent.state = torrent.target_client.get_torrent_state(torrent)
                                torrent.set_target_client_info(torrent.target_client.get_torrent_info(torrent))
                                logger.debug(f"Torrent {torrent.name} already exists on {torrent.target_client.name}")
                            else:
                                logger.debug(f"Torrent {torrent.name} not found on {torrent.target_client.name}, ready to copy")
                                connection.do_copy_torrent(torrent)
        ### If state begins with TARGET
        elif str(torrent.state.name).startswith("TARGET"):
            ### Gotta update its state first:
            if torrent.target_client.has_torrent(torrent):
                torrent.state = torrent.target_client.get_torrent_state(torrent)
                torrent.set_target_client_info(torrent.target_client.get_torrent_info(torrent))
            else:
                logger.warning(f"Torrent {torrent.name} not found on target client {torrent.target_client.name}")
                ## idk what to do here?
                # torrents.remove(torrent)
                continue
            logger.debug(f"Torrent {torrent.name} has target client {torrent.target_client.name}, state: {torrent.state.name}")
            ### If it's seeding on the target, we can remove it from the home and list
            if torrent.state == TorrentState.TARGET_SEEDING:
                if torrent.target_client.has_torrent(torrent):
                    if torrent.home_client.has_torrent(torrent):
                        torrent.home_client.remove_torrent(torrent.id, remove_data=True)
                        logger.debug(f"Torrent {torrent.name} removed from home client {torrent.home_client.name}, and from watchlist")
                    else:
                        logger.warning(f"Torrent {torrent.name} not found on home client {torrent.home_client.name}, removing from watchlist")
                    torrents.remove(torrent)



# Load torrents state
torrents = load_torrents_state()
logger.info(f"Loaded {len(torrents)} torrents from state file.")

logger.info("Starting transfer cycle")
try:
    while True:
        get_radarr_queue_updates(radarr_config, torrents, save_torrents_state)
        update_torrents(torrents, download_clients, connections)
        save_torrents_state()
        # logger.debug("Sleeping for 5 seconds...")
        sleep(5)
except KeyboardInterrupt:
    logger.info("Application interrupted. Saving state before exiting...")
    save_torrents_state()
