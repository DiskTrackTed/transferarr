import json
import os
import argparse
import logging

# Default paths for Docker deployment
DEFAULT_CONFIG_PATH = "/config/config.json"
DEFAULT_STATE_DIR = "/state"

logger = logging.getLogger("transferarr")

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

def load_config(config_path=None):
    """
    Load and validate the configuration file.
    :param config_path: Path to the configuration file (optional).
    :return: A dictionary containing the configuration.
    """
    config_path = config_path or DEFAULT_CONFIG_PATH

    if not os.path.exists(config_path):
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Error parsing configuration file: {e}")

    return validate_config(config)

def validate_config(config):
    """
    Validate the configuration and set defaults for missing fields.
    :param config: The configuration dictionary.
    :return: The validated and updated configuration dictionary.
    """

    # Set defaults for optional fields
    config.setdefault("log_level", "INFO")
    
    # History configuration defaults
    history_config = config.setdefault("history", {})
    history_config.setdefault("enabled", True)
    history_config.setdefault("retention_days", 90)  # None = keep forever
    history_config.setdefault("track_progress", True)

    # Auth configuration defaults (don't set 'enabled' - that's set by setup)
    # We only set defaults for fields that have safe defaults
    auth_config = config.setdefault("auth", {})
    auth_config.setdefault("session_timeout_minutes", 60)

    return config

def parse_args():
    """
    Parse command-line arguments for config file and state directory.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Transferarr - Torrent Transfer Manager")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=f"Path to the configuration file (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        default=None,
        help=f"Path to the state directory for state.json and history.db (default: {DEFAULT_STATE_DIR})"
    )
    return parser.parse_args()
