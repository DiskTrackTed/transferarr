"""Unit tests for the auth module."""
import os
import tempfile

import pytest

from transferarr.auth import (
    API_KEY_LENGTH,
    API_KEY_PREFIX,
    User,
    generate_api_key,
    get_api_config,
    get_auth_config,
    get_or_create_api_key,
    get_or_create_secret_key,
    hash_password,
    is_api_key_required,
    is_auth_configured,
    is_auth_enabled,
    save_api_config,
    save_auth_config,
    verify_api_key,
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


# =============================================================================
# API Key Tests
# =============================================================================


class TestGenerateApiKey:
    """Tests for generate_api_key function."""

    def test_generate_api_key_has_prefix(self):
        """Generated key has the correct prefix."""
        key = generate_api_key()
        assert key.startswith(API_KEY_PREFIX)

    def test_generate_api_key_correct_length(self):
        """Generated key has the correct length."""
        key = generate_api_key()
        # Total length = prefix length + random part length
        expected_length = len(API_KEY_PREFIX) + API_KEY_LENGTH
        assert len(key) == expected_length

    def test_generate_api_key_unique(self):
        """Generated keys are unique."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_generate_api_key_alphanumeric(self):
        """Generated key contains only alphanumeric characters after prefix."""
        key = generate_api_key()
        random_part = key[len(API_KEY_PREFIX):]
        assert random_part.isalnum()


class TestVerifyApiKey:
    """Tests for verify_api_key function."""

    def test_verify_api_key_correct(self):
        """Correct key verifies."""
        key = generate_api_key()
        assert verify_api_key(key, key) is True

    def test_verify_api_key_incorrect(self):
        """Wrong key fails."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert verify_api_key(key1, key2) is False

    def test_verify_api_key_empty_provided(self):
        """Empty provided key fails gracefully."""
        stored_key = generate_api_key()
        assert verify_api_key("", stored_key) is False
        assert verify_api_key(None, stored_key) is False

    def test_verify_api_key_empty_stored(self):
        """Empty stored key fails gracefully."""
        provided_key = generate_api_key()
        assert verify_api_key(provided_key, "") is False
        assert verify_api_key(provided_key, None) is False

    def test_verify_api_key_both_empty(self):
        """Both empty fails gracefully."""
        assert verify_api_key("", "") is False
        assert verify_api_key(None, None) is False

    def test_verify_api_key_case_sensitive(self):
        """API key comparison is case-sensitive."""
        key = "tr_TestKey123456789012345678901234"
        assert verify_api_key(key, key) is True
        assert verify_api_key(key.lower(), key) is False
        assert verify_api_key(key.upper(), key) is False
        assert verify_api_key(key, key.lower()) is False


class TestGetApiConfig:
    """Tests for get_api_config function."""

    def test_get_api_config_defaults(self):
        """Missing api section returns defaults."""
        config = {}
        api = get_api_config(config)

        assert api["key"] is None
        assert api["key_required"] is False

    def test_get_api_config_partial(self):
        """Partial api section fills missing fields with defaults."""
        config = {
            "api": {
                "key": "tr_testkey123",
            }
        }
        api = get_api_config(config)

        assert api["key"] == "tr_testkey123"
        assert api["key_required"] is False  # Default

    def test_get_api_config_full(self):
        """Full api section returns all values."""
        config = {
            "api": {
                "key": "tr_testkey123",
                "key_required": False,
            }
        }
        api = get_api_config(config)

        assert api["key"] == "tr_testkey123"
        assert api["key_required"] is False


class TestIsApiKeyRequired:
    """Tests for is_api_key_required function."""

    def test_is_api_key_required_no_key(self):
        """No key means not required."""
        config = {"api": {"key_required": True}}
        assert is_api_key_required(config) is False

    def test_is_api_key_required_with_key_and_required(self):
        """Key present and required=True means required."""
        config = {"api": {"key": "tr_testkey", "key_required": True}}
        assert is_api_key_required(config) is True

    def test_is_api_key_required_with_key_not_required(self):
        """Key present but required=False means not required."""
        config = {"api": {"key": "tr_testkey", "key_required": False}}
        assert is_api_key_required(config) is False

    def test_is_api_key_required_empty_config(self):
        """Empty config means not required (no key)."""
        config = {}
        assert is_api_key_required(config) is False


class TestSaveApiConfig:
    """Tests for save_api_config function."""

    def test_save_api_config_creates_section(self):
        """Creates api section if missing."""
        config = {}
        save_api_config(config, {"key": "tr_newkey"})

        assert "api" in config
        assert config["api"]["key"] == "tr_newkey"

    def test_save_api_config_updates_existing(self):
        """Updates existing api section."""
        config = {"api": {"key": "tr_oldkey", "key_required": True}}
        save_api_config(config, {"key": "tr_newkey"})

        assert config["api"]["key"] == "tr_newkey"
        assert config["api"]["key_required"] is True  # Unchanged

    def test_save_api_config_writes_to_file(self):
        """Saves to file when config path is set."""
        import json

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"api": {}}, f)
            config_path = f.name

        try:
            config = {"api": {}, "_config_path": config_path}
            save_api_config(config, {"key": "tr_filetest"})

            # Read back and verify
            with open(config_path) as f:
                saved = json.load(f)

            assert saved["api"]["key"] == "tr_filetest"
            assert "_config_path" not in saved  # Internal key not saved
        finally:
            os.unlink(config_path)


class TestGetOrCreateApiKey:
    """Tests for get_or_create_api_key function."""

    def test_get_or_create_api_key_returns_existing(self):
        """Returns existing key without generating new one."""
        config = {"api": {"key": "tr_existingkey"}}
        key = get_or_create_api_key(config)

        assert key == "tr_existingkey"

    def test_get_or_create_api_key_generates_new(self):
        """Generates and saves new key if none exists."""
        import json

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"api": {}}, f)
            config_path = f.name

        try:
            config = {"api": {}, "_config_path": config_path}
            key = get_or_create_api_key(config)

            # Should have generated a key
            assert key.startswith(API_KEY_PREFIX)

            # Key should be saved in config
            assert config["api"]["key"] == key

            # Key should be saved to file
            with open(config_path) as f:
                saved = json.load(f)
            assert saved["api"]["key"] == key
        finally:
            os.unlink(config_path)
