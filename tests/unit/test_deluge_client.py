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


class TestGetAllTorrentsStatus:
    """Tests for get_all_torrents_status field coverage."""

    def test_requests_table_fields_for_rpc(self):
        """RPC status fetch includes seeds and payload-rate fields for the table view."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrents_status.return_value = {
                b"abc123": {
                    b"name": b"Example Torrent",
                    b"state": b"Seeding",
                    b"progress": 100.0,
                    b"save_path": b"/downloads",
                    b"total_size": 123456789,
                    b"time_added": 1700000000,
                    b"trackers": [{b"url": b"http://tracker.example/announce"}],
                    b"num_seeds": 12,
                    b"download_payload_rate": 0,
                    b"upload_payload_rate": 4096,
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.get_all_torrents_status()

            mock_rpc.core.get_torrents_status.assert_called_once_with(
                {},
                [
                    "name",
                    "state",
                    "progress",
                    "save_path",
                    "total_size",
                    "time_added",
                    "trackers",
                    "num_seeds",
                    "download_payload_rate",
                    "upload_payload_rate",
                ],
            )
            assert result == {
                "abc123": {
                    "name": "Example Torrent",
                    "state": "Seeding",
                    "progress": 100.0,
                    "save_path": "/downloads",
                    "total_size": 123456789,
                    "time_added": 1700000000,
                    "trackers": [{"url": "http://tracker.example/announce"}],
                    "num_seeds": 12,
                    "download_payload_rate": 0,
                    "upload_payload_rate": 4096,
                }
            }

    def test_missing_table_fields_do_not_break_status_mapping(self):
        """Missing seeds/rate fields still return the decoded base mapping."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.get_torrents_status.return_value = {
                b"abc123": {
                    b"name": b"Example Torrent",
                    b"state": b"Seeding",
                    b"progress": 100.0,
                    b"save_path": b"/downloads",
                    b"total_size": 123456789,
                    b"time_added": 1700000000,
                    b"trackers": [{b"url": b"http://tracker.example/announce"}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.get_all_torrents_status()

            assert result == {
                "abc123": {
                    "name": "Example Torrent",
                    "state": "Seeding",
                    "progress": 100.0,
                    "save_path": "/downloads",
                    "total_size": 123456789,
                    "time_added": 1700000000,
                    "trackers": [{"url": "http://tracker.example/announce"}],
                }
            }


class TestStartCreateTorrent:
    """Tests for start_create_torrent — fires RPC and returns poll spec."""

    def test_fires_rpc_and_returns_spec(self):
        """RPC called with correct params, returns poll spec dict."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            tracker_url = "http://localhost:6969/announce"
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            spec = client.start_create_torrent(
                path="/downloads/movie.mkv",
                trackers=[tracker_url],
                private=True,
                add_to_session=True,
                total_size=100_000,
            )

            mock_rpc.core.create_torrent.assert_called_once_with(
                "/downloads/movie.mkv",
                tracker_url,
                262144,         # piece_length
                "",             # comment
                ANY,            # target (dynamic)
                [],             # webseeds
                True,           # private
                "transferarr",  # created_by
                [[tracker_url]],  # tracker tiers
                True,           # add_to_session
            )
            assert spec["expected_name"] == "movie.mkv"
            assert spec["tracker_urls"] == [tracker_url]
            assert spec["timeout"] == 30  # 100KB → tiny tier
            assert "started_at" not in spec

    def test_multiple_trackers_as_single_tier(self):
        """Multiple tracker URLs are passed as a single tier (list of lists)."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            trackers = [
                "http://public:6969/announce",
                "http://internal:6969/announce",
            ]
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            spec = client.start_create_torrent(
                path="/downloads/movie.mkv",
                trackers=trackers,
                private=False,
                add_to_session=True,
            )

            mock_rpc.core.create_torrent.assert_called_once_with(
                "/downloads/movie.mkv",
                "http://public:6969/announce",
                262144,
                "",
                ANY,
                [],
                False,
                "transferarr",
                [["http://public:6969/announce", "http://internal:6969/announce"]],
                True,
            )
            assert spec["tracker_urls"] == trackers

    def test_web_mode(self):
        """Web API called with correct params, returns poll spec."""
        with patch("transferarr.clients.deluge.DelugeRPCClient"):
            with patch.object(DelugeClient, "_connect"):
                client = DelugeClient(make_web_config())
                client.web_authenticated = True

                tracker_url = "http://localhost:6969/announce"

                with patch.object(client, "_send_web_request") as mock_web:
                    mock_web.return_value = {"result": None}

                    spec = client.start_create_torrent(
                        path="/downloads/movie.mkv",
                        trackers=[tracker_url],
                        private=True,
                        add_to_session=True,
                    )

                    create_calls = [
                        c for c in mock_web.call_args_list
                        if c[0][0] == "core.create_torrent"
                    ]
                    assert len(create_calls) == 1
                    assert spec["expected_name"] == "movie.mkv"

    def test_rpc_error_raises(self):
        """Exception from RPC propagates."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True
            mock_rpc.core.create_torrent.side_effect = Exception("RPC failed")

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            with pytest.raises(Exception, match="RPC failed"):
                client.start_create_torrent(
                    path="/downloads/test",
                    trackers=["http://tracker:6969/announce"],
                )

    def test_timeout_scales_with_total_size(self):
        """Timeout in returned spec comes from _calculate_create_timeout."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            spec = client.start_create_torrent(
                path="/downloads/big",
                trackers=["http://t:6969/announce"],
                total_size=5 * 1024**3,  # 5GB → 120s tier (≤10GB)
            )
            assert spec["timeout"] == 120


class TestPollCreatedTorrent:
    """Tests for poll_created_torrent — single-shot check for created torrent."""

    def test_finds_match(self):
        """Returns hash when name + tracker match."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            tracker_url = "http://tracker:6969/announce"
            mock_rpc.core.get_torrents_status.return_value = {
                "abc123": {
                    "name": "movie.mkv",
                    "trackers": [{"url": tracker_url}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.poll_created_torrent("movie.mkv", [tracker_url])
            assert result == "abc123"

    def test_no_match_returns_none(self):
        """Returns None when no torrents match."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            mock_rpc.core.get_torrents_status.return_value = {}

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.poll_created_torrent(
                "movie.mkv", ["http://tracker:6969/announce"]
            )
            assert result is None

    def test_ignores_cross_seed_different_tracker(self):
        """Same name but different tracker URL → None."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            mock_rpc.core.get_torrents_status.return_value = {
                "crossseed_hash": {
                    "name": "movie.mkv",
                    "trackers": [{"url": "http://other-tracker.example.com/announce"}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.poll_created_torrent(
                "movie.mkv", ["http://transferarr:6969/announce"]
            )
            assert result is None

    def test_matches_any_of_multiple_tracker_urls(self):
        """Partial tracker overlap still matches."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            external = "http://public:6969/announce"
            internal = "http://internal:6969/announce"
            mock_rpc.core.get_torrents_status.return_value = {
                "dual_hash": {
                    "name": "movie.mkv",
                    "trackers": [{"url": external}, {"url": internal}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.poll_created_torrent("movie.mkv", [external, internal])
            assert result == "dual_hash"

    def test_idempotent_on_retry(self):
        """Finds previously-created transfer torrent (no snapshot needed)."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            our_tracker = "http://transferarr:6969/announce"
            mock_rpc.core.get_torrents_status.return_value = {
                "prev_attempt_hash": {
                    "name": "movie.mkv",
                    "trackers": [{"url": our_tracker}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            result = client.poll_created_torrent("movie.mkv", [our_tracker])
            assert result == "prev_attempt_hash"

    def test_applies_label(self):
        """Calls _apply_label when found and label given."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            tracker_url = "http://tracker:6969/announce"
            mock_rpc.core.get_torrents_status.return_value = {
                "labeled_hash": {
                    "name": "movie.mkv",
                    "trackers": [{"url": tracker_url}],
                }
            }

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            with patch.object(client, "_apply_label") as mock_label:
                result = client.poll_created_torrent(
                    "movie.mkv", [tracker_url], label="transferarr_tmp"
                )

            assert result == "labeled_hash"
            mock_label.assert_called_once_with("labeled_hash", "transferarr_tmp")

    def test_no_label_when_not_found(self):
        """Does not call _apply_label when torrent not found."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = True

            mock_rpc.core.get_torrents_status.return_value = {}

            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc

            with patch.object(client, "_apply_label") as mock_label:
                result = client.poll_created_torrent(
                    "movie.mkv",
                    ["http://tracker:6969/announce"],
                    label="transferarr_tmp",
                )

            assert result is None
            mock_label.assert_not_called()


class TestCalculateCreateTimeout:
    """Tests for _calculate_create_timeout static method."""

    def test_unknown_size_returns_default(self):
        """Unknown size (0) returns the generous default timeout."""
        assert DelugeClient._calculate_create_timeout(0) == 240

    def test_negative_size_returns_default(self):
        """Negative size treated as unknown."""
        assert DelugeClient._calculate_create_timeout(-1) == 240

    def test_tiny_file(self):
        """≤100MB returns shortest timeout."""
        assert DelugeClient._calculate_create_timeout(50 * 1024 * 1024) == 30
        assert DelugeClient._calculate_create_timeout(100 * 1024 * 1024) == 30

    def test_small_file(self):
        """≤1GB returns 60s timeout."""
        assert DelugeClient._calculate_create_timeout(500 * 1024 * 1024) == 60
        assert DelugeClient._calculate_create_timeout(1024 ** 3) == 60

    def test_medium_file(self):
        """≤10GB returns 120s timeout."""
        assert DelugeClient._calculate_create_timeout(5 * 1024 ** 3) == 120
        assert DelugeClient._calculate_create_timeout(10 * 1024 ** 3) == 120

    def test_large_file(self):
        """≤50GB returns 240s timeout."""
        assert DelugeClient._calculate_create_timeout(25 * 1024 ** 3) == 240
        assert DelugeClient._calculate_create_timeout(50 * 1024 ** 3) == 240

    def test_very_large_file(self):
        """>50GB returns maximum timeout."""
        assert DelugeClient._calculate_create_timeout(100 * 1024 ** 3) == 600

    def test_boundary_just_over_100mb(self):
        """Just over 100MB (0.1GB boundary) moves to next tier."""
        # 101MB in bytes = 101 * 1024^2
        just_over = int(0.101 * 1024 ** 3)
        assert DelugeClient._calculate_create_timeout(just_over) == 60


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

    def test_start_create_torrent_requires_connection(self):
        """start_create_torrent raises when not connected."""
        with patch("transferarr.clients.deluge.DelugeRPCClient") as mock_rpc_class:
            mock_rpc = MagicMock()
            mock_rpc_class.return_value = mock_rpc
            mock_rpc.connected = False
            
            client = DelugeClient(make_rpc_config())
            client.rpc_client = mock_rpc
            
            with pytest.raises(ConnectionError):
                client.start_create_torrent("/path", ["http://tracker"])

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
