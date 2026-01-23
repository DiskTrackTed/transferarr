"""Unit tests for the config module."""
import json
import os
import tempfile

import pytest

from transferarr.config import load_config, validate_config, ConfigError


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_stores_config_path(self):
        """load_config stores _config_path for saving."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"media_managers": [], "download_clients": {}, "connections": []}, f)
            config_path = f.name

        try:
            config = load_config(config_path)
            
            # _config_path should be set
            assert "_config_path" in config
            assert config["_config_path"] == config_path
        finally:
            os.unlink(config_path)

    def test_load_config_missing_file_raises_error(self):
        """load_config raises ConfigError for missing file."""
        with pytest.raises(ConfigError) as exc_info:
            load_config("/nonexistent/path/config.json")
        
        assert "not found" in str(exc_info.value)

    def test_load_config_invalid_json_raises_error(self):
        """load_config raises ConfigError for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {")
            config_path = f.name

        try:
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)
            
            assert "parsing" in str(exc_info.value).lower()
        finally:
            os.unlink(config_path)


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_validate_config_sets_defaults(self):
        """validate_config sets default values."""
        config = {}
        validated = validate_config(config)

        assert validated["log_level"] == "INFO"
        assert "history" in validated
        assert validated["history"]["enabled"] is True
        assert validated["history"]["retention_days"] == 90
        assert validated["history"]["track_progress"] is True
        assert "auth" in validated
        assert validated["auth"]["session_timeout_minutes"] == 60

    def test_validate_config_preserves_existing(self):
        """validate_config preserves existing values."""
        config = {
            "log_level": "DEBUG",
            "history": {"enabled": False},
            "auth": {"enabled": True, "username": "admin"},
        }
        validated = validate_config(config)

        assert validated["log_level"] == "DEBUG"
        assert validated["history"]["enabled"] is False
        assert validated["auth"]["enabled"] is True
        assert validated["auth"]["username"] == "admin"
