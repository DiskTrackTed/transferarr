"""Unit tests for connection schema validation.

Tests the unified ConnectionSchema that supports both file-transfer (SFTP/Local)
and torrent (P2P) config shapes via conditional @validates_schema.
"""
import pytest
from marshmallow import ValidationError

from transferarr.web.schemas import (
    ConnectionSchema,
    ConnectionUpdateSchema,
    ConnectionTestSchema,
    TorrentTransferConfigSchema,
)


# =============================================================================
# Sample data builders
# =============================================================================

def _file_transfer_data(**overrides):
    """Build a valid file-transfer connection payload."""
    data = {
        "name": "test-conn",
        "from": "source-deluge",
        "to": "target-deluge",
        "transfer_config": {
            "from": {"type": "local"},
            "to": {"type": "sftp", "sftp": {"host": "server", "port": 22, "username": "user", "password": "pass"}},
        },
        "source_dot_torrent_path": "/torrents",
        "source_torrent_download_path": "/downloads",
        "destination_dot_torrent_tmp_dir": "/tmp/torrents",
        "destination_torrent_download_path": "/downloads",
    }
    data.update(overrides)
    return data


def _torrent_transfer_data(**overrides):
    """Build a valid torrent-transfer connection payload."""
    data = {
        "name": "test-torrent-conn",
        "from": "source-deluge",
        "to": "target-deluge",
        "transfer_config": {
            "type": "torrent",
            "destination_path": "/downloads",
        },
    }
    data.update(overrides)
    return data


# =============================================================================
# ConnectionSchema Tests
# =============================================================================

class TestFileTransferSchemaValid:
    """File transfer config with all path fields validates successfully."""

    def test_file_transfer_schema_valid(self):
        """File transfer config with all path fields validates successfully."""
        schema = ConnectionSchema()
        result = schema.load(_file_transfer_data())

        assert result["from_"] == "source-deluge"
        assert result["to"] == "target-deluge"
        assert result["source_dot_torrent_path"] == "/torrents"
        assert result["source_torrent_download_path"] == "/downloads"
        assert result["destination_dot_torrent_tmp_dir"] == "/tmp/torrents"
        assert result["destination_torrent_download_path"] == "/downloads"
        # transfer_config is a raw dict (fields.Dict)
        assert "from" in result["transfer_config"]
        assert "to" in result["transfer_config"]

    def test_file_transfer_with_sftp_on_both_sides(self):
        """File transfer with SFTP on both sides validates."""
        data = _file_transfer_data(transfer_config={
            "from": {"type": "sftp", "sftp": {"host": "a", "port": 22, "username": "u", "password": "p"}},
            "to": {"type": "sftp", "sftp": {"host": "b", "port": 22, "username": "u", "password": "p"}},
        })
        schema = ConnectionSchema()
        result = schema.load(data)
        assert result["transfer_config"]["from"]["type"] == "sftp"
        assert result["transfer_config"]["to"]["type"] == "sftp"


class TestFileTransferSchemaMissingPaths:
    """File transfer config missing path fields raises ValidationError."""

    def test_file_transfer_schema_missing_paths(self):
        """File transfer config without path fields raises ValidationError."""
        data = _file_transfer_data()
        # Remove all path fields
        del data["source_dot_torrent_path"]
        del data["source_torrent_download_path"]
        del data["destination_dot_torrent_tmp_dir"]
        del data["destination_torrent_download_path"]

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "source_dot_torrent_path" in errors
        assert "source_torrent_download_path" in errors
        assert "destination_dot_torrent_tmp_dir" in errors
        assert "destination_torrent_download_path" in errors

    def test_file_transfer_schema_missing_some_paths(self):
        """File transfer config missing only some path fields raises ValidationError."""
        data = _file_transfer_data()
        del data["source_dot_torrent_path"]
        del data["destination_torrent_download_path"]

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "source_dot_torrent_path" in errors
        assert "destination_torrent_download_path" in errors
        # These should NOT be in errors
        assert "source_torrent_download_path" not in errors
        assert "destination_dot_torrent_tmp_dir" not in errors


class TestTorrentSchemaValid:
    """Torrent config validates successfully."""

    def test_torrent_schema_valid(self):
        """Torrent config with {type: "torrent"} validates (no path fields needed)."""
        schema = ConnectionSchema()
        result = schema.load(_torrent_transfer_data())

        assert result["from_"] == "source-deluge"
        assert result["to"] == "target-deluge"
        assert result["transfer_config"]["type"] == "torrent"
        assert result["transfer_config"]["destination_path"] == "/downloads"
        # Path fields should default to None (not required for torrent)
        assert result["source_dot_torrent_path"] is None
        assert result["source_torrent_download_path"] is None
        assert result["destination_dot_torrent_tmp_dir"] is None
        assert result["destination_torrent_download_path"] is None

    def test_torrent_schema_with_destination_path(self):
        """Torrent config with optional destination_path validates."""
        data = _torrent_transfer_data()
        data["transfer_config"]["destination_path"] = "/custom/path"
        schema = ConnectionSchema()
        result = schema.load(data)
        assert result["transfer_config"]["destination_path"] == "/custom/path"

    def test_torrent_schema_without_destination_path(self):
        """Torrent config without destination_path also validates."""
        data = _torrent_transfer_data()
        del data["transfer_config"]["destination_path"]
        schema = ConnectionSchema()
        result = schema.load(data)
        assert result["transfer_config"]["type"] == "torrent"

    def test_torrent_schema_ignores_path_fields(self):
        """Torrent config with path fields set to None passes validation."""
        data = _torrent_transfer_data()
        data["source_dot_torrent_path"] = None
        data["source_torrent_download_path"] = None
        data["destination_dot_torrent_tmp_dir"] = None
        data["destination_torrent_download_path"] = None

        schema = ConnectionSchema()
        result = schema.load(data)
        assert result["transfer_config"]["type"] == "torrent"
        assert result["source_dot_torrent_path"] is None


class TestFileTransferConfigValidatedNested:
    """File transfer transfer_config from/to structure validated by sub-schema."""

    def test_file_transfer_config_validated_nested(self):
        """File transfer transfer_config with invalid from/to raises ValidationError."""
        data = _file_transfer_data(transfer_config={
            "from": {"type": "invalid_type"},
            "to": {"type": "local"},
        })

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "transfer_config" in errors

    def test_file_transfer_config_missing_from(self):
        """File transfer transfer_config missing 'from' raises ValidationError."""
        data = _file_transfer_data(transfer_config={
            "to": {"type": "local"},
        })

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "transfer_config" in errors

    def test_file_transfer_config_missing_to(self):
        """File transfer transfer_config missing 'to' raises ValidationError."""
        data = _file_transfer_data(transfer_config={
            "from": {"type": "local"},
        })

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "transfer_config" in errors


class TestInvalidTransferConfigType:
    """Invalid transfer_config type raises ValidationError."""

    def test_invalid_transfer_config_type(self):
        """transfer_config.type = 'invalid' raises ValidationError."""
        data = _torrent_transfer_data()
        data["transfer_config"]["type"] = "invalid"

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        # This should fail on the torrent schema (type must equal "torrent")
        # but also fail on the file schema (no from/to) — the validator checks
        # torrent path first since type != "torrent", falls through to file validation
        assert "transfer_config" in errors

    def test_empty_transfer_config(self):
        """Empty transfer_config raises ValidationError."""
        data = _file_transfer_data(transfer_config={})

        schema = ConnectionSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load(data)

        errors = exc_info.value.messages
        assert "transfer_config" in errors


# =============================================================================
# ConnectionTestSchema Tests
# =============================================================================

class TestConnectionTestSchema:
    """ConnectionTestSchema accepts both transfer config shapes."""

    def test_connection_test_schema_torrent(self):
        """ConnectionTestSchema accepts torrent transfer_config."""
        schema = ConnectionTestSchema()
        result = schema.load({
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {"type": "torrent"},
        })
        assert result["transfer_config"]["type"] == "torrent"

    def test_connection_test_schema_file(self):
        """ConnectionTestSchema accepts file transfer transfer_config."""
        schema = ConnectionTestSchema()
        result = schema.load({
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "local"},
            },
        })
        assert "from" in result["transfer_config"]

    def test_connection_test_schema_no_path_fields_required(self):
        """ConnectionTestSchema does not require path fields for either type."""
        schema = ConnectionTestSchema()
        # File transfer without path fields should be fine for test
        result = schema.load({
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "sftp", "sftp": {"host": "x"}},
            },
        })
        assert result["from_"] == "source-deluge"

    def test_connection_test_schema_invalid_transfer_config(self):
        """ConnectionTestSchema rejects invalid transfer_config."""
        schema = ConnectionTestSchema()
        with pytest.raises(ValidationError):
            schema.load({
                "from": "source-deluge",
                "to": "target-deluge",
                "transfer_config": {"type": "invalid"},
            })


# =============================================================================
# ConnectionUpdateSchema Tests
# =============================================================================

class TestConnectionUpdateSchema:
    """ConnectionUpdateSchema supports both config shapes."""

    def test_update_schema_torrent(self):
        """ConnectionUpdateSchema accepts torrent config without path fields."""
        schema = ConnectionUpdateSchema()
        result = schema.load({
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {"type": "torrent", "destination_path": "/dl"},
        })
        assert result["transfer_config"]["type"] == "torrent"
        assert result["source_dot_torrent_path"] is None

    def test_update_schema_file_requires_paths(self):
        """ConnectionUpdateSchema requires path fields for file transfer."""
        schema = ConnectionUpdateSchema()
        with pytest.raises(ValidationError) as exc_info:
            schema.load({
                "from": "source-deluge",
                "to": "target-deluge",
                "transfer_config": {
                    "from": {"type": "local"},
                    "to": {"type": "local"},
                },
                # No path fields — should fail
            })
        errors = exc_info.value.messages
        assert "source_dot_torrent_path" in errors

    def test_update_schema_file_with_paths(self):
        """ConnectionUpdateSchema accepts file config with all path fields."""
        schema = ConnectionUpdateSchema()
        result = schema.load({
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "local"},
            },
            "source_dot_torrent_path": "/a",
            "source_torrent_download_path": "/b",
            "destination_dot_torrent_tmp_dir": "/c",
            "destination_torrent_download_path": "/d",
        })
        assert result["source_dot_torrent_path"] == "/a"


# =============================================================================
# TorrentTransferConfigSchema Tests
# =============================================================================

class TestTorrentTransferConfigSchema:
    """Direct tests for TorrentTransferConfigSchema."""

    def test_valid_torrent_config(self):
        """Valid torrent config loads successfully."""
        schema = TorrentTransferConfigSchema()
        result = schema.load({"type": "torrent", "destination_path": "/downloads"})
        assert result["type"] == "torrent"
        assert result["destination_path"] == "/downloads"

    def test_torrent_config_destination_optional(self):
        """destination_path is optional."""
        schema = TorrentTransferConfigSchema()
        result = schema.load({"type": "torrent"})
        assert result["type"] == "torrent"
        assert result["destination_path"] is None

    def test_torrent_config_wrong_type(self):
        """type != 'torrent' fails validation."""
        schema = TorrentTransferConfigSchema()
        with pytest.raises(ValidationError):
            schema.load({"type": "sftp"})
