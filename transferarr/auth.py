"""Authentication module for Transferarr."""
import json
import os
import secrets
import string

import bcrypt
from flask_login import UserMixin

# API key prefix for identification
API_KEY_PREFIX = "tr_"
API_KEY_LENGTH = 32  # Length of random part (not including prefix)


class User(UserMixin):
    """Simple user model for single-user authentication."""

    def __init__(self, username: str):
        self.id = username
        self.username = username


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    if not password or not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def get_auth_config(config: dict) -> dict:
    """Get auth configuration with defaults."""
    auth = config.get("auth", {})
    return {
        "enabled": auth.get("enabled", False),
        "username": auth.get("username", "admin"),
        "password_hash": auth.get("password_hash"),
        "session_timeout_minutes": auth.get("session_timeout_minutes", 60),
    }


def is_auth_enabled(config: dict) -> bool:
    """Check if authentication is enabled and properly configured."""
    auth = get_auth_config(config)
    return auth["enabled"] and auth["password_hash"] is not None


def is_auth_configured(config: dict) -> bool:
    """Check if auth has been configured (setup completed).

    Returns True if:
    - auth.enabled is explicitly False (user skipped setup), OR
    - auth.enabled is True and password_hash is set (user created credentials)

    Returns False if auth section is missing or password_hash is None with enabled=True.
    """
    auth = config.get("auth", {})
    if "enabled" not in auth:
        return False  # Never configured
    if auth.get("enabled") is False:
        return True  # Explicitly disabled (user chose to skip)
    return auth.get("password_hash") is not None


def save_auth_config(config: dict, auth_settings: dict) -> None:
    """Save auth configuration to config.json.

    Args:
        config: The current config dict (will be updated in-place)
        auth_settings: Dict with auth settings to save
    """
    # Update config in memory
    if "auth" not in config:
        config["auth"] = {}
    config["auth"].update(auth_settings)

    # Save to file
    config_path = config.get("_config_path")  # Set by load_config()
    if config_path:
        with open(config_path, "w") as f:
            # Don't write internal keys like _config_path
            save_config = {k: v for k, v in config.items() if not k.startswith("_")}
            json.dump(save_config, f, indent=4)


def get_or_create_secret_key(state_dir: str) -> bytes:
    """Get or create a secret key for Flask sessions.

    The secret key is stored in <state_dir>/secret_key to persist across restarts.
    If the file doesn't exist, a new random key is generated and saved.
    """
    secret_key_path = os.path.join(state_dir, "secret_key")

    if os.path.exists(secret_key_path):
        with open(secret_key_path, "rb") as f:
            return f.read()

    # Generate new key
    secret_key = os.urandom(32)
    with open(secret_key_path, "wb") as f:
        f.write(secret_key)

    return secret_key


# =============================================================================
# API Key Authentication
# =============================================================================


def generate_api_key() -> str:
    """Generate a new API key with the standard prefix.

    Returns:
        A new API key in the format 'tr_<random_string>'
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(API_KEY_LENGTH))
    return f"{API_KEY_PREFIX}{random_part}"


def verify_api_key(provided_key: str, stored_key: str) -> bool:
    """Verify an API key using constant-time comparison.

    Args:
        provided_key: The API key provided in the request
        stored_key: The stored API key to compare against

    Returns:
        True if the keys match, False otherwise
    """
    if not provided_key or not stored_key:
        return False
    return secrets.compare_digest(provided_key, stored_key)


def check_api_key_in_request(config: dict, request) -> bool:
    """Check if a valid API key is provided in the request.

    Checks both X-API-Key header and ?apikey= query parameter.
    Header takes precedence over query parameter.

    Args:
        config: The application configuration dict
        request: The Flask request object

    Returns:
        True if a valid API key is provided, False otherwise
    """
    api_config = get_api_config(config)
    stored_key = api_config.get("key")

    if not stored_key:
        return False

    # Check header first (preferred)
    provided_key = request.headers.get("X-API-Key")

    # Fall back to query parameter
    if not provided_key:
        provided_key = request.args.get("apikey")

    if not provided_key:
        return False

    return verify_api_key(provided_key, stored_key)


def get_api_config(config: dict) -> dict:
    """Get API configuration with defaults.

    Args:
        config: The application configuration dict

    Returns:
        Dict with api config fields: key, key_required
    """
    api = config.get("api", {})
    return {
        "key": api.get("key"),
        "key_required": api.get("key_required", False),
    }


def is_api_key_required(config: dict) -> bool:
    """Check if API key authentication is required.

    API key is required when:
    - api.key_required is True
    - AND api.key is configured (not None/empty)

    Args:
        config: The application configuration dict

    Returns:
        True if API key is required for API requests
    """
    api = get_api_config(config)
    return api["key_required"] and api["key"] is not None


def save_api_config(config: dict, api_settings: dict) -> None:
    """Save API configuration to config.json.

    Args:
        config: The current config dict (will be updated in-place)
        api_settings: Dict with API settings to save (key, key_required)
    """
    # Update config in memory
    if "api" not in config:
        config["api"] = {}
    config["api"].update(api_settings)

    # Save to file using same pattern as save_auth_config
    config_path = config.get("_config_path")
    if config_path:
        with open(config_path, "w") as f:
            save_config = {k: v for k, v in config.items() if not k.startswith("_")}
            json.dump(save_config, f, indent=4)


def get_or_create_api_key(config: dict) -> str:
    """Get existing API key or create a new one.

    If no API key exists in the config, generates a new one and saves it.

    Args:
        config: The application configuration dict

    Returns:
        The API key (existing or newly generated)
    """
    api = get_api_config(config)
    if api["key"]:
        return api["key"]

    # Generate new key and save
    new_key = generate_api_key()
    save_api_config(config, {"key": new_key})
    return new_key


if __name__ == "__main__":
    """CLI entrypoint for password hashing."""
    import getpass
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "hash-password":
        password = getpass.getpass("Enter password: ")
        confirm = getpass.getpass("Confirm password: ")

        if password != confirm:
            print("Passwords do not match", file=sys.stderr)
            sys.exit(1)

        if len(password) < 8:
            print("Password must be at least 8 characters", file=sys.stderr)
            sys.exit(1)

        print(hash_password(password))
    else:
        print("Usage: python -m transferarr.auth hash-password")
        sys.exit(1)
