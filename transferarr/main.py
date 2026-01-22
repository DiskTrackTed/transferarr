# main.py
import os
import logging
from pathlib import Path
from threading import Thread
from time import sleep

from transferarr.config import load_config, parse_args, DEFAULT_CONFIG_PATH, DEFAULT_STATE_DIR
from transferarr.web import create_app
from transferarr.services.torrent_service import TorrentManager
from transferarr.services.history_service import HistoryService

# Parse arguments and load config
args = parse_args()

# Resolve config file path (CLI > env > default)
config_file = args.config or os.getenv("CONFIG_FILE", DEFAULT_CONFIG_PATH)

# Resolve state directory (CLI > env > default)
state_dir = args.state_dir or os.getenv("STATE_DIR", DEFAULT_STATE_DIR)
state_dir = Path(state_dir)

# Load configuration
try:
    config = load_config(config_file)
except Exception as e:
    print(f"Error loading configuration: {e}")
    exit(1)

# Configure logging
log_level = config.get("log_level", "INFO").upper()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("transferarr")
logger.setLevel(log_level)

logger.info(f"Config file: {config_file}")
logger.info(f"State directory: {state_dir}")

# Ensure state directory exists
state_dir.mkdir(parents=True, exist_ok=True)

# Initialize history service (if enabled)
history_config = config.get("history", {})
history_enabled = history_config.get("enabled", True)

if history_enabled:
    history_db_path = state_dir / "history.db"
    history_service = HistoryService(str(history_db_path))
    logger.info(f"History database initialized at: {history_db_path}")
    
    # Apply retention policy on startup
    retention_days = history_config.get("retention_days")
    if retention_days is not None and retention_days > 0:
        history_service.prune_old_entries(retention_days)
        logger.info(f"History retention policy: {retention_days} days")
else:
    history_service = None
    logger.info("History tracking is disabled")

# Start torrent manager with history service and config
torrent_manager = TorrentManager(
    config, 
    config_file, 
    state_dir=str(state_dir),
    history_service=history_service, 
    history_config=history_config
)
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