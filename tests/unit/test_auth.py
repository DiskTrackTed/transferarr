"""Unit tests for the auth module."""
import os
import tempfile

import pytest

from transferarr.auth import (
    User,
    get_auth_config,
    get_or_create_secret_key,
    hash_password,
    is_auth_configured,
    is_auth_enabled,
    save_auth_config,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_valid_bcrypt(self):
        """Hash is valid bcrypt format."""
        password = "testpassword123"
        hashed = hash_password(password)

        # bcrypt hashes start with $2b$ (or $2a$, $2y$)
        assert hashed.startswith("$2")
        # bcrypt hashes are 60 characters
        assert len(hashed) == 60

    def test_hash_password_different_salts(self):
        """Same password produces different hashes (salt)."""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Different hashes due to random salt
        assert hash1 != hash2
        # But both should verify correctly
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_verify_password_correct(self):
        """Correct password verifies."""
        password = "mysecretpassword"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Wrong password fails."""
        password = "mysecretpassword"
        hashed = hash_password(password)

        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty_string(self):
        """Empty password fails gracefully."""
        hashed = hash_password("realpassword")

        assert verify_password("", hashed) is False
        assert verify_password(None, hashed) is False
        assert verify_password("password", None) is False
        assert verify_password("", None) is False


class TestGetAuthConfig:
    """Tests for get_auth_config function."""

    def test_get_auth_config_defaults(self):
        """Missing auth section returns defaults."""
        config = {}
        auth = get_auth_config(config)

        assert auth["enabled"] is False
        assert auth["username"] == "admin"
        assert auth["password_hash"] is None
        assert auth["session_timeout_minutes"] == 60

    def test_get_auth_config_partial(self):
        """Partial auth section fills missing fields with defaults."""
        config = {
            "auth": {
                "enabled": True,
                "username": "myuser",
            }
        }
        auth = get_auth_config(config)

        assert auth["enabled"] is True
        assert auth["username"] == "myuser"
        assert auth["password_hash"] is None  # Default
        assert auth["session_timeout_minutes"] == 60  # Default

    def test_get_auth_config_full(self):
        """Full auth section returns all values."""
        config = {
            "auth": {
                "enabled": True,
                "username": "admin",
                "password_hash": "$2b$12$somehash",
                "session_timeout_minutes": 120,
            }
        }
        auth = get_auth_config(config)

        assert auth["enabled"] is True
        assert auth["username"] == "admin"
        assert auth["password_hash"] == "$2b$12$somehash"
        assert auth["session_timeout_minutes"] == 120


class TestIsAuthEnabled:
    """Tests for is_auth_enabled function."""

    def test_is_auth_enabled_true(self):
        """Enabled + hash = True."""
        config = {
            "auth": {
                "enabled": True,
                "password_hash": "$2b$12$somehash",
            }
        }
        assert is_auth_enabled(config) is True

    def test_is_auth_enabled_no_hash(self):
        """Enabled but no hash = False."""
        config = {
            "auth": {
                "enabled": True,
                "password_hash": None,
            }
        }
        assert is_auth_enabled(config) is False

    def test_is_auth_enabled_disabled(self):
        """Disabled = False."""
        config = {
            "auth": {
                "enabled": False,
                "password_hash": "$2b$12$somehash",
            }
        }
        assert is_auth_enabled(config) is False

    def test_is_auth_enabled_no_config(self):
        """No auth config = False."""
        config = {}
        assert is_auth_enabled(config) is False


class TestIsAuthConfigured:
    """Tests for is_auth_configured function."""

    def test_is_auth_configured_not_configured(self):
        """No auth section = False."""
        config = {}
        assert is_auth_configured(config) is False

    def test_is_auth_configured_no_enabled_key(self):
        """Auth section without 'enabled' key = False."""
        config = {"auth": {"username": "admin"}}
        assert is_auth_configured(config) is False

    def test_is_auth_configured_skipped(self):
        """enabled=False = True (configured)."""
        config = {
            "auth": {
                "enabled": False,
            }
        }
        assert is_auth_configured(config) is True

    def test_is_auth_configured_with_credentials(self):
        """enabled + hash = True."""
        config = {
            "auth": {
                "enabled": True,
                "password_hash": "$2b$12$somehash",
            }
        }
        assert is_auth_configured(config) is True

    def test_is_auth_configured_enabled_but_no_hash(self):
        """enabled=True but no hash = False (incomplete setup)."""
        config = {
            "auth": {
                "enabled": True,
                "password_hash": None,
            }
        }
        assert is_auth_configured(config) is False


class TestSaveAuthConfig:
    """Tests for save_auth_config function."""

    def test_save_auth_config_creates_section(self):
        """Creates auth section if missing."""
        config = {}
        save_auth_config(config, {"enabled": True, "username": "admin"})

        assert "auth" in config
        assert config["auth"]["enabled"] is True
        assert config["auth"]["username"] == "admin"

    def test_save_auth_config_updates_existing(self):
        """Updates existing auth section."""
        config = {
            "auth": {
                "enabled": False,
                "username": "olduser",
                "session_timeout_minutes": 60,
            }
        }
        save_auth_config(config, {"enabled": True, "username": "newuser"})

        assert config["auth"]["enabled"] is True
        assert config["auth"]["username"] == "newuser"
        # Preserved existing field
        assert config["auth"]["session_timeout_minutes"] == 60

    def test_save_auth_config_writes_to_file(self):
        """Saves config to file when _config_path is set."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"existing": "data"}')
            config_path = f.name

        try:
            config = {"existing": "data", "_config_path": config_path}
            save_auth_config(config, {"enabled": True, "username": "admin"})

            # Read back from file
            import json

            with open(config_path) as f:
                saved = json.load(f)

            assert saved["auth"]["enabled"] is True
            assert saved["auth"]["username"] == "admin"
            assert saved["existing"] == "data"
            # Internal key should not be saved
            assert "_config_path" not in saved
        finally:
            os.unlink(config_path)


class TestUserModel:
    """Tests for User model."""

    def test_user_model(self):
        """User model has correct id/username."""
        user = User("testuser")

        assert user.id == "testuser"
        assert user.username == "testuser"

    def test_user_model_is_authenticated(self):
        """User.is_authenticated returns True."""
        user = User("testuser")

        # UserMixin provides is_authenticated as a property that returns True
        assert user.is_authenticated is True

    def test_user_model_is_active(self):
        """User.is_active returns True (from UserMixin)."""
        user = User("testuser")

        assert user.is_active is True

    def test_user_model_get_id(self):
        """User.get_id() returns the user id as string."""
        user = User("testuser")

        assert user.get_id() == "testuser"


class TestSecretKey:
    """Tests for get_or_create_secret_key function."""

    def test_get_or_create_secret_key_creates(self):
        """Creates new key if not exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_key_path = os.path.join(tmpdir, "secret_key")

            # Key file should not exist yet
            assert not os.path.exists(secret_key_path)

            key = get_or_create_secret_key(tmpdir)

            # Key should now exist
            assert os.path.exists(secret_key_path)
            assert isinstance(key, bytes)

    def test_get_or_create_secret_key_reuses(self):
        """Returns existing key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create key first time
            key1 = get_or_create_secret_key(tmpdir)
            # Get key second time
            key2 = get_or_create_secret_key(tmpdir)

            # Should be the same key
            assert key1 == key2

    def test_get_or_create_secret_key_length(self):
        """Key is correct length (32 bytes)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key = get_or_create_secret_key(tmpdir)

            assert len(key) == 32

    def test_get_or_create_secret_key_is_random(self):
        """Different directories get different keys."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                key1 = get_or_create_secret_key(tmpdir1)
                key2 = get_or_create_secret_key(tmpdir2)

                # Different directories should have different keys
                assert key1 != key2
