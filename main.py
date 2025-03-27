import radarr
import os
import logging
import json
from time import sleep
from utils import do_copy_files, do_torrent_cleanup
from radarr_utils import get_radarr_queue_updates
from deluge import get_local_deluge_info, get_sb_deluge_info, DelugeClient
from torrent import Torrent

log_level = os.getenv("TRANSFERARR_LOG_LEVEL", "INFO").upper()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transferarr")
logger.setLevel(log_level)

logging.getLogger("utils").setLevel(log_level)
logging.getLogger("radarr_utils").setLevel(log_level)
logging.getLogger("deluge").setLevel(log_level)
logging.getLogger("ftp").setLevel(log_level)

STATE_FILE = "torrents_state.json"

def save_torrents_state():
    """Save the torrents state to a JSON file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump([torrent.to_dict() for torrent in torrents], f, indent=4)
        logger.info("Torrents state saved successfully.")
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
    host = "192.168.1.64:7878"
)
radarr_config.api_key['apikey'] = "REDACTED_API_KEY"
radarr_config.api_key['X-Api-Key'] = "REDACTED_API_KEY"

local_client = DelugeClient('192.168.1.64', 
                            58846, 
                            'transferarr', 
                            'test1234', 
                            dot_torrent_path='/data/cinimator/deluge/config/state/',
                            torrent_download_path='/data/cinimator/deluge/downloads/')
if(local_client.is_connected()):
    logger.info("Connected to local deluge")

sb_client = DelugeClient('169.150.223.207', 27656, 'transferarr', '2Gf_2h_d34', 
                         dot_torrent_tmp_dir='/home/disktrackted2/tmp/',
                         torrent_download_path='/home/disktrackted2/deluge-down/')
if(sb_client.is_connected()):
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
        do_torrent_cleanup(local_client, sb_client, torrents)
        logger.debug("Sleeping for 5 seconds...")
        sleep(5)
except KeyboardInterrupt:
    logger.info("Application interrupted. Saving state before exiting...")
    save_torrents_state()
