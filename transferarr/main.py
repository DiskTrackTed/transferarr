# main.py
import os
import logging
from threading import Thread
from time import sleep

from transferarr.config import load_config, parse_args
from transferarr.web import create_app
from transferarr.services.torrent_service import TorrentManager

# Parse arguments and load config
args = parse_args()

# Load configuration
try:
    config_file = args.config if args.config else os.getenv("CONFIG_FILE", "config.json")
    config = load_config(config_file)
except Exception as e:
    print(f"Error loading configuration: {e}")
    exit(1)

# Configure logging
log_level = config.get("log_level", "INFO").upper()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transferarr")
logger.setLevel(log_level)

# Start torrent manager
torrent_manager = TorrentManager(config, config_file)
torrent_manager.start()

# Create and run Flask app
app = create_app(config, torrent_manager)

def start_web_server():
    app.run(host="0.0.0.0", port=10444, debug=False)

# Run web server in a thread
web_server_thread = Thread(target=start_web_server, daemon=True)
web_server_thread.start()

# Main application loop
try:
    while True:
        sleep(60)  # Just keep the main thread alive
except KeyboardInterrupt:
    logger.info("Application interrupted. Shutting down...")
    torrent_manager.stop()