#pylint: disable=too-many-nested-blocks
import os
import logging
import json
import radarr
from time import sleep
from threading import Thread
from flask import Flask, jsonify, render_template, request
from transferarr.radarr_utils import get_radarr_queue_updates, radrr_torrent_ready_to_remove
from transferarr.deluge import  DelugeClient
from transferarr.torrent import Torrent, TorrentState
from transferarr.config import load_config, parse_args
from transferarr.transfer_connection import TransferConnection
from transferarr.utils import connection_modal_browse

import os.path

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
    torrents_to_remove = []
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
                for connection in connections:
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
            for connection in connections: 
                if any(t.name == torrent.name for t in connection.get_active_transfers()):
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
                if (radrr_torrent_ready_to_remove(radarr_config, torrent)):
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
        if torrent in torrents:
            torrents.remove(torrent)

# Load torrents state
torrents = load_torrents_state()
logger.info(f"Loaded {len(torrents)} torrents from state file.")


app = Flask(__name__)

# Configure web server logging
flask_log_file = config.get("web_log_file", None)
if flask_log_file:
    # Create directory for log file if it doesn't exist
    log_dir = os.path.dirname(flask_log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure Flask logging to file
    from logging.handlers import RotatingFileHandler
    flask_handler = RotatingFileHandler(
        flask_log_file, 
        maxBytes=10485760,  # 10MB
        backupCount=5       # Keep 5 backup logs
    )
    flask_handler.setLevel(logging.INFO)
    flask_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Add handler to Flask logger
    flask_logger = logging.getLogger('werkzeug')
    flask_logger.setLevel(logging.INFO)
    flask_logger.addHandler(flask_handler)
    
    # Disable Flask's default handler (console output)
    flask_logger.propagate = False
    
    app.logger.addHandler(flask_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False
    
    logger.info(f"Flask logs redirected to {flask_log_file}")

def save_config(updated_config):
    """Save the updated configuration to the config file."""
    try:
        with open(config_file, "w") as f:
            json.dump(updated_config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        return False

@app.route("/api/config")
def get_config():
    """API endpoint to get the current configuration."""
    # Return a sanitized version of the config (without sensitive information if needed)
    safe_config = {
        "download_clients": config.get("download_clients", {})
    }
    return jsonify(safe_config)

@app.route("/api/download_clients", methods=["GET"])
def get_download_clients():
    """API endpoint to get the list of download clients."""
    try:
        download_clients_data = {}
        
        for client_name, client in download_clients.items():
            download_clients_data[client_name] = {
                "name": client.name,
                "type": client.type,
                "host": client.host,
                "port": client.port,
                "username": client.username,
                "password": client.password
            }
        
        return jsonify(download_clients_data)
    except Exception as e:
        logger.error(f"Error getting download clients: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/download_clients", methods=["POST"])
def add_download_client():
    """API endpoint to add a new download client."""
    
    try:
        client_data = request.json
        if not client_data or "name" not in client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "username", "password"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        name = client_data.pop("name")
        
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # If download_clients doesn't exist, create it
        if "download_clients" not in updated_config:
            updated_config["download_clients"] = {}
        
        # Check if client with this name already exists
        if name in updated_config["download_clients"]:
            return jsonify({"error": f"Client with name '{name}' already exists"}), 409
        
        # Add the new client
        updated_config["download_clients"][name] = client_data
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Initialize the new client
            if client_data["type"] == "deluge":
                download_clients[name] = DelugeClient(
                    name,
                    client_data["host"],
                    client_data["port"],
                    client_data["username"],
                    client_data["password"]
                )
            
            return jsonify({"success": True, "message": f"Client '{name}' added successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error adding download client: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/download_clients/<name>", methods=["PUT"])
def edit_download_client(name):
    """API endpoint to edit an existing download client."""
    try:
        client_data = request.json
        if not client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "username", "password"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # Check if client exists
        if name not in updated_config.get("download_clients", {}):
            return jsonify({"error": f"Client with name '{name}' not found"}), 404
        
        # Update the client
        updated_config["download_clients"][name] = client_data
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Re-initialize the client
            if client_data["type"] == "deluge":
                # If client is already in connections, we need to stop and rebuild those connections
                existing_client = download_clients.get(name)
                if existing_client:
                    # Remove client from connections
                    for connection in connections[:]:
                        if connection.from_client.name == name or connection.to_client.name == name:
                            connections.remove(connection)
                
                # Create new client
                download_clients[name] = DelugeClient(
                    name,
                    client_data["host"],
                    client_data["port"],
                    client_data["username"],
                    client_data["password"]
                )
            
            return jsonify({"success": True, "message": f"Client '{name}' updated successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error updating download client: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/download_clients/<name>", methods=["DELETE"])
def delete_download_client(name):
    """API endpoint to delete a download client."""
    try:
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # Check if client exists
        if name not in updated_config.get("download_clients", {}):
            return jsonify({"error": f"Client with name '{name}' not found"}), 404
        
        # Check if client is used in any connections
        for connection in config.get("connections", []):
            if connection["from"] == name or connection["to"] == name:
                return jsonify({"error": f"Client '{name}' is used in connections and cannot be deleted"}), 409
        
        # Delete the client
        del updated_config["download_clients"][name]
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Remove the client from download_clients
            if name in download_clients:
                del download_clients[name]
            
            return jsonify({"success": True, "message": f"Client '{name}' deleted successfully"})
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting download client: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/download_clients/test", methods=["POST"])
def test_download_client():
    """API endpoint to test a download client connection."""
    
    try:
        client_data = request.json
        if not client_data:
            return jsonify({"error": "Invalid client data"}), 400
        
        # Validate required fields
        required_fields = ["type", "host", "port", "username", "password"]
        for field in required_fields:
            if field not in client_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Create a temporary client to test connection
        if client_data["type"] == "deluge":
            temp_client = DelugeClient(
                "temp_client",
                client_data["host"],
                client_data["port"],
                client_data["username"],
                client_data["password"]
            )
            
            # Test the connection
            result = temp_client.test_connection()
            
            # Return the result
            return jsonify(result)
        else:
            return jsonify({"error": f"Unsupported client type: {client_data['type']}"}), 400
    
    except Exception as e:
        logger.error(f"Error testing download client: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/connections", methods=["POST"])
def add_connection():
    """API endpoint to add a new connection."""
    try:
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config", 
                          "source_dot_torrent_path", "source_torrent_download_path",
                          "destination_dot_torrent_tmp_dir", "destination_torrent_download_path"]
        
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in download_clients:
            return jsonify({"error": f"Client '{from_client_name}' not found"}), 404
        
        if to_client_name not in download_clients:
            return jsonify({"error": f"Client '{to_client_name}' not found"}), 404
        
        # Check if a connection already exists between these clients
        existing_connection = None
        for conn in connections:
            if conn.from_client.name == from_client_name and conn.to_client.name == to_client_name:
                existing_connection = conn
                break
        
        if existing_connection:
            return jsonify({"error": f"A connection from '{from_client_name}' to '{to_client_name}' already exists"}), 409
        
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # If connections doesn't exist, create it
        if "connections" not in updated_config:
            updated_config["connections"] = []
        
        # Add the new connection
        updated_config["connections"].append(connection_data)
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Create and add the new connection object
            from_client = download_clients[from_client_name]
            to_client = download_clients[to_client_name]
            new_connection = TransferConnection(connection_data, from_client, to_client)
            from_client.add_connection(new_connection)
            to_client.add_connection(new_connection)
            connections.append(new_connection)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{from_client_name}' to '{to_client_name}' added successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error adding connection: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/connections/<int:connection_id>", methods=["PUT"])
def edit_connection(connection_id):
    """API endpoint to edit an existing connection."""
    try:
        if connection_id < 0 or connection_id >= len(connections):
            return jsonify({"error": f"Connection with ID {connection_id} not found"}), 404
            
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config", 
                          "source_dot_torrent_path", "source_torrent_download_path",
                          "destination_dot_torrent_tmp_dir", "destination_torrent_download_path"]
        
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in download_clients:
            return jsonify({"error": f"Client '{from_client_name}' not found"}), 404
        
        if to_client_name not in download_clients:
            return jsonify({"error": f"Client '{to_client_name}' not found"}), 404
        
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # Check if a different connection already exists between these clients
        for i, conn in enumerate(updated_config.get("connections", [])):
            if i != connection_id and conn["from"] == from_client_name and conn["to"] == to_client_name:
                return jsonify({
                    "error": f"A different connection from '{from_client_name}' to '{to_client_name}' already exists"
                }), 409
        
        # Update the connection
        if connection_id < len(updated_config.get("connections", [])):
            updated_config["connections"][connection_id] = connection_data
        else:
            return jsonify({"error": f"Connection with ID {connection_id} not found in configuration"}), 404
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Remove the old connection
            old_connection = connections[connection_id]
            from_client = old_connection.from_client
            to_client = old_connection.to_client
            
            # Clean up the old connection
            if hasattr(old_connection, 'shutdown') and callable(getattr(old_connection, 'shutdown')):
                old_connection.shutdown()
            
            # Create a new connection
            from_client = download_clients[from_client_name]
            to_client = download_clients[to_client_name]
            new_connection = TransferConnection(connection_data, from_client, to_client)
            
            # Replace the old connection
            connections[connection_id] = new_connection
            
            # Update client connections
            for client in download_clients.values():
                client.remove_connection(old_connection)
            
            from_client.add_connection(new_connection)
            to_client.add_connection(new_connection)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{from_client_name}' to '{to_client_name}' updated successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error updating connection: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/connections/<int:connection_id>", methods=["DELETE"])
def delete_connection(connection_id):
    """API endpoint to delete an existing connection."""
    try:
        if connection_id < 0 or connection_id >= len(connections):
            return jsonify({"error": f"Connection with ID {connection_id} not found"}), 404
            
        # Create a copy of the config to modify
        updated_config = dict(config)
        
        # Check if the connection exists in the configuration
        if connection_id >= len(updated_config.get("connections", [])):
            return jsonify({"error": f"Connection with ID {connection_id} not found in configuration"}), 404
        
        # Remove the connection from the configuration
        removed_connection_config = updated_config["connections"].pop(connection_id)
        
        # Save the updated config
        if save_config(updated_config):
            # Update the global config
            config.update(updated_config)
            
            # Remove the connection from the connections list
            old_connection = connections[connection_id]
            
            # Clean up the old connection
            if hasattr(old_connection, 'shutdown') and callable(getattr(old_connection, 'shutdown')):
                old_connection.shutdown()
            
            # Remove connection from clients
            from_client = old_connection.from_client
            to_client = old_connection.to_client
            from_client.remove_connection(old_connection)
            to_client.remove_connection(old_connection)
            
            # Remove from connections list
            connections.pop(connection_id)
            
            return jsonify({
                "success": True, 
                "message": f"Connection from '{removed_connection_config['from']}' to '{removed_connection_config['to']}' deleted successfully"
            })
        else:
            return jsonify({"error": "Failed to save configuration"}), 500
    
    except Exception as e:
        logger.error(f"Error deleting connection: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/")
def dashboard_page():
    """Render the dashboard page."""
    return render_template("pages/dashboard.html")

@app.route("/torrents")
def torrents_page():
    """Render the torrents page."""
    return render_template("pages/torrents.html")

@app.route("/settings")
def settings_page():
    """Render the settings page."""
    return render_template("pages/settings.html")

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
        "active_transfers": sum(len(connection.get_active_transfers()) for connection in connections),
        "total_torrents": len(torrents),
        "connections": len(connections)
    })

@app.route("/api/connections")
def get_connections():
    """API endpoint to get information about current connections."""
    connections_data = []
    for idx, connection in enumerate(connections):
        from_client = connection.from_client.name
        to_client = connection.to_client.name
        connection_data = {
            "id": idx,
            "from": from_client,
            "to": to_client,
            "source_dot_torrent_path": connection.source_dot_torrent_path,
            "source_torrent_download_path": connection.source_torrent_download_path,
            "destination_dot_torrent_tmp_dir": connection.destination_dot_torrent_tmp_dir,
            "destination_torrent_download_path": connection.destination_torrent_download_path,
            "transfer_config": connection.transfer_config,
            "active_transfers": connection.get_active_transfers_count(),
            "max_transfers": connection.max_transfers,
            "total_transfers": connection.get_total_transfers_count(),
            "status": "active"  # Assuming connections are always active for now
        }
        connections_data.append(connection_data)
    
    return jsonify(connections_data)

@app.route("/api/connections/test", methods=["POST"])
def test_connections():
    """API endpoint to test a connection between two download clients."""
    
    try:
        connection_data = request.json
        if not connection_data:
            return jsonify({"error": "Invalid connection data"}), 400
        
        # Validate required fields
        required_fields = ["from", "to", "transfer_config"]
        for field in required_fields:
            if field not in connection_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        from_client_name = connection_data["from"]
        to_client_name = connection_data["to"]
        
        # Check if clients exist
        if from_client_name not in download_clients or to_client_name not in download_clients:
            return jsonify({"error": "One or both clients do not exist"}), 404
        
        # Create a temporary connection for testing
        from_client = download_clients[from_client_name]
        to_client = download_clients[to_client_name]
        
        temp_connection = TransferConnection(
            connection_data,
            from_client,
            to_client
        )

        result = temp_connection.test_connection()
        
        # Return the result
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error testing connections: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/browse", methods=["POST"])
def browse_directory():
    """API endpoint to browse directories (local or remote via SFTP)."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        # Validate required fields
        required_fields = ["type", "config"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        path = data.get("path", "/")
        connection_type = data.get("type", "local")
        connection_config = data.get("config", {})

        return connection_modal_browse(path, connection_type, connection_config)
            
    except Exception as e:
        logger.error(f"Error in browse_directory: {e}")
        return jsonify({
            "error": f"Server error: {str(e)}",
            "entries": []
        }), 500

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
        sleep(2)
except KeyboardInterrupt:
    logger.info("Application interrupted. Saving state before exiting...")
    save_torrents_state()

    for connection in connections:
        connection.shutdown()
