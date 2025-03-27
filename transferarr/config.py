import json
import os
import argparse

DEFAULT_CONFIG_PATH = "config.json"

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
    required_fields = ["radarr_host", "radarr_api_key", "local_deluge", "sb_deluge"]
    for field in required_fields:
        if field not in config:
            raise ConfigError(f"Missing required configuration field: {field}")

    # Set defaults for optional fields
    config.setdefault("log_level", "INFO")
    config.setdefault("state_file", "torrents_state.json")

    return config

def parse_args():
    """
    Parse command-line arguments to allow overriding the config file location.
    :return: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Transferarr Configuration")
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the configuration file (default: config.json)"
    )
    return parser.parse_args()
