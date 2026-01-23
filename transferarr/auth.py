"""Authentication module for Transferarr."""
import json
import os

import bcrypt
from flask_login import UserMixin


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
