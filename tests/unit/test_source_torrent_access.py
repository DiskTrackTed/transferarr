"""Unit tests for source torrent file access (SFTP and local).

Tests cover:
- SFTPClient.read_file()
- TorrentTransferHandler._fetch_torrent_file_via_sftp()
- TorrentTransferHandler._fetch_torrent_file_locally()
- TransferConnection.source_config / source_type properties
- handle_seeding() with SFTP/local/magnet paths
- _test_sftp_connectivity() helper
- _test_local_state_dir() helper
- _mask_sftp_passwords() for source.sftp
- _preserve_sftp_passwords() for source.sftp
- TorrentTransferConfigSchema with source field
- TorrentSourceConfigSchema validation
- Config migration: source_sftp → source
"""

import base64
import os
from io import BytesIO
from unittest.mock import Mock, MagicMock, patch, ANY

import pytest

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.torrent_transfer import TorrentTransferHandler
from transferarr.services.transfer_connection import (
    TransferConnection,
    _test_sftp_connectivity,
    _test_local_state_dir,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_handler(tracker=None, history_service=None):
    return TorrentTransferHandler(
        tracker=tracker or Mock(),
        history_service=history_service,
        history_config={},
    )


def _make_connection(source_config=None, source_type=None, destination_path="/downloads"):
    conn = Mock()
    conn.from_client = Mock()
    conn.to_client = Mock()
    conn.destination_torrent_download_path = destination_path
    conn.source_config = source_config
    conn.source_type = source_type
    conn.name = "test-conn"
    # Default: torrent is not private (allows magnet path in tests)
    conn.from_client.is_private_torrent.return_value = False
    return conn


def _make_seeding_torrent(**transfer_overrides):
    t = Torrent(name="Test.Movie.2024", id="orig_hash")
    t.state = TorrentState.TORRENT_SEEDING
    t.transfer = {
        "hash": "ab" * 20,
        "name": "[TR-abc123] Test.Movie.2024",
        "on_source": True,
        "on_target": True,
        "retry_count": 0,
        "total_size": 100_000,
        **transfer_overrides,
    }
    return t


SAMPLE_TORRENT_BYTES = b"d8:announce35:http://tracker:6969/announce4:infod6:lengthi1024ee"

# New-format source configs
SAMPLE_SFTP_SOURCE_CONFIG = {
    "type": "sftp",
    "sftp": {
        "host": "192.168.1.100",
        "port": 22,
        "username": "testuser",
        "password": "testpass",
    },
    "state_dir": "/home/testuser/state",
}

SAMPLE_LOCAL_SOURCE_CONFIG = {
    "type": "local",
    "state_dir": "/mnt/deluge-state",
}


# ══════════════════════════════════════════════════════════════════════
# SFTPClient.read_file()
# ══════════════════════════════════════════════════════════════════════


class TestSFTPClientReadFile:
    """Tests for SFTPClient.read_file()."""

    @patch("transferarr.clients.ftp.pysftp")
    def test_returns_file_bytes(self, mock_pysftp):
        """read_file returns bytes from remote file."""
        from transferarr.clients.ftp import SFTPClient

        mock_conn = MagicMock()
        mock_pysftp.Connection.return_value = mock_conn

        def fake_getfo(path, flo):
            flo.write(b"hello world")

        mock_conn.getfo.side_effect = fake_getfo

        client = SFTPClient(host="test", username="u", password="p")
        result = client.read_file("/remote/file.txt")

        assert result == b"hello world"
        mock_conn.getfo.assert_called_once()
        # Verify path arg
        call_args = mock_conn.getfo.call_args[0]
        assert call_args[0] == "/remote/file.txt"

    @patch("transferarr.clients.ftp.pysftp")
    def test_read_file_empty_returns_empty_bytes(self, mock_pysftp):
        """read_file returns empty bytes when file is empty."""
        from transferarr.clients.ftp import SFTPClient

        mock_conn = MagicMock()
        mock_pysftp.Connection.return_value = mock_conn
        mock_conn.getfo.side_effect = lambda path, flo: None  # writes nothing

        client = SFTPClient(host="test", username="u", password="p")
        result = client.read_file("/remote/empty.txt")

        assert result == b""

    @patch("transferarr.clients.ftp.pysftp")
    def test_read_file_closes_connection(self, mock_pysftp):
        """read_file closes connection even on success."""
        from transferarr.clients.ftp import SFTPClient

        mock_conn = MagicMock()
        mock_pysftp.Connection.return_value = mock_conn
        mock_conn.getfo.side_effect = lambda path, flo: flo.write(b"data")

        client = SFTPClient(host="test", username="u", password="p")
        client.read_file("/some/path")

        # close() called: once in __init__ and once in read_file finally block
        assert mock_conn.close.call_count >= 1

    @patch("transferarr.clients.ftp.pysftp")
    def test_read_file_raises_on_error(self, mock_pysftp):
        """read_file propagates errors from SFTP."""
        from transferarr.clients.ftp import SFTPClient

        mock_conn = MagicMock()
        mock_pysftp.Connection.return_value = mock_conn
        mock_conn.getfo.side_effect = FileNotFoundError("No such file")

        client = SFTPClient(host="test", username="u", password="p")
        with pytest.raises(FileNotFoundError):
            client.read_file("/nonexistent")


# ══════════════════════════════════════════════════════════════════════
# _sftp_client_params() helper
# ══════════════════════════════════════════════════════════════════════


class TestSftpClientParams:
    """Tests for the _sftp_client_params() helper that filters non-SFTP keys.
    
    This helper is still used by _test_sftp_connectivity() for file-transfer
    SFTP configs that may include state_dir.  For new torrent source configs,
    the SFTP params are already in a clean sub-dict so filtering is unnecessary.
    """

    def test_filters_state_dir(self):
        """state_dir is stripped from the config dict."""
        from transferarr.services.torrent_transfer import _sftp_client_params

        config = {"host": "h", "port": 22, "username": "u", "password": "p", "state_dir": "/state"}
        result = _sftp_client_params(config)
        assert "state_dir" not in result
        assert result == {"host": "h", "port": 22, "username": "u", "password": "p"}

    def test_keeps_sftp_keys(self):
        """All SFTPClient-compatible keys are preserved."""
        from transferarr.services.torrent_transfer import _sftp_client_params

        config = {
            "host": "h", "port": 22, "username": "u", "password": "p",
            "private_key": "/key", "ssh_config_host": "alias", "ssh_config_file": "~/.ssh/config",
        }
        result = _sftp_client_params(config)
        assert result == config

    def test_empty_dict(self):
        """Empty dict returns empty dict."""
        from transferarr.services.torrent_transfer import _sftp_client_params
        assert _sftp_client_params({}) == {}


# ══════════════════════════════════════════════════════════════════════
# TorrentTransferHandler._fetch_torrent_file_via_sftp()
# ══════════════════════════════════════════════════════════════════════


class TestFetchTorrentFileViaSftp:
    """Tests for _fetch_torrent_file_via_sftp() with new source config shape."""

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_happy_path_returns_base64(self, MockSFTP):
        """Returns base64-encoded torrent data on success."""
        handler = _make_handler()
        mock_sftp_instance = MockSFTP.return_value
        mock_sftp_instance.read_file.return_value = SAMPLE_TORRENT_BYTES

        result = handler._fetch_torrent_file_via_sftp("abc", SAMPLE_SFTP_SOURCE_CONFIG)

        assert result is not None
        assert base64.b64decode(result) == SAMPLE_TORRENT_BYTES
        # Should pass only SFTP sub-dict params (no state_dir)
        MockSFTP.assert_called_once_with(**SAMPLE_SFTP_SOURCE_CONFIG["sftp"])
        mock_sftp_instance.read_file.assert_called_once_with("/home/testuser/state/abc.torrent")

    def test_no_state_dir_returns_none(self):
        """Returns None when state_dir is not configured."""
        handler = _make_handler()
        config_without_state_dir = {"type": "sftp", "sftp": {"host": "h"}}

        result = handler._fetch_torrent_file_via_sftp("abc", config_without_state_dir)

        assert result is None

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_sftp_read_fails_returns_none(self, MockSFTP):
        """Returns None when SFTP read fails."""
        handler = _make_handler()
        MockSFTP.return_value.read_file.side_effect = Exception("Connection refused")

        result = handler._fetch_torrent_file_via_sftp("abc", SAMPLE_SFTP_SOURCE_CONFIG)

        assert result is None

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_empty_file_returns_none(self, MockSFTP):
        """Returns None when file is empty."""
        handler = _make_handler()
        MockSFTP.return_value.read_file.return_value = b""

        result = handler._fetch_torrent_file_via_sftp("abc", SAMPLE_SFTP_SOURCE_CONFIG)

        assert result is None

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_non_bencoded_returns_none(self, MockSFTP):
        """Returns None when file doesn't look bencoded."""
        handler = _make_handler()
        MockSFTP.return_value.read_file.return_value = b"<html>Not a torrent</html>"

        result = handler._fetch_torrent_file_via_sftp("abc", SAMPLE_SFTP_SOURCE_CONFIG)

        assert result is None


# ══════════════════════════════════════════════════════════════════════
# TorrentTransferHandler._fetch_torrent_file_locally()
# ══════════════════════════════════════════════════════════════════════


class TestFetchTorrentFileLocally:
    """Tests for _fetch_torrent_file_locally()."""

    def test_happy_path_returns_base64(self, tmp_path):
        """Returns base64-encoded torrent data on success."""
        handler = _make_handler()
        torrent_file = tmp_path / "abc.torrent"
        torrent_file.write_bytes(SAMPLE_TORRENT_BYTES)

        result = handler._fetch_torrent_file_locally("abc", str(tmp_path))

        assert result is not None
        assert base64.b64decode(result) == SAMPLE_TORRENT_BYTES

    def test_missing_file_returns_none(self, tmp_path):
        """Returns None when torrent file doesn't exist."""
        handler = _make_handler()

        result = handler._fetch_torrent_file_locally("nonexistent", str(tmp_path))

        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        """Returns None when file is empty."""
        handler = _make_handler()
        torrent_file = tmp_path / "abc.torrent"
        torrent_file.write_bytes(b"")

        result = handler._fetch_torrent_file_locally("abc", str(tmp_path))

        assert result is None

    def test_non_bencoded_returns_none(self, tmp_path):
        """Returns None when file doesn't look bencoded."""
        handler = _make_handler()
        torrent_file = tmp_path / "abc.torrent"
        torrent_file.write_bytes(b"<html>Not a torrent</html>")

        result = handler._fetch_torrent_file_locally("abc", str(tmp_path))

        assert result is None

    def test_nonexistent_dir_returns_none(self):
        """Returns None when state_dir doesn't exist."""
        handler = _make_handler()

        result = handler._fetch_torrent_file_locally("abc", "/nonexistent/path")

        assert result is None

    def test_permission_error_returns_none(self, tmp_path):
        """Returns None on permission error."""
        handler = _make_handler()
        torrent_file = tmp_path / "abc.torrent"
        torrent_file.write_bytes(SAMPLE_TORRENT_BYTES)

        with patch("builtins.open", side_effect=PermissionError("permission denied")):
            result = handler._fetch_torrent_file_locally("abc", str(tmp_path))
            assert result is None

    def test_execute_only_state_dir_still_reads_known_torrent_file(self, tmp_path):
        """Returns torrent data when the state dir is traversable but not readable."""
        handler = _make_handler()
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        torrent_file = state_dir / "abc.torrent"
        torrent_file.write_bytes(SAMPLE_TORRENT_BYTES)
        torrent_file.chmod(0o400)
        state_dir.chmod(0o100)

        try:
            result = handler._fetch_torrent_file_locally("abc", str(state_dir))

            assert result is not None
            assert base64.b64decode(result) == SAMPLE_TORRENT_BYTES
        finally:
            state_dir.chmod(0o700)
            torrent_file.chmod(0o600)


# ══════════════════════════════════════════════════════════════════════
# TransferConnection.source_config / source_type properties
# ══════════════════════════════════════════════════════════════════════


class TestSourceConfigProperty:
    """Tests for TransferConnection.source_config and source_type."""

    def test_returns_none_when_not_configured(self):
        """Returns None for torrent config without source."""
        config = {
            "transfer_config": {"type": "torrent"},
            "from": "client-a",
            "to": "client-b",
        }
        conn = TransferConnection("test", config, Mock(), Mock())
        assert conn.source_config is None
        assert conn.source_type is None

    def test_returns_sftp_config_when_set(self):
        """Returns the source dict and type 'sftp' when configured."""
        config = {
            "transfer_config": {
                "type": "torrent",
                "source": SAMPLE_SFTP_SOURCE_CONFIG,
            },
            "from": "client-a",
            "to": "client-b",
        }
        conn = TransferConnection("test", config, Mock(), Mock())
        assert conn.source_config == SAMPLE_SFTP_SOURCE_CONFIG
        assert conn.source_type == "sftp"

    def test_returns_local_config_when_set(self):
        """Returns the source dict and type 'local' when configured."""
        config = {
            "transfer_config": {
                "type": "torrent",
                "source": SAMPLE_LOCAL_SOURCE_CONFIG,
            },
            "from": "client-a",
            "to": "client-b",
        }
        conn = TransferConnection("test", config, Mock(), Mock())
        assert conn.source_config == SAMPLE_LOCAL_SOURCE_CONFIG
        assert conn.source_type == "local"

    def test_returns_none_for_file_transfer(self):
        """Returns None for file transfer config (no source key)."""
        config = {
            "transfer_config": {
                "from": {"type": "sftp", "sftp": {"host": "x"}},
                "to": {"type": "local"},
            },
            "from": "client-a",
            "to": "client-b",
        }
        conn = TransferConnection("test", config, Mock(), Mock())
        assert conn.source_config is None
        assert conn.source_type is None


# ══════════════════════════════════════════════════════════════════════
# handle_seeding() — source access paths
# ══════════════════════════════════════════════════════════════════════


class TestHandleSeedingSftpPath:
    """Tests for handle_seeding() using the SFTP .torrent file path."""

    def test_sftp_path_adds_via_torrent_file(self):
        """When source type is sftp, adds original via add_torrent_file."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_SFTP_SOURCE_CONFIG,
            source_type="sftp",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.add_torrent_file.return_value = "added_hash"

        b64_data = base64.b64encode(SAMPLE_TORRENT_BYTES).decode()
        with patch.object(handler, "_fetch_torrent_file_via_sftp", return_value=b64_data):
            result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.to_client.add_torrent_file.assert_called_once()
        # Should NOT use magnet fallback
        conn.from_client.get_magnet_uri.assert_not_called()
        conn.to_client.add_torrent_magnet.assert_not_called()

    def test_sftp_fetch_fails_triggers_retry(self):
        """When SFTP fetch returns None, retries instead of magnet fallback."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_SFTP_SOURCE_CONFIG,
            source_type="sftp",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}

        with patch.object(handler, "_fetch_torrent_file_via_sftp", return_value=None):
            result = handler.handle_seeding(torrent, conn)

        assert result is False
        # Should NOT fall back to magnet
        conn.from_client.get_magnet_uri.assert_not_called()
        conn.to_client.add_torrent_magnet.assert_not_called()
        conn.to_client.add_torrent_file.assert_not_called()
        # Should increment retry count
        assert torrent.transfer["retry_count"] == 1

    def test_sftp_fetch_fails_max_retries_transfer_failed(self):
        """After max SFTP retries, transitions to TRANSFER_FAILED."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42
        torrent.transfer["retry_count"] = handler.MAX_RETRIES - 1  # One more → max

        conn = _make_connection(
            source_config=SAMPLE_SFTP_SOURCE_CONFIG,
            source_type="sftp",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}

        with patch.object(handler, "_fetch_torrent_file_via_sftp", return_value=None):
            result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.state == TorrentState.TRANSFER_FAILED

    def test_no_source_config_uses_magnet_directly(self):
        """Without source config, goes straight to magnet."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(source_config=None, source_type=None)
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = "added_hash"

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        conn.to_client.add_torrent_magnet.assert_called_once()

    def test_sftp_add_torrent_file_returns_none_triggers_retry(self):
        """When add_torrent_file fails (returns None), triggers retry."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()

        conn = _make_connection(
            source_config=SAMPLE_SFTP_SOURCE_CONFIG,
            source_type="sftp",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.add_torrent_file.return_value = None

        b64_data = base64.b64encode(SAMPLE_TORRENT_BYTES).decode()
        with patch.object(handler, "_fetch_torrent_file_via_sftp", return_value=b64_data):
            result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1


class TestHandleSeedingLocalPath:
    """Tests for handle_seeding() using the local .torrent file path."""

    def test_local_path_adds_via_torrent_file(self):
        """When source type is local, adds original via add_torrent_file."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_LOCAL_SOURCE_CONFIG,
            source_type="local",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.add_torrent_file.return_value = "added_hash"

        b64_data = base64.b64encode(SAMPLE_TORRENT_BYTES).decode()
        with patch.object(handler, "_fetch_torrent_file_locally", return_value=b64_data):
            result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.to_client.add_torrent_file.assert_called_once()
        conn.from_client.get_magnet_uri.assert_not_called()

    def test_local_fetch_fails_triggers_retry(self):
        """When local fetch returns None, retries."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_LOCAL_SOURCE_CONFIG,
            source_type="local",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}

        with patch.object(handler, "_fetch_torrent_file_locally", return_value=None):
            result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1
        conn.from_client.get_magnet_uri.assert_not_called()

    def test_local_fetch_fails_max_retries_transfer_failed(self):
        """After max local retries, transitions to TRANSFER_FAILED."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42
        torrent.transfer["retry_count"] = handler.MAX_RETRIES - 1

        conn = _make_connection(
            source_config=SAMPLE_LOCAL_SOURCE_CONFIG,
            source_type="local",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}

        with patch.object(handler, "_fetch_torrent_file_locally", return_value=None):
            result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.state == TorrentState.TRANSFER_FAILED


# ══════════════════════════════════════════════════════════════════════
# _test_sftp_connectivity() helper
# ══════════════════════════════════════════════════════════════════════


class TestSftpConnectivityHelper:
    """Tests for _test_sftp_connectivity()."""

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_success(self, MockSFTP):
        """Returns success when SFTPClient connects."""
        sftp_params = SAMPLE_SFTP_SOURCE_CONFIG["sftp"]
        result = _test_sftp_connectivity(sftp_params)

        assert len(result) == 1
        assert result[0]["component"] == "Source SFTP"
        assert result[0]["success"] is True
        MockSFTP.assert_called_once_with(**sftp_params)

    @patch("transferarr.clients.ftp.SFTPClient", autospec=False)
    def test_failure(self, MockSFTP):
        """Returns failure when SFTPClient raises."""
        MockSFTP.side_effect = Exception("Connection refused")

        result = _test_sftp_connectivity(SAMPLE_SFTP_SOURCE_CONFIG["sftp"])

        assert len(result) == 1
        assert result[0]["component"] == "Source SFTP"
        assert result[0]["success"] is False
        assert "Connection refused" in result[0]["message"]


# ══════════════════════════════════════════════════════════════════════
# _test_local_state_dir() helper
# ══════════════════════════════════════════════════════════════════════


class TestLocalStateDirHelper:
    """Tests for _test_local_state_dir()."""

    def test_success(self, tmp_path):
        """Returns success when directory exists and is readable."""
        result = _test_local_state_dir({"state_dir": str(tmp_path)})

        assert len(result) == 1
        assert result[0]["component"] == "Source Local"
        assert result[0]["success"] is True

    def test_no_state_dir(self):
        """Returns failure when state_dir is not set."""
        result = _test_local_state_dir({})

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "No state_dir" in result[0]["message"]

    def test_dir_not_found(self):
        """Returns failure when directory doesn't exist."""
        result = _test_local_state_dir({"state_dir": "/nonexistent/path"})

        assert len(result) == 1
        assert result[0]["success"] is False
        assert "not found" in result[0]["message"]

    def test_dir_not_accessible(self, tmp_path):
        """Returns failure when directory is not accessible."""
        with patch("transferarr.services.transfer_connection.os.access", return_value=False):
            result = _test_local_state_dir({"state_dir": str(tmp_path)})
            assert len(result) == 1
            assert result[0]["success"] is False
            assert "not accessible" in result[0]["message"]

    def test_execute_only_dir_is_accessible(self, tmp_path):
        """Returns success when the directory is traversable for known child paths."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        state_dir.chmod(0o100)

        try:
            result = _test_local_state_dir({"state_dir": str(state_dir)})

            assert len(result) == 1
            assert result[0]["success"] is True
            assert "Directory accessible" in result[0]["message"]
        finally:
            state_dir.chmod(0o700)


# ══════════════════════════════════════════════════════════════════════
# Password masking / preservation for source.sftp
# ══════════════════════════════════════════════════════════════════════


class TestPasswordMaskingSource:
    """Tests for _mask_sftp_passwords with source.sftp."""

    def test_masks_source_sftp_password(self):
        """source.sftp.password is masked as '***'."""
        from transferarr.web.services.connection_service import _mask_sftp_passwords

        config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h", "password": "secret"}, "state_dir": "/s"},
        }
        result = _mask_sftp_passwords(config)

        assert result["source"]["sftp"]["password"] == "***"
        # Original not mutated
        assert config["source"]["sftp"]["password"] == "secret"

    def test_no_password_not_masked(self):
        """source.sftp without password is left alone."""
        from transferarr.web.services.connection_service import _mask_sftp_passwords

        config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h"}, "state_dir": "/s"},
        }
        result = _mask_sftp_passwords(config)

        assert "password" not in result["source"]["sftp"]

    def test_no_source_unchanged(self):
        """Torrent config without source is returned as-is."""
        from transferarr.web.services.connection_service import _mask_sftp_passwords

        config = {"type": "torrent"}
        result = _mask_sftp_passwords(config)

        assert result == {"type": "torrent"}

    def test_local_source_unchanged(self):
        """Local source config (no sftp) is returned as-is."""
        from transferarr.web.services.connection_service import _mask_sftp_passwords

        config = {
            "type": "torrent",
            "source": {"type": "local", "state_dir": "/s"},
        }
        result = _mask_sftp_passwords(config)

        assert result == config

    def test_file_config_still_masked(self):
        """File transfer from/to SFTP passwords still masked."""
        from transferarr.web.services.connection_service import _mask_sftp_passwords

        config = {
            "from": {"type": "sftp", "sftp": {"host": "h", "password": "s1"}},
            "to": {"type": "sftp", "sftp": {"host": "h2", "password": "s2"}},
        }
        result = _mask_sftp_passwords(config)

        assert result["from"]["sftp"]["password"] == "***"
        assert result["to"]["sftp"]["password"] == "***"


class TestPasswordPreservationSource:
    """Tests for _preserve_sftp_passwords with source.sftp."""

    def _make_service(self):
        from transferarr.web.services.connection_service import ConnectionService
        return ConnectionService(Mock())

    def test_preserves_masked_password(self):
        """Preserves stored password when new value is '***'."""
        svc = self._make_service()
        transfer_config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h", "password": "***"}, "state_dir": "/s"},
        }
        existing = {
            "transfer_config": {
                "type": "torrent",
                "source": {"type": "sftp", "sftp": {"host": "h", "password": "real"}, "state_dir": "/s"},
            }
        }

        result = svc._preserve_sftp_passwords(transfer_config, existing)

        assert result["source"]["sftp"]["password"] == "real"

    def test_preserves_empty_password(self):
        """Preserves stored password when new value is empty."""
        svc = self._make_service()
        transfer_config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h", "password": ""}, "state_dir": "/s"},
        }
        existing = {
            "transfer_config": {
                "type": "torrent",
                "source": {"type": "sftp", "sftp": {"host": "h", "password": "real"}, "state_dir": "/s"},
            }
        }

        result = svc._preserve_sftp_passwords(transfer_config, existing)

        assert result["source"]["sftp"]["password"] == "real"

    def test_uses_new_password_when_provided(self):
        """Uses new password when it's actually provided."""
        svc = self._make_service()
        transfer_config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h", "password": "newpass"}, "state_dir": "/s"},
        }
        existing = {
            "transfer_config": {
                "type": "torrent",
                "source": {"type": "sftp", "sftp": {"host": "h", "password": "old"}, "state_dir": "/s"},
            }
        }

        result = svc._preserve_sftp_passwords(transfer_config, existing)

        assert result["source"]["sftp"]["password"] == "newpass"

    def test_no_existing_password_keeps_empty(self):
        """When no stored password exists, keeps the empty value."""
        svc = self._make_service()
        transfer_config = {
            "type": "torrent",
            "source": {"type": "sftp", "sftp": {"host": "h", "password": ""}, "state_dir": "/s"},
        }
        existing = {"transfer_config": {"type": "torrent"}}

        result = svc._preserve_sftp_passwords(transfer_config, existing)

        assert result["source"]["sftp"]["password"] == ""

    def test_local_source_passthrough(self):
        """Local source config (no sftp) passes through unchanged."""
        svc = self._make_service()
        transfer_config = {
            "type": "torrent",
            "source": {"type": "local", "state_dir": "/s"},
        }
        existing = {"transfer_config": {"type": "torrent"}}

        result = svc._preserve_sftp_passwords(transfer_config, existing)

        assert result["source"]["type"] == "local"
        assert result["source"]["state_dir"] == "/s"


class TestUpdateConnectionPreservesTorrentPassword:
    """Regression: update_connection must call _preserve_sftp_passwords for torrent transfers.

    Before the fix, `update_connection()` guarded password preservation with
    `if not is_torrent_transfer(...)`, so editing a torrent connection with
    SFTP source would silently lose the stored password.
    """

    def _make_service_with_connection(self, stored_password="secret"):
        """Build a ConnectionService with a torrent connection already configured."""
        from transferarr.web.services.connection_service import ConnectionService

        mock_from = Mock()
        mock_from.name = "source-deluge"
        mock_to = Mock()
        mock_to.name = "target-deluge"

        mock_connection = Mock()
        mock_connection.from_client = mock_from
        mock_connection.to_client = mock_to

        tm = Mock()
        tm.download_clients = {"source-deluge": mock_from, "target-deluge": mock_to}
        tm.connections = {"my-conn": mock_connection}
        tm.config = {
            "connections": {
                "my-conn": {
                    "from": "source-deluge",
                    "to": "target-deluge",
                    "transfer_config": {
                        "type": "torrent",
                        "source": {
                            "type": "sftp",
                            "sftp": {"host": "h", "password": stored_password},
                            "state_dir": "/s",
                        },
                    },
                }
            }
        }
        tm.save_config.return_value = True
        return ConnectionService(tm), tm

    def test_update_preserves_empty_password_for_torrent_sftp(self):
        """Editing a torrent connection with empty password preserves stored password."""
        svc, tm = self._make_service_with_connection(stored_password="my_real_pass")

        svc.update_connection("my-conn", {
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
                "source": {
                    "type": "sftp",
                    "sftp": {"host": "h", "password": ""},
                    "state_dir": "/s",
                },
            },
        })

        saved = tm.save_config.call_args[0][0]
        saved_password = saved["connections"]["my-conn"]["transfer_config"]["source"]["sftp"]["password"]
        assert saved_password == "my_real_pass"

    def test_update_preserves_masked_password_for_torrent_sftp(self):
        """Editing a torrent connection with '***' password preserves stored password."""
        svc, tm = self._make_service_with_connection(stored_password="my_real_pass")

        svc.update_connection("my-conn", {
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
                "source": {
                    "type": "sftp",
                    "sftp": {"host": "h", "password": "***"},
                    "state_dir": "/s",
                },
            },
        })

        saved = tm.save_config.call_args[0][0]
        saved_password = saved["connections"]["my-conn"]["transfer_config"]["source"]["sftp"]["password"]
        assert saved_password == "my_real_pass"


# ══════════════════════════════════════════════════════════════════════
# TorrentSourceConfigSchema validation
# ══════════════════════════════════════════════════════════════════════


class TestTorrentSourceConfigSchema:
    """Tests for TorrentSourceConfigSchema cross-field validation."""

    def test_sftp_with_sftp_block(self):
        """type=sftp with sftp block validates."""
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        result = schema.load({
            "type": "sftp",
            "sftp": {"host": "h", "port": 22, "username": "u", "password": "p"},
            "state_dir": "/state",
        })
        assert result["type"] == "sftp"
        assert result["sftp"]["host"] == "h"
        assert result["state_dir"] == "/state"

    def test_sftp_without_sftp_block_fails(self):
        """type=sftp without sftp block raises ValidationError."""
        from marshmallow import ValidationError as MarshmallowValidationError
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        with pytest.raises(MarshmallowValidationError) as exc_info:
            schema.load({"type": "sftp", "state_dir": "/state"})
        assert "sftp" in str(exc_info.value.messages)

    def test_local_without_sftp_block(self):
        """type=local without sftp block validates."""
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        result = schema.load({"type": "local", "state_dir": "/state"})
        assert result["type"] == "local"
        assert result["state_dir"] == "/state"
        assert result.get("sftp") is None

    def test_local_with_sftp_block_fails(self):
        """type=local with sftp block raises ValidationError."""
        from marshmallow import ValidationError as MarshmallowValidationError
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        with pytest.raises(MarshmallowValidationError) as exc_info:
            schema.load({
                "type": "local",
                "sftp": {"host": "h"},
                "state_dir": "/state",
            })
        assert "sftp" in str(exc_info.value.messages)

    def test_state_dir_optional_at_schema_level(self):
        """state_dir is optional at schema level (needed for test connection without it)."""
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        # Should load without error — state_dir defaults to None
        result = schema.load({"type": "local"})
        assert result["state_dir"] is None

    def test_state_dir_required_on_save(self):
        """state_dir is required when saving (require_paths=True in _validate_transfer_config)."""
        from marshmallow import ValidationError as MarshmallowValidationError
        from transferarr.web.schemas import _validate_transfer_config

        # Source without state_dir should fail on save
        with pytest.raises(MarshmallowValidationError) as exc_info:
            _validate_transfer_config(
                {"type": "torrent", "source": {"type": "local"}},
                require_paths=True,
            )
        assert "state_dir" in str(exc_info.value.messages)

    def test_state_dir_not_required_on_test(self):
        """state_dir is not required for connection testing (require_paths=False)."""
        from transferarr.web.schemas import _validate_transfer_config

        # Should not raise — state_dir not checked when require_paths=False
        _validate_transfer_config(
            {"type": "torrent", "source": {"type": "local"}},
            require_paths=False,
        )

    def test_invalid_type_fails(self):
        """Invalid type raises ValidationError."""
        from marshmallow import ValidationError as MarshmallowValidationError
        from transferarr.web.schemas import TorrentSourceConfigSchema

        schema = TorrentSourceConfigSchema()
        with pytest.raises(MarshmallowValidationError):
            schema.load({"type": "invalid", "state_dir": "/state"})


# ══════════════════════════════════════════════════════════════════════
# TorrentTransferConfigSchema with source field
# ══════════════════════════════════════════════════════════════════════


class TestTorrentTransferConfigSchemaSource:
    """Tests for TorrentTransferConfigSchema source field."""

    def test_source_sftp_accepted(self):
        """Schema accepts source with sftp type."""
        from transferarr.web.schemas import TorrentTransferConfigSchema

        data = {
            "type": "torrent",
            "source": {
                "type": "sftp",
                "sftp": {"host": "192.168.1.1", "port": 22, "username": "user", "password": "pass"},
                "state_dir": "/state",
            },
        }
        schema = TorrentTransferConfigSchema()
        result = schema.load(data)

        assert result["source"]["sftp"]["host"] == "192.168.1.1"
        assert result["source"]["state_dir"] == "/state"

    def test_source_local_accepted(self):
        """Schema accepts source with local type."""
        from transferarr.web.schemas import TorrentTransferConfigSchema

        data = {
            "type": "torrent",
            "source": {"type": "local", "state_dir": "/mnt/state"},
        }
        schema = TorrentTransferConfigSchema()
        result = schema.load(data)

        assert result["source"]["type"] == "local"
        assert result["source"]["state_dir"] == "/mnt/state"

    def test_source_optional(self):
        """Schema works without source (defaults to None = magnet-only)."""
        from transferarr.web.schemas import TorrentTransferConfigSchema

        data = {"type": "torrent"}
        schema = TorrentTransferConfigSchema()
        result = schema.load(data)

        assert result.get("source") is None

    def test_source_with_ssh_config(self):
        """Schema accepts source sftp with SSH config fields."""
        from transferarr.web.schemas import TorrentTransferConfigSchema

        data = {
            "type": "torrent",
            "source": {
                "type": "sftp",
                "sftp": {"ssh_config_file": "~/.ssh/config", "ssh_config_host": "myhost"},
                "state_dir": "/state",
            },
        }
        schema = TorrentTransferConfigSchema()
        result = schema.load(data)

        assert result["source"]["sftp"]["ssh_config_host"] == "myhost"

    def test_destination_path_still_works(self):
        """destination_path field still works alongside source."""
        from transferarr.web.schemas import TorrentTransferConfigSchema

        data = {
            "type": "torrent",
            "destination_path": "/custom/downloads",
            "source": {"type": "local", "state_dir": "/s"},
        }
        schema = TorrentTransferConfigSchema()
        result = schema.load(data)

        assert result["destination_path"] == "/custom/downloads"


# ══════════════════════════════════════════════════════════════════════
# Config migration: source_sftp → source
# ══════════════════════════════════════════════════════════════════════


class TestConfigMigration:
    """Tests for source_sftp → source migration in _migrate_connections_config()."""

    def _make_manager(self, config):
        """Create a minimal mock TorrentManager with the given config."""
        from unittest.mock import PropertyMock
        manager = Mock()
        manager.config = config
        manager.save_config = Mock(return_value=True)
        # Bind the real method to our mock
        from transferarr.services.torrent_service import TorrentManager
        manager._migrate_connections_config = TorrentManager._migrate_connections_config.__get__(manager)
        return manager

    def test_migrates_source_sftp_to_source(self):
        """Converts source_sftp flat dict to source nested dict."""
        config = {
            "connections": {
                "conn1": {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {
                        "type": "torrent",
                        "source_sftp": {
                            "host": "h",
                            "port": 22,
                            "username": "u",
                            "password": "p",
                            "state_dir": "/state",
                        },
                    },
                }
            }
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        tc = config["connections"]["conn1"]["transfer_config"]
        assert "source_sftp" not in tc
        assert tc["source"]["type"] == "sftp"
        assert tc["source"]["sftp"] == {"host": "h", "port": 22, "username": "u", "password": "p"}
        assert tc["source"]["state_dir"] == "/state"

    def test_preserves_torrent_config_without_source_sftp(self):
        """Torrent config without source_sftp is left unchanged."""
        config = {
            "connections": {
                "conn1": {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {"type": "torrent"},
                }
            }
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        tc = config["connections"]["conn1"]["transfer_config"]
        assert "source" not in tc
        assert "source_sftp" not in tc

    def test_preserves_file_transfer_config(self):
        """File transfer config is not touched."""
        config = {
            "connections": {
                "conn1": {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {
                        "from": {"type": "local"},
                        "to": {"type": "sftp", "sftp": {"host": "h"}},
                    },
                }
            }
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        tc = config["connections"]["conn1"]["transfer_config"]
        assert "source" not in tc
        assert tc["from"]["type"] == "local"

    def test_handles_source_sftp_without_state_dir(self):
        """Migrates source_sftp even when state_dir is missing."""
        config = {
            "connections": {
                "conn1": {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {
                        "type": "torrent",
                        "source_sftp": {"host": "h", "username": "u"},
                    },
                }
            }
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        tc = config["connections"]["conn1"]["transfer_config"]
        assert tc["source"]["type"] == "sftp"
        assert tc["source"]["sftp"] == {"host": "h", "username": "u"}
        assert "state_dir" not in tc["source"]

    def test_saves_config_after_migration(self):
        """Config is saved after migration."""
        config = {
            "connections": {
                "conn1": {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {
                        "type": "torrent",
                        "source_sftp": {"host": "h", "state_dir": "/s"},
                    },
                }
            }
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        manager.save_config.assert_called_once()

    def test_array_to_dict_still_works(self):
        """Array format migration still works."""
        config = {
            "connections": [
                {"from": "a", "to": "b", "transfer_config": {"type": "torrent"}},
            ]
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        assert isinstance(config["connections"], dict)
        assert "a -> b" in config["connections"]

    def test_combined_array_and_source_sftp_migration(self):
        """Both migrations run together: array→dict + source_sftp→source."""
        config = {
            "connections": [
                {
                    "from": "a",
                    "to": "b",
                    "transfer_config": {
                        "type": "torrent",
                        "source_sftp": {"host": "h", "state_dir": "/s"},
                    },
                },
            ]
        }
        manager = self._make_manager(config)
        manager._migrate_connections_config()

        assert isinstance(config["connections"], dict)
        tc = config["connections"]["a -> b"]["transfer_config"]
        assert "source_sftp" not in tc
        assert tc["source"]["type"] == "sftp"


# ══════════════════════════════════════════════════════════════════════
# DelugeClient.is_private_torrent() — RPC + Web
# ══════════════════════════════════════════════════════════════════════


class TestIsPrivateTorrentRPC:
    """Tests for DelugeClient.is_private_torrent() via RPC."""

    def test_returns_true_for_private_torrent(self):
        """Returns True when torrent has private=True."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrents_status.return_value = {
                b"abc123": {b"private": True}
            }

            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=58846, password="test",
                extra_config={"connection_type": "rpc"}
            )
            client = DelugeClient(config)
            assert client.is_private_torrent("abc123") is True

    def test_returns_false_for_public_torrent(self):
        """Returns False when torrent has private=False."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrents_status.return_value = {
                b"abc123": {b"private": False}
            }

            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=58846, password="test",
                extra_config={"connection_type": "rpc"}
            )
            client = DelugeClient(config)
            assert client.is_private_torrent("abc123") is False

    def test_returns_false_when_field_missing(self):
        """Returns False when torrent not found in response."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrents_status.return_value = {}

            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=58846, password="test",
                extra_config={"connection_type": "rpc"}
            )
            client = DelugeClient(config)
            assert client.is_private_torrent("abc123") is False

    def test_raises_when_not_connected(self):
        """Raises ConnectionError when not connected."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False  # Not connected

            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=58846, password="test",
                extra_config={"connection_type": "rpc"}
            )
            client = DelugeClient(config)

            with pytest.raises(ConnectionError):
                client.is_private_torrent("abc123")


class TestIsPrivateTorrentWeb:
    """Tests for DelugeClient.is_private_torrent() via Web UI."""

    def test_returns_true_for_private_torrent(self):
        """Returns True when Web API returns private=True."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.requests"):
            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=8112, password="test",
                extra_config={"connection_type": "web"}
            )
            client = DelugeClient(config)
            client.ensure_connected = Mock(return_value=True)
            client._send_web_request = Mock(return_value={
                "result": {"torrents": {"abc123": {"private": True}}}
            })

            assert client.is_private_torrent("abc123") is True

    def test_returns_false_for_public_torrent(self):
        """Returns False when Web API returns private=False."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.requests"):
            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=8112, password="test",
                extra_config={"connection_type": "web"}
            )
            client = DelugeClient(config)
            client.ensure_connected = Mock(return_value=True)
            client._send_web_request = Mock(return_value={
                "result": {"torrents": {"abc123": {"private": False}}}
            })

            assert client.is_private_torrent("abc123") is False

    def test_returns_false_when_result_is_none(self):
        """Returns False when Web API returns no result (no torrents)."""
        from transferarr.clients.deluge import DelugeClient

        with patch("transferarr.clients.deluge.requests"):
            from transferarr.clients.config import ClientConfig
            config = ClientConfig(
                name="test", client_type="deluge",
                host="localhost", port=8112, password="test",
                extra_config={"connection_type": "web"}
            )
            client = DelugeClient(config)
            client.ensure_connected = Mock(return_value=True)
            client._send_web_request = Mock(return_value={
                "result": None
            })

            assert client.is_private_torrent("abc123") is False


# ══════════════════════════════════════════════════════════════════════
# handle_seeding() — Private torrent blocking in magnet-only mode
# ══════════════════════════════════════════════════════════════════════


class TestHandleSeedingPrivateTorrentBlocking:
    """Tests for handle_seeding() blocking private torrents when no source access."""

    def test_private_torrent_without_source_sets_transfer_failed(self):
        """Private torrent + no source config → TRANSFER_FAILED."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()

        conn = _make_connection(source_config=None, source_type=None)
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.is_private_torrent.return_value = True

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.state == TorrentState.TRANSFER_FAILED
        # Should NOT attempt magnet or torrent file add
        conn.from_client.get_magnet_uri.assert_not_called()
        conn.to_client.add_torrent_magnet.assert_not_called()
        conn.to_client.add_torrent_file.assert_not_called()

    def test_public_torrent_without_source_uses_magnet(self):
        """Public torrent + no source config → proceeds with magnet."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(source_config=None, source_type=None)
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.is_private_torrent.return_value = False
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = "added_hash"

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.to_client.add_torrent_magnet.assert_called_once()

    def test_private_check_failure_proceeds_with_magnet(self):
        """When is_private_torrent raises, falls back to magnet (graceful)."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(source_config=None, source_type=None)
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.is_private_torrent.side_effect = Exception("RPC error")
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = "added_hash"

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.to_client.add_torrent_magnet.assert_called_once()

    def test_private_torrent_with_sftp_uses_sftp_normally(self):
        """Private torrent + SFTP source → fetches via SFTP (no blocking)."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_SFTP_SOURCE_CONFIG,
            source_type="sftp",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.add_torrent_file.return_value = "added_hash"

        b64_data = base64.b64encode(SAMPLE_TORRENT_BYTES).decode()
        with patch.object(handler, "_fetch_torrent_file_via_sftp", return_value=b64_data):
            result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        # Should NOT check private flag when source is configured
        conn.from_client.is_private_torrent.assert_not_called()

    def test_private_torrent_with_local_uses_local_normally(self):
        """Private torrent + local source → fetches locally (no blocking)."""
        handler = _make_handler()
        torrent = _make_seeding_torrent()
        torrent._transfer_id = 42

        conn = _make_connection(
            source_config=SAMPLE_LOCAL_SOURCE_CONFIG,
            source_type="local",
        )
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.add_torrent_file.return_value = "added_hash"

        b64_data = base64.b64encode(SAMPLE_TORRENT_BYTES).decode()
        with patch.object(handler, "_fetch_torrent_file_locally", return_value=b64_data):
            result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.from_client.is_private_torrent.assert_not_called()
