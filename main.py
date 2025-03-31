#pylint: disable=too-many-nested-blocks
import os
import logging
import json
import radarr
from time import sleep
from transferarr.radarr_utils import get_radarr_queue_updates
from transferarr.deluge import  DelugeClient
from transferarr.torrent import Torrent, TorrentState
from transferarr.config import load_config, parse_args
from transferarr.transfer_connection import TransferConnection
from transferarr.utils import decode_bytes
from flask import Flask, jsonify, render_template
from threading import Thread

# Parse command-line arguments
args = parse_args()

# Load configuration
try:
    config_file = args.config if args.config else os.getenv("CONFIG_FILE", "config.json")
    config = load_config(config_file)
except Exception as e:
    print(f"Error loading configuration: {e}")
    exit(1)

log_level = config.get("log_level", "INFO").upper()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transferarr")
logger.setLevel(log_level)

logging.getLogger("transferarr.utils").setLevel(log_level)
logging.getLogger("transferarr.radarr_utils").setLevel(log_level)
logging.getLogger("transferarr.transfer_connection").setLevel(log_level)
logging.getLogger("transferarr.transfer_client").setLevel(log_level)
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
        if torrent.state in [TorrentState.RADARR_QUEUED, TorrentState.UNCLAIMED, TorrentState.ERROR]:
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
                if torrent.state == TorrentState.ERROR:
                    logger.error(f"Torrent {torrent.name} is in ERROR state, removing from list")
                    torrents.remove(torrent)
                    save_torrents_state()
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
        elif str(torrent.state.name).startswith("HOME"):
            ### Gotta update its state first:
            if torrent.home_client.has_torrent(torrent):
                torrent.state = torrent.home_client.get_torrent_state(torrent)
                torrent.set_home_client_info(torrent.home_client.get_torrent_info(torrent))
                torrent.set_progress_from_home_client_info()
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
                                connection.enqueue_copy_torrent(torrent)
        ### If the torrent is in COPYING state, check if it's in the connection queue
        elif torrent.state == TorrentState.COPYING:
            # Check if the torrent is in any connection's active transfers
            already_in_queue = False
            active_transfers = TransferConnection.get_active_transfers()
            if any(t.name == torrent.name for t in active_transfers):
                already_in_queue = True
                logger.debug(f"Torrent {torrent.name} is already in the transfer queue")
            
            # If not in the queue, find the appropriate connection and enqueue it
            if not already_in_queue and torrent.home_client and torrent.target_client:
                connection_found = False
                for connection in connections:
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

app = Flask(__name__)


@app.route("/")
def index():
    """Render the main page."""
    return render_template("index.html")

@app.route("/api/torrents")
def get_torrents():
    """API endpoint to get the current state of torrents."""
    return jsonify([torrent.to_dict() for torrent in torrents])

@app.route("/api/all_torrents")
def get_all_torrents():
    """API endpoint to get all torrents from all clients."""
    all_torrents = {}
    
    for client_name, client in download_clients.items():
        try:
            if isinstance(client, DelugeClient):
                # Handle disconnected clients gracefully
                if not client.is_connected():
                    logger.warning(f"Client {client_name} is not connected, skipping")
                    all_torrents[client_name] = {}
                    continue
                
                # Get safely decoded torrent data using client method
                processed_torrents = client.get_all_torrents_status()
                
                # If there's an error and we get back an empty dict,
                # at least return a valid response
                if not processed_torrents:
                    all_torrents[client_name] = {}
                    continue
                    
                all_torrents[client_name] = processed_torrents
        except Exception as e:
            # Log the error but don't crash the endpoint
            logger.error(f"Failed to get torrents from client {client_name}: {e}")
            all_torrents[client_name] = {}
    
    # Return whatever data we were able to collect
    return jsonify(all_torrents)

@app.route("/api/stats")
def get_stats():
    """API endpoint to get system stats."""
    return jsonify({
        "active_transfers": TransferConnection.get_active_transfers_count(),
        "total_torrents": len(torrents),
        "connections": len(connections)
    })

def start_web_server():
    """Start the Flask web server."""
    app.run(host="0.0.0.0", port=10444, debug=False)

# Start the web server in a separate thread
web_server_thread = Thread(target=start_web_server, daemon=True)
web_server_thread.start()

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
    # Shutdown transfer executor
    TransferConnection.shutdown()
