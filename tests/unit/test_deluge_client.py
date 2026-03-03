"""Unit tests for DelugeClient torrent creation and magnet methods.

Tests for Phase 3: Deluge Client Extensions.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, ANY
from transferarr.clients.deluge import DelugeClient
from transferarr.clients.config import ClientConfig


def make_rpc_config(name="test", host="localhost", port=58846, password="test"):
    """Create a ClientConfig for RPC connection."""
    return ClientConfig(
        name=name,
        client_type="deluge",
        host=host,
        port=port,
        password=password,
        extra_config={"connection_type": "rpc"}
    )


def make_web_config(name="test", host="localhost", port=8112, password="test"):
    """Create a ClientConfig for Web connection."""
    return ClientConfig(
        name=name,
        client_type="deluge",
        host=host,
        port=port,
        password=password,
        extra_config={"connection_type": "web"}
    )


class TestCreateTorrent:
    """Tests for create_torrent method."""

    def test_create_torrent_rpc(self):
        """RPC method called with correct params, polls for new hash."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            
            new_hash = "abc123def456"
            # First call: get existing torrents (empty)
            # Second call: poll finds the new torrent
            mock_rpc.core.get_torrents_status.side_effect = [
                {},  # pre-existing check
                {new_hash: {"name": "movie.mkv"}},  # polling finds new torrent
            ]
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with patch("time.sleep"):
                result = client.create_torrent(
                    path="/downloads/movie.mkv",
                    name="Test Movie",
                    trackers=["http://localhost:6969/announce"],
                    private=True,
                    add_to_session=True
                )
            
            # Verify RPC was called with correct params
            # target is dynamic (timestamp-based), so use ANY
            mock_rpc.core.create_torrent.assert_called_once_with(
                "/downloads/movie.mkv",       # path
                "http://localhost:6969/announce",  # tracker (primary)
                262144,                        # piece_length (256KB)
                "",                            # comment
                ANY,                           # target (dynamic timestamp)
                [],                            # webseeds
                True,                          # private
                "transferarr",                 # created_by
                ["http://localhost:6969/announce"],  # trackers list
                True                           # add_to_session
            )
            assert result == new_hash

    def test_create_torrent_returns_hash(self):
        """Returns new info_hash discovered by polling."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            
            new_hash = "fedcba9876543210"
            # Pre-existing empty, then poll finds the new torrent
            mock_rpc.core.get_torrents_status.side_effect = [
                {},  # pre-existing check
                {new_hash: {b"name": b"test"}},  # bytes keys/values from Deluge
            ]
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with patch("time.sleep"):
                result = client.create_torrent(
                    path="/downloads/test",
                    name="Test",
                    trackers=["http://tracker:6969/announce"]
                )
            
            assert result == new_hash
            assert isinstance(result, str)

    def test_create_torrent_raises_on_failure(self):
        """Raises exception when torrent creation times out."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            
            # Pre-existing empty, then polling never finds the torrent
            mock_rpc.core.get_torrents_status.return_value = {}
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with patch("time.sleep"):
                with pytest.raises(Exception) as excinfo:
                    client.create_torrent(
                        path="/downloads/test",
                        name="Test",
                        trackers=["http://tracker:6969/announce"]
                    )
            
            assert "timed out" in str(excinfo.value).lower()

    def test_create_torrent_web(self):
        """Web API called with correct params, polls for new hash."""
        with patch("transferarr.clients.deluge.DelugeRPCClient"):
            with patch.object(DelugeClient, "_connect"):
                client = DelugeClient(make_web_config())
                client.web_authenticated = True
                
                new_hash = "webapi123hash"
                
                def web_side_effect(method, params, **kwargs):
                    if method == "web.update_ui":
                        # Track call count to distinguish pre-existing vs polling
                        web_side_effect.ui_calls += 1
                        if web_side_effect.ui_calls == 1:
                            # Pre-existing check: empty
                            return {"result": {"torrents": {}}}
                        else:
                            # Polling: return new torrent
                            return {"result": {"torrents": {
                                new_hash: {"name": "movie.mkv"}
                            }}}
                    elif method == "core.create_torrent":
                        return {"result": None}
                    return {"result": None}
                
                web_side_effect.ui_calls = 0
                
                with patch.object(client, "_send_web_request") as mock_web:
                    mock_web.side_effect = web_side_effect
                    
                    with patch("time.sleep"):
                        result = client.create_torrent(
                            path="/downloads/movie.mkv",
                            name="Test Movie",
                            trackers=["http://localhost:6969/announce"],
                            private=True,
                            add_to_session=True
                        )
                    
                    # Verify core.create_torrent was called
                    create_calls = [
                        c for c in mock_web.call_args_list
                        if c[0][0] == "core.create_torrent"
                    ]
                    assert len(create_calls) == 1
                    assert result == new_hash


class TestGetMagnetUri:
    """Tests for get_magnet_uri method."""

    def test_get_magnet_uri_returns_string(self):
        """Returns magnet link as string."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            
            expected_magnet = "magnet:?xt=urn:btih:abc123&dn=Test"
            mock_rpc.core.get_magnet_uri.return_value = expected_magnet
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_magnet_uri("abc123")
            
            mock_rpc.core.get_magnet_uri.assert_called_once_with("abc123")
            assert result == expected_magnet

    def test_get_magnet_uri_decodes_bytes(self):
        """Decodes bytes response to string."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            
            mock_rpc.core.get_magnet_uri.return_value = b"magnet:?xt=urn:btih:bytes123"
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_magnet_uri("bytes123")
            
            assert result == "magnet:?xt=urn:btih:bytes123"
            assert isinstance(result, str)

    def test_get_magnet_uri_raises_on_not_found(self):
        """Raises exception when torrent not found."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_magnet_uri.return_value = None
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(Exception) as excinfo:
                client.get_magnet_uri("nonexistent")
            
            assert "Failed to get magnet URI" in str(excinfo.value)


class TestAddTorrentMagnet:
    """Tests for add_torrent_magnet method."""

    def test_add_torrent_magnet_rpc(self):
        """RPC method called correctly with magnet and options."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.add_torrent_magnet.return_value = "added123hash"
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            magnet = "magnet:?xt=urn:btih:abc123&dn=Test"
            options = {"download_location": "/downloads/movies"}
            
            result = client.add_torrent_magnet(magnet, options)
            
            mock_rpc.core.add_torrent_magnet.assert_called_once_with(magnet, options)
            assert result == "added123hash"

    def test_add_torrent_magnet_default_options(self):
        """Uses empty dict when no options provided."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.add_torrent_magnet.return_value = "hash456"
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.add_torrent_magnet("magnet:?xt=urn:btih:test")
            
            # Should use empty dict as default
            mock_rpc.core.add_torrent_magnet.assert_called_once()
            call_args = mock_rpc.core.add_torrent_magnet.call_args
            assert call_args[0][1] == {}
            assert result == "hash456"

    def test_add_torrent_magnet_raises_on_failure(self):
        """Raises exception when adding magnet fails."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.add_torrent_magnet.return_value = None
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(Exception) as excinfo:
                client.add_torrent_magnet("magnet:?xt=urn:btih:invalid")
            
            assert "Failed to add magnet" in str(excinfo.value)


class TestGetTorrentProgressBytes:
    """Tests for get_torrent_progress_bytes method."""

    def test_get_torrent_progress_returns_bytes(self):
        """Returns total_done and total_size in bytes."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrent_status.return_value = {
                "total_done": 1073741824,  # 1 GB done
                "total_size": 4294967296   # 4 GB total
            }
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_torrent_progress_bytes("abc123")
            
            mock_rpc.core.get_torrent_status.assert_called_once_with(
                "abc123",
                ["total_done", "total_size"]
            )
            assert result["total_done"] == 1073741824
            assert result["total_size"] == 4294967296

    def test_get_torrent_progress_handles_zero(self):
        """Handles zero progress correctly."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrent_status.return_value = {
                "total_done": 0,
                "total_size": 1000000
            }
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_torrent_progress_bytes("new_torrent")
            
            assert result["total_done"] == 0
            assert result["total_size"] == 1000000

    def test_get_torrent_progress_raises_on_not_found(self):
        """Raises exception when torrent not found."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrent_status.return_value = {}
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(Exception) as excinfo:
                client.get_torrent_progress_bytes("nonexistent")
            
            assert "not found" in str(excinfo.value)


class TestGetDefaultDownloadPath:
    """Tests for get_default_download_path method."""

    def test_get_default_download_path(self):
        """Returns download_location config value."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_config_value.return_value = "/downloads"
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_default_download_path()
            
            mock_rpc.core.get_config_value.assert_called_once_with("download_location")
            assert result == "/downloads"

    def test_get_default_download_path_decodes_bytes(self):
        """Decodes bytes response to string."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_config_value.return_value = b"/mnt/downloads"
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_default_download_path()
            
            assert result == "/mnt/downloads"
            assert isinstance(result, str)

    def test_get_default_download_path_empty_fallback(self):
        """Returns empty string when config not set."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_config_value.return_value = None
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            result = client.get_default_download_path()
            
            assert result == ""


class TestConnectionRequired:
    """Tests that methods require connection."""

    def test_create_torrent_requires_connection(self):
        """create_torrent raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.create_torrent("/path", "name", ["http://tracker"])

    def test_get_magnet_uri_requires_connection(self):
        """get_magnet_uri raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.get_magnet_uri("abc123")

    def test_add_torrent_magnet_requires_connection(self):
        """add_torrent_magnet raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.add_torrent_magnet("magnet:?xt=urn:btih:test")

    def test_get_torrent_progress_requires_connection(self):
        """get_torrent_progress_bytes raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.get_torrent_progress_bytes("abc123")

    def test_get_default_download_path_requires_connection(self):
        """get_default_download_path raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.get_default_download_path()


# --- Test force_reannounce (U7) ---

class TestForceReannounce:
    """Tests for force_reannounce method."""

    def test_force_reannounce_rpc(self):
        """RPC mode calls core.force_reannounce with list containing hash."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.force_reannounce("abc123def456")

            assert result is True
            mock_rpc.core.force_reannounce.assert_called_once_with(["abc123def456"])

    def test_force_reannounce_web(self):
        """Web mode sends core.force_reannounce request."""
        with patch("transferarr.clients.deluge.DelugeRPCClient"):
            with patch.object(DelugeClient, "_connect"):
                client = DelugeClient(make_web_config())
                client.web_authenticated = True

                with patch.object(client, "_send_web_request") as mock_web:
                    mock_web.return_value = {"result": None, "error": None, "id": 3}

                    result = client.force_reannounce("abc123def456")

                    assert result is True
                    mock_web.assert_called_once_with(
                        "core.force_reannounce",
                        [["abc123def456"]],
                        id=3
                    )

    def test_force_reannounce_returns_false_on_error(self):
        """Returns False when RPC call raises."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.force_reannounce.side_effect = Exception("RPC error")

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.force_reannounce("abc123")

            assert result is False

    def test_force_reannounce_requires_connection(self):
        """Returns False when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.force_reannounce("abc123")

            assert result is False


# --- Test _apply_label (U8) ---

class TestApplyLabel:
    """Tests for _apply_label method."""

    def test_apply_label_rpc_creates_and_sets(self):
        """RPC mode: enables label plugin check, creates label, sets on torrent."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            # get_enabled_plugins returns Label
            mock_rpc.core.get_enabled_plugins.return_value = [b"Label", b"Execute"]
            # get_labels returns empty (label doesn't exist yet)
            mock_rpc.call.side_effect = [
                [],                  # label.get_labels
                None,               # label.add
                None,               # label.set_torrent
            ]

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            client._apply_label("abc123", "transferarr_tmp")

            # Should have called label.add then label.set_torrent
            calls = mock_rpc.call.call_args_list
            assert calls[0][0] == ("label.get_labels",)
            assert calls[1][0] == ("label.add", "transferarr_tmp")
            assert calls[2][0] == ("label.set_torrent", "abc123", "transferarr_tmp")

    def test_apply_label_rpc_skips_when_no_plugin(self):
        """RPC mode: silently skips when Label plugin not enabled."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_enabled_plugins.return_value = [b"Execute"]

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            client._apply_label("abc123", "test_label")

            mock_rpc.call.assert_not_called()

    def test_apply_label_rpc_skips_add_when_label_exists(self):
        """RPC mode: skips label.add when label already exists."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_enabled_plugins.return_value = [b"Label"]
            mock_rpc.call.side_effect = [
                [b"transferarr_tmp"],  # label.get_labels - label exists
                None,                  # label.set_torrent
            ]

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            client._apply_label("abc123", "transferarr_tmp")

            calls = mock_rpc.call.call_args_list
            assert len(calls) == 2
            assert calls[0][0] == ("label.get_labels",)
            assert calls[1][0] == ("label.set_torrent", "abc123", "transferarr_tmp")

    def test_apply_label_exception_is_swallowed(self):
        """Exception during labeling does not propagate."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_enabled_plugins.side_effect = Exception("RPC error")

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            # Should not raise
            client._apply_label("abc123", "test_label")

    def test_apply_label_web_mode(self):
        """Web mode: calls correct web requests for label operations."""
        with patch("transferarr.clients.deluge.DelugeRPCClient"):
            with patch.object(DelugeClient, "_connect"):
                client = DelugeClient(make_web_config())
            client.web_authenticated = True
            client.session = MagicMock()

            # Mock sequential web responses
            mock_responses = []
            for result in [
                ["Label"],           # get_enabled_plugins
                [],                  # label.get_labels (empty)
                None,                # label.add
                None,                # label.set_torrent
            ]:
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {"result": result, "error": None, "id": 1}
                mock_responses.append(resp)

            client.session.post.side_effect = mock_responses

            client._apply_label("abc123", "transferarr_tmp")

            # Verify the web requests
            post_calls = client.session.post.call_args_list
            methods = [c[1].get("json", {}).get("method") or c[0][1]["method"]
                       for c in post_calls if c[1].get("json") or (len(c[0]) > 1)]
            assert "core.get_enabled_plugins" in methods
            assert "label.get_labels" in methods
            assert "label.add" in methods
            assert "label.set_torrent" in methods
