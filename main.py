import os
import logging
import json
import radarr
from time import sleep
from transferarr.utils import do_copy_files, do_torrent_cleanup
from transferarr.radarr_utils import get_radarr_queue_updates
from transferarr.deluge import get_local_deluge_info, get_sb_deluge_info, DelugeClient
from transferarr.torrent import Torrent
from transferarr.config import load_config, parse_args

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

def save_torrents_state():
    """Save the torrents state to a JSON file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump([torrent.to_dict() for torrent in torrents], f, indent=4)
        logger.debug("Torrents state saved successfully.")
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
        return [Torrent.from_dict(data, save_callback=save_torrents_state) for data in torrents_data]
    except Exception as e:
        logger.error(f"Failed to load torrents state: {e}")
        return []

radarr_config = radarr.Configuration(
    host=config["radarr_host"]
)
radarr_config.api_key['apikey'] = config["radarr_api_key"]
radarr_config.api_key['X-Api-Key'] = config["radarr_api_key"]

local_client = DelugeClient(
    config["local_deluge"]["host"],
    config["local_deluge"]["port"],
    config["local_deluge"]["username"],
    config["local_deluge"]["password"],
    dot_torrent_path=config["local_deluge"]["dot_torrent_path"],
    torrent_download_path=config["local_deluge"]["torrent_download_path"]
)
if local_client.is_connected():
    logger.info("Connected to local deluge")

sb_client = DelugeClient(
    config["sb_deluge"]["host"],
    config["sb_deluge"]["port"],
    config["sb_deluge"]["username"],
    config["sb_deluge"]["password"],
    dot_torrent_tmp_dir=config["sb_deluge"]["dot_torrent_tmp_dir"],
    torrent_download_path=config["sb_deluge"]["torrent_download_path"],
    transfer_config=config["sb_deluge"].get("transfer_config")
)
if sb_client.is_connected():
    logger.info("Connected to SB deluge")

# Load torrents state
torrents = load_torrents_state()
logger.info(f"Loaded {len(torrents)} torrents from state file.")

logger.info("Starting transfer cycle")
try:
    while True:
        get_radarr_queue_updates(radarr_config, torrents, save_torrents_state)
        get_local_deluge_info(local_client, torrents)
        get_sb_deluge_info(sb_client, torrents)
        do_copy_files(local_client, sb_client, torrents)
        do_torrent_cleanup(local_client, sb_client, torrents, save_torrents_state)
        logger.debug("Sleeping for 5 seconds...")
        sleep(5)
except KeyboardInterrupt:
    logger.info("Application interrupted. Saving state before exiting...")
    save_torrents_state()
