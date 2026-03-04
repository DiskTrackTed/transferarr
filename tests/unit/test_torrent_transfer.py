"""Unit tests for torrent-based transfer components."""

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.torrent_transfer import TorrentTransferHandler
from transferarr.services.transfer_connection import (
    get_transfer_type,
    is_torrent_transfer,
    TRANSFER_TYPE_SFTP,
    TRANSFER_TYPE_TORRENT,
    DEFAULT_TRANSFER_TYPE,
)
from transferarr.utils import (
    generate_transfer_id,
    build_transfer_torrent_name,
    parse_magnet_uri,
    build_magnet_uri,
)


# --- Test TorrentState enum ---

class TestTorrentStateEnum:
    """Tests for new torrent transfer states."""
    
    def test_torrent_creating_exists(self):
        """TORRENT_CREATING state exists."""
        assert TorrentState.TORRENT_CREATING.value == 30
    
    def test_torrent_target_adding_exists(self):
        """TORRENT_TARGET_ADDING state exists."""
        assert TorrentState.TORRENT_TARGET_ADDING.value == 31
    
    def test_torrent_downloading_exists(self):
        """TORRENT_DOWNLOADING state exists."""
        assert TorrentState.TORRENT_DOWNLOADING.value == 32
    
    def test_torrent_seeding_exists(self):
        """TORRENT_SEEDING state exists."""
        assert TorrentState.TORRENT_SEEDING.value == 33


# --- Test Torrent model transfer serialization ---

class TestTorrentModelTransferSerialization:
    """Tests for transfer dict serialization in Torrent model."""
    
    def test_torrent_model_transfer_serialization(self):
        """Transfer dict survives to_dict/from_dict."""
        transfer_data = {
            "hash": "abc123def456",
            "name": "[TR-f7e2a1] Test.Movie.2024",
            "retry_count": 0,
            "total_size": 1073741824,
            "on_source": True,
            "on_target": False,
        }
        
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.TORRENT_DOWNLOADING,
            transfer=transfer_data,
        )
        
        # Serialize
        data = torrent.to_dict()
        
        # Verify transfer is in serialized data
        assert "transfer" in data
        assert data["transfer"]["hash"] == "abc123def456"
        assert data["transfer"]["name"] == "[TR-f7e2a1] Test.Movie.2024"
        assert data["transfer"]["retry_count"] == 0
        
        # Deserialize
        restored = Torrent.from_dict(data, download_clients={})
        
        # Verify transfer is restored
        assert restored.transfer is not None
        assert restored.transfer["hash"] == "abc123def456"
        assert restored.transfer["name"] == "[TR-f7e2a1] Test.Movie.2024"
        assert restored.transfer["retry_count"] == 0
        assert restored.transfer["total_size"] == 1073741824
    
    def test_torrent_model_no_transfer_serialization(self):
        """Torrent without transfer dict serializes correctly."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.HOME_SEEDING,
        )
        
        data = torrent.to_dict()
        
        # Transfer should not be in serialized data
        assert "transfer" not in data
    
    def test_torrent_model_transfer_state_preserved(self):
        """Torrent state is preserved with transfer data."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.TORRENT_CREATING,
            transfer={"hash": "xyz789"},
        )
        
        data = torrent.to_dict()
        restored = Torrent.from_dict(data, download_clients={})
        
        assert restored.state == TorrentState.TORRENT_CREATING
    
    def test_display_progress_uses_transfer_data_in_torrent_states(self):
        """Progress from API should reflect transfer progress in TORRENT_* states."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.TORRENT_DOWNLOADING,
            transfer={
                "hash": "xyz789",
                "bytes_downloaded": 50000000,  # 50MB
                "total_size": 100000000,  # 100MB
            },
        )
        # Set home client progress to 100% (source is seeding)
        torrent.progress = 100
        
        data = torrent.to_dict()
        
        # API should show 50% (transfer progress), not 100% (home client progress)
        assert data["progress"] == 50
    
    def test_display_progress_uses_home_client_in_non_torrent_states(self):
        """Progress from API should reflect home client progress in non-TORRENT_* states."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.COPYING,
        )
        torrent.progress = 75
        
        data = torrent.to_dict()
        
        # API should show home client progress
        assert data["progress"] == 75
    
    def test_display_progress_handles_zero_total_size(self):
        """Progress should return 0 if total_size is 0 (avoid division by zero)."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.TORRENT_DOWNLOADING,
            transfer={
                "hash": "xyz789",
                "bytes_downloaded": 0,
                "total_size": 0,
            },
        )
        
        data = torrent.to_dict()
        
        assert data["progress"] == 0
    
    def test_display_transfer_speed_uses_transfer_data(self):
        """Transfer speed should reflect transfer download_rate in TORRENT_* states."""
        torrent = Torrent(
            name="Test.Movie.2024",
            id="original_hash",
            state=TorrentState.TORRENT_DOWNLOADING,
            transfer={
                "hash": "xyz789",
                "download_rate": 5242880,  # 5 MB/s
            },
        )
        # SFTP transfer speed
        torrent.transfer_speed = 1000000
        
        data = torrent.to_dict()
        
        # Should show torrent download rate, not SFTP speed
        assert data["transfer_speed"] == 5242880


# --- Test transfer config type parsing ---

class TestTransferConfigTypeParsing:
    """Tests for transfer config type parsing."""
    
    def test_transfer_config_type_torrent(self):
        """Type 'torrent' detected correctly."""
        config = {"type": "torrent"}
        
        assert get_transfer_type(config) == TRANSFER_TYPE_TORRENT
        assert is_torrent_transfer(config) is True
    
    def test_transfer_config_type_sftp(self):
        """Type 'sftp' detected correctly."""
        config = {"type": "sftp"}
        
        assert get_transfer_type(config) == TRANSFER_TYPE_SFTP
        assert is_torrent_transfer(config) is False
    
    def test_transfer_config_backward_compat_no_type(self):
        """Missing 'type' defaults to SFTP."""
        config = {
            "from": {"type": "local"},
            "to": {"type": "sftp", "sftp": {"host": "example.com"}}
        }
        
        assert get_transfer_type(config) == DEFAULT_TRANSFER_TYPE
        assert get_transfer_type(config) == TRANSFER_TYPE_SFTP
        assert is_torrent_transfer(config) is False
    
    def test_transfer_config_backward_compat_empty(self):
        """Empty config defaults to SFTP."""
        assert get_transfer_type({}) == TRANSFER_TYPE_SFTP
        assert is_torrent_transfer({}) is False
    
    def test_transfer_config_backward_compat_none(self):
        """None config defaults to SFTP."""
        assert get_transfer_type(None) == TRANSFER_TYPE_SFTP
        assert is_torrent_transfer(None) is False


# --- Test magnet URI utilities ---

class TestParseMagnetUri:
    """Tests for parse_magnet_uri function."""
    
    def test_parse_magnet_uri_basic(self):
        """Parse basic magnet URI with hash only."""
        magnet = "magnet:?xt=urn:btih:abc123def456abc123def456abc123def4567890ab"
        
        result = parse_magnet_uri(magnet)
        
        assert result["hash"] == "abc123def456abc123def456abc123def4567890ab"
        assert result["name"] is None
        assert result["trackers"] == []
    
    def test_parse_magnet_uri_with_name(self):
        """Parse magnet URI with display name."""
        magnet = "magnet:?xt=urn:btih:abc123def456abc123def456abc123def4567890ab&dn=Test%20Movie%202024"
        
        result = parse_magnet_uri(magnet)
        
        assert result["hash"] == "abc123def456abc123def456abc123def4567890ab"
        assert result["name"] == "Test Movie 2024"
    
    def test_parse_magnet_uri_with_trackers(self):
        """Parse magnet URI with tracker URLs."""
        magnet = "magnet:?xt=urn:btih:abc123def456abc123def456abc123def4567890ab&tr=http%3A%2F%2Ftracker.example.com%2Fannounce&tr=udp%3A%2F%2Ftracker2.example.com%3A6969"
        
        result = parse_magnet_uri(magnet)
        
        assert result["hash"] == "abc123def456abc123def456abc123def4567890ab"
        assert len(result["trackers"]) == 2
        assert "http://tracker.example.com/announce" in result["trackers"]
        assert "udp://tracker2.example.com:6969" in result["trackers"]
    
    def test_parse_magnet_uri_full(self):
        """Parse complete magnet URI."""
        magnet = "magnet:?xt=urn:btih:abc123def456abc123def456abc123def4567890ab&dn=Test%20Movie&tr=http%3A%2F%2Ftracker.example.com%2Fannounce"
        
        result = parse_magnet_uri(magnet)
        
        assert result["hash"] == "abc123def456abc123def456abc123def4567890ab"
        assert result["name"] == "Test Movie"
        assert len(result["trackers"]) == 1
    
    def test_parse_magnet_uri_invalid(self):
        """Invalid URI raises ValueError."""
        with pytest.raises(ValueError, match="Invalid magnet URI"):
            parse_magnet_uri("http://example.com/torrent")
    
    def test_parse_magnet_uri_uppercase_hash(self):
        """Parse magnet URI with uppercase hash (normalized to lowercase)."""
        magnet = "magnet:?xt=urn:btih:ABC123DEF456ABC123DEF456ABC123DEF4567890AB"
        
        result = parse_magnet_uri(magnet)
        
        assert result["hash"] == "abc123def456abc123def456abc123def4567890ab"


class TestBuildMagnetUri:
    """Tests for build_magnet_uri function."""
    
    def test_build_magnet_uri_hash_only(self):
        """Build magnet URI with hash only."""
        magnet = build_magnet_uri("abc123def456abc123def456abc123def4567890ab")
        
        assert magnet.startswith("magnet:?xt=urn:btih:")
        assert "abc123def456abc123def456abc123def4567890ab" in magnet
    
    def test_build_magnet_uri_with_name(self):
        """Build magnet URI with display name."""
        magnet = build_magnet_uri(
            "abc123def456abc123def456abc123def4567890ab",
            name="Test Movie 2024"
        )
        
        assert "dn=Test%20Movie%202024" in magnet
    
    def test_build_magnet_uri_with_trackers(self):
        """Build magnet URI with tracker URLs."""
        magnet = build_magnet_uri(
            "abc123def456abc123def456abc123def4567890ab",
            trackers=["http://tracker.example.com/announce"]
        )
        
        assert "tr=" in magnet
        assert "tracker.example.com" in magnet
    
    def test_build_magnet_uri_full(self):
        """Build complete magnet URI."""
        magnet = build_magnet_uri(
            "abc123def456abc123def456abc123def4567890ab",
            name="Test Movie",
            trackers=["http://tracker1.example.com/announce", "http://tracker2.example.com/announce"]
        )
        
        assert "xt=urn:btih:abc123def456abc123def456abc123def4567890ab" in magnet
        assert "dn=Test%20Movie" in magnet
        assert magnet.count("tr=") == 2
    
    def test_build_magnet_uri_uppercase_hash_normalized(self):
        """Build magnet URI normalizes hash to lowercase."""
        magnet = build_magnet_uri("ABC123DEF456ABC123DEF456ABC123DEF4567890AB")
        
        assert "abc123def456abc123def456abc123def4567890ab" in magnet


class TestGenerateTransferId:
    """Tests for generate_transfer_id function."""
    
    def test_generate_transfer_id_length(self):
        """Generated ID has correct length."""
        transfer_id = generate_transfer_id()
        
        assert len(transfer_id) == 6
    
    def test_generate_transfer_id_alphanumeric(self):
        """Generated ID contains only lowercase alphanumeric characters."""
        transfer_id = generate_transfer_id()
        
        assert transfer_id.isalnum()
        assert transfer_id.islower()
    
    def test_generate_transfer_id_unique(self):
        """Generated IDs are unique."""
        ids = [generate_transfer_id() for _ in range(100)]
        
        # All 100 should be unique (collision probability is astronomically low)
        assert len(set(ids)) == 100


class TestBuildTransferTorrentName:
    """Tests for build_transfer_torrent_name function."""
    
    def test_build_transfer_torrent_name_with_id(self):
        """Build transfer torrent name with provided ID."""
        name = build_transfer_torrent_name("Test.Movie.2024.1080p", "abc123")
        
        assert name == "[TR-abc123] Test.Movie.2024.1080p"
    
    def test_build_transfer_torrent_name_generates_id(self):
        """Build transfer torrent name generates ID if not provided."""
        name = build_transfer_torrent_name("Test.Movie.2024.1080p")
        
        assert name.startswith("[TR-")
        assert "] Test.Movie.2024.1080p" in name
        # Extract and verify the ID
        id_part = name[4:10]  # [TR-XXXXXX]
        assert len(id_part) == 6
        assert id_part.isalnum()


# --- Test TorrentTransferHandler utility functions ---

class TestIsTransferTorrentName:
    """Tests for is_transfer_torrent_name function."""
    
    def test_is_transfer_torrent_name_true(self):
        """Returns True for transfer torrent names."""
        from transferarr.services.torrent_transfer import is_transfer_torrent_name
        
        assert is_transfer_torrent_name("[TR-abc123] Test.Movie.2024") is True
        assert is_transfer_torrent_name("[TR-f7e2a1] Another.Movie") is True
    
    def test_is_transfer_torrent_name_false(self):
        """Returns False for regular torrent names."""
        from transferarr.services.torrent_transfer import is_transfer_torrent_name
        
        assert is_transfer_torrent_name("Test.Movie.2024.1080p") is False
        assert is_transfer_torrent_name("TR-abc123 Test") is False  # No brackets
        assert is_transfer_torrent_name("[TR abc123] Test") is False  # No dash


class TestGetTransferIdFromName:
    """Tests for get_transfer_id_from_name function."""
    
    def test_get_transfer_id_from_valid_name(self):
        """Extracts transfer ID from valid transfer torrent name."""
        from transferarr.services.torrent_transfer import get_transfer_id_from_name
        
        assert get_transfer_id_from_name("[TR-abc123] Test.Movie") == "abc123"
        assert get_transfer_id_from_name("[TR-f7e2a1] Another.Movie") == "f7e2a1"
    
    def test_get_transfer_id_from_invalid_name(self):
        """Returns None for non-transfer torrent names."""
        from transferarr.services.torrent_transfer import get_transfer_id_from_name
        
        assert get_transfer_id_from_name("Test.Movie.2024") is None
        assert get_transfer_id_from_name("TR-abc123 Test") is None


# --- Test TorrentTransferHandler class ---

class TestTorrentTransferHandler:
    """Tests for TorrentTransferHandler class."""
    
    def test_handler_initialization(self):
        """Handler initializes with tracker and optional services."""
        from unittest.mock import Mock
        from transferarr.services.torrent_transfer import TorrentTransferHandler
        
        mock_tracker = Mock()
        mock_history = Mock()
        
        handler = TorrentTransferHandler(
            tracker=mock_tracker,
            history_service=mock_history,
            history_config={"track_progress": True}
        )
        
        assert handler.tracker == mock_tracker
        assert handler.history_service == mock_history
        assert handler.history_config == {"track_progress": True}
        assert handler.MAX_RETRIES == 3
    
    def test_handler_max_retries_default(self):
        """Handler has default MAX_RETRIES of 3."""
        from unittest.mock import Mock
        from transferarr.services.torrent_transfer import TorrentTransferHandler
        
        handler = TorrentTransferHandler(tracker=Mock())
        
        assert handler.MAX_RETRIES == 3
    
    def test_handle_retry_increments_count(self):
        """_handle_retry increments retry_count."""
        from unittest.mock import Mock
        from transferarr.services.torrent_transfer import TorrentTransferHandler
        
        handler = TorrentTransferHandler(tracker=Mock())
        torrent = Torrent(name="Test", id="abc123")
        torrent.transfer = {"retry_count": 0}
        
        result = handler._handle_retry(torrent)
        
        assert result is False
        assert torrent.transfer["retry_count"] == 1
    
    def test_handle_retry_resets_on_max(self):
        """_handle_retry resets to HOME_SEEDING after MAX_RETRIES."""
        from unittest.mock import Mock
        from transferarr.services.torrent_transfer import TorrentTransferHandler
        
        mock_tracker = Mock()
        handler = TorrentTransferHandler(tracker=mock_tracker)
        torrent = Torrent(name="Test", id="abc123")
        torrent.transfer = {
            "retry_count": 2,  # Will become 3, hitting MAX_RETRIES
            "hash": "abc123def456abc123def456abc123def456789012"  # Valid 40-char hex
        }
        
        result = handler._handle_retry(torrent)
        
        assert result is False
        assert torrent.transfer is None
        assert torrent.state == TorrentState.HOME_SEEDING
        # Verify tracker unregistration was called
        mock_tracker.unregister_transfer.assert_called_once()
    
    def test_register_with_tracker(self):
        """_register_with_tracker converts hex string to bytes."""
        from unittest.mock import Mock
        from transferarr.services.torrent_transfer import TorrentTransferHandler
        
        mock_tracker = Mock()
        handler = TorrentTransferHandler(tracker=mock_tracker)
        
        handler._register_with_tracker("abc123def456")
        
        # Check that register_transfer was called with bytes
        call_args = mock_tracker.register_transfer.call_args[0][0]
        assert isinstance(call_args, bytes)
        assert call_args == bytes.fromhex("abc123def456")


# ──────────────────────────────────────────────────
# Helpers for handler tests
# ──────────────────────────────────────────────────

def _make_torrent(name="Test.Movie.2024", state=TorrentState.TORRENT_DOWNLOADING,
                  transfer_hash="ab" * 20, _transfer_id=None, **transfer_overrides):
    """Create a Torrent with transfer data for testing."""
    t = Torrent(name=name, id="abc123", _transfer_id=_transfer_id)
    t.state = state
    t.transfer = {
        "hash": transfer_hash,
        "on_source": True,
        "on_target": True,
        "retry_count": 0,
        "reannounce_count": 0,
        "bytes_downloaded": 0,
        "total_size": 1024 * 1024 * 100,
        **transfer_overrides,
    }
    return t


def _make_handler(tracker=None, history_service=None, history_config=None):
    """Create a TorrentTransferHandler with optional mocks."""
    return TorrentTransferHandler(
        tracker=tracker or Mock(),
        history_service=history_service,
        history_config=history_config or {},
    )


def _make_connection(from_client=None, to_client=None, destination_path=None):
    """Create a mock TransferConnection."""
    conn = Mock()
    conn.from_client = from_client or Mock()
    conn.to_client = to_client or Mock()
    conn.destination_torrent_download_path = destination_path or "/downloads"
    return conn


# --- Test cleanup_transfer_torrents ---

class TestCleanupTransferTorrents:
    """Tests for TorrentTransferHandler.cleanup_transfer_torrents()."""

    def test_removes_from_target_and_source(self):
        """Removes transfer torrent from both clients."""
        tracker = Mock()
        handler = _make_handler(tracker=tracker)
        torrent = _make_torrent()
        source = Mock()
        target = Mock()

        handler.cleanup_transfer_torrents(torrent, source_client=source, target_client=target)

        target.remove_torrent.assert_called_once_with(torrent.transfer["hash"], remove_data=False)
        source.remove_torrent.assert_called_once_with(torrent.transfer["hash"], remove_data=False)
        tracker.unregister_transfer.assert_called_once()
        assert torrent.transfer["cleaned_up"] is True

    def test_skips_target_when_on_target_false(self):
        """Skips target removal when on_target is False."""
        handler = _make_handler()
        torrent = _make_torrent(on_target=False)
        target = Mock()

        handler.cleanup_transfer_torrents(torrent, source_client=Mock(), target_client=target)

        target.remove_torrent.assert_not_called()

    def test_skips_source_when_on_source_false(self):
        """Skips source removal when on_source is False."""
        handler = _make_handler()
        torrent = _make_torrent(on_source=False)
        source = Mock()

        handler.cleanup_transfer_torrents(torrent, source_client=source, target_client=Mock())

        source.remove_torrent.assert_not_called()

    def test_skips_when_no_transfer_data(self):
        """Does nothing when torrent has no transfer data."""
        handler = _make_handler()
        torrent = Torrent(name="Test", id="abc")
        torrent.transfer = None

        handler.cleanup_transfer_torrents(torrent, source_client=Mock(), target_client=Mock())

    def test_skips_when_no_transfer_hash(self):
        """Does nothing when transfer data has no hash."""
        handler = _make_handler()
        torrent = Torrent(name="Test", id="abc")
        torrent.transfer = {"on_source": True, "on_target": True}

        handler.cleanup_transfer_torrents(torrent, source_client=Mock(), target_client=Mock())

    def test_handles_target_removal_error_gracefully(self):
        """Continues cleanup even if target removal fails."""
        tracker = Mock()
        handler = _make_handler(tracker=tracker)
        torrent = _make_torrent()
        target = Mock()
        target.remove_torrent.side_effect = Exception("connection lost")
        source = Mock()

        handler.cleanup_transfer_torrents(torrent, source_client=source, target_client=target)

        source.remove_torrent.assert_called_once()
        tracker.unregister_transfer.assert_called_once()
        assert torrent.transfer["cleaned_up"] is True

    def test_handles_source_removal_error_gracefully(self):
        """Continues cleanup even if source removal fails."""
        tracker = Mock()
        handler = _make_handler(tracker=tracker)
        torrent = _make_torrent()
        source = Mock()
        source.remove_torrent.side_effect = Exception("connection lost")

        handler.cleanup_transfer_torrents(torrent, source_client=source, target_client=Mock())

        tracker.unregister_transfer.assert_called_once()
        assert torrent.transfer["cleaned_up"] is True

    def test_skips_clients_when_none(self):
        """Skips client removal when clients are None."""
        tracker = Mock()
        handler = _make_handler(tracker=tracker)
        torrent = _make_torrent()

        handler.cleanup_transfer_torrents(torrent, source_client=None, target_client=None)

        tracker.unregister_transfer.assert_called_once()
        assert torrent.transfer["cleaned_up"] is True


# --- Test _cleanup_failed_transfer ---

class TestCleanupFailedTransfer:
    """Tests for TorrentTransferHandler._cleanup_failed_transfer()."""

    def test_calls_cleanup_and_marks_history_failed(self):
        """Cleans up torrents and marks history as failed."""
        history = Mock()
        tracker = Mock()
        handler = _make_handler(tracker=tracker, history_service=history)
        torrent = _make_torrent(_transfer_id=42)
        connection = _make_connection()

        handler._cleanup_failed_transfer(torrent, connection)

        connection.to_client.remove_torrent.assert_called_once()
        connection.from_client.remove_torrent.assert_called_once()
        tracker.unregister_transfer.assert_called_once()

        history.fail_transfer.assert_called_once()
        call_args = history.fail_transfer.call_args
        assert call_args[0][0] == 42
        assert "Max retries" in call_args[0][1]

    def test_no_history_when_no_transfer_id(self):
        """Skips history update when no _transfer_id."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = _make_torrent()

        handler._cleanup_failed_transfer(torrent, _make_connection())

        history.fail_transfer.assert_not_called()

    def test_no_history_when_no_history_service(self):
        """Skips history update when no history service."""
        handler = _make_handler(history_service=None)
        torrent = _make_torrent(_transfer_id=42)

        handler._cleanup_failed_transfer(torrent, _make_connection())

    def test_does_nothing_when_no_transfer_data(self):
        """Does nothing when torrent has no transfer data."""
        handler = _make_handler()
        torrent = Torrent(name="Test", id="abc")
        torrent.transfer = None

        handler._cleanup_failed_transfer(torrent, _make_connection())


# --- Test handle_downloading stall detection ---

class TestHandleDownloadingStall:
    """Tests for stall detection in TorrentTransferHandler.handle_downloading()."""

    def _make_downloading_torrent(self, last_progress_offset_seconds=0,
                                  bytes_downloaded=5000, reannounce_count=0,
                                  **extra_transfer):
        """Create a torrent in TORRENT_DOWNLOADING state with progress timing."""
        now = datetime.now(timezone.utc)
        last_progress = now - timedelta(seconds=last_progress_offset_seconds)
        return _make_torrent(
            state=TorrentState.TORRENT_DOWNLOADING,
            bytes_downloaded=bytes_downloaded,
            reannounce_count=reannounce_count,
            last_progress_at=last_progress.isoformat(),
            total_size=1024 * 1024 * 100,
            **extra_transfer,
        )

    def test_normal_progress_no_stall(self):
        """No stall when progress was recent."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(last_progress_offset_seconds=10)
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 10000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 1024,
        }

        result = handler.handle_downloading(torrent, conn)

        assert result is False
        assert torrent.transfer["bytes_downloaded"] == 10000
        conn.from_client.force_reannounce.assert_not_called()
        conn.to_client.force_reannounce.assert_not_called()

    def test_stall_triggers_reannounce(self):
        """Stall beyond threshold triggers re-announce on both clients."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(last_progress_offset_seconds=360)
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 5000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 0,
        }

        result = handler.handle_downloading(torrent, conn)

        assert result is False
        assert torrent.transfer["reannounce_count"] == 1
        conn.from_client.force_reannounce.assert_called_once()
        conn.to_client.force_reannounce.assert_called_once()

    def test_stall_increments_reannounce_count(self):
        """Each stall detection increments the reannounce counter."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(
            last_progress_offset_seconds=360,
            reannounce_count=1,
        )
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 5000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 0,
        }

        handler.handle_downloading(torrent, conn)

        assert torrent.transfer["reannounce_count"] == 2

    def test_max_reannounce_sets_stalled(self):
        """After max re-announce attempts, sets stalled flag."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(
            last_progress_offset_seconds=360,
            reannounce_count=3,
        )
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 5000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 0,
        }

        result = handler.handle_downloading(torrent, conn)

        assert result is False
        assert torrent.transfer.get("stalled") is True
        conn.from_client.force_reannounce.assert_not_called()

    def test_progress_resets_reannounce_count(self):
        """New progress resets the reannounce counter to 0."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(
            last_progress_offset_seconds=10,
            bytes_downloaded=5000,
            reannounce_count=2,
        )
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 10000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 1024,
        }

        handler.handle_downloading(torrent, conn)

        assert torrent.transfer["reannounce_count"] == 0

    def test_download_complete_transitions_to_seeding(self):
        """Transitions to TORRENT_SEEDING when download is complete."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent()
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 1024 * 1024 * 100,
            "total_size": 1024 * 1024 * 100,
            "state": "Seeding",
            "download_payload_rate": 0,
        }

        result = handler.handle_downloading(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_SEEDING

    def test_missing_torrent_triggers_retry(self):
        """Missing transfer torrent on target triggers retry."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent()
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = None
        conn.to_client.has_torrent.return_value = False

        result = handler.handle_downloading(torrent, conn)

        assert result is False
        assert torrent.transfer.get("on_target") is False
        assert torrent.transfer["retry_count"] == 1

    def test_history_progress_updated(self):
        """History progress is updated when bytes increase."""
        history = Mock()
        handler = _make_handler(
            history_service=history,
            history_config={"track_progress": True},
        )
        torrent = self._make_downloading_torrent(bytes_downloaded=5000)
        torrent._transfer_id = 42
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 50000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 1024,
        }

        handler.handle_downloading(torrent, conn)

        history.update_progress.assert_called_once_with(42, 50000)

    def test_history_progress_not_updated_when_disabled(self):
        """History progress NOT updated when track_progress is False."""
        history = Mock()
        handler = _make_handler(
            history_service=history,
            history_config={"track_progress": False},
        )
        torrent = self._make_downloading_torrent(bytes_downloaded=5000)
        torrent._transfer_id = 42
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 50000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 1024,
        }

        handler.handle_downloading(torrent, conn)

        history.update_progress.assert_not_called()

    def test_no_stall_before_threshold(self):
        """No stall detection when below threshold (4 minutes < 5 minutes)."""
        handler = _make_handler()
        torrent = self._make_downloading_torrent(
            last_progress_offset_seconds=240,
        )
        conn = _make_connection()

        conn.to_client.get_transfer_progress.return_value = {
            "total_done": 5000,
            "total_size": 1024 * 1024 * 100,
            "state": "Downloading",
            "download_payload_rate": 0,
        }

        handler.handle_downloading(torrent, conn)

        conn.from_client.force_reannounce.assert_not_called()
        conn.to_client.force_reannounce.assert_not_called()


# --- Test handle_creating (U1) ---

class TestHandleCreating:
    """Tests for TorrentTransferHandler.handle_creating()."""

    def test_happy_path_creates_torrent_and_transitions(self):
        """Initializes transfer, creates torrent on source, transitions to TARGET_ADDING."""
        history = Mock()
        history.create_transfer.return_value = 99
        handler = _make_handler(history_service=history)
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.size = 100_000
        torrent.state = TorrentState.TORRENT_CREATING
        conn = _make_connection()
        conn.from_client.get_torrent_info.return_value = {
            "save_path": "/downloads",
            "name": "Test.Movie.2024",
            "total_size": 100_000,
        }
        conn.from_client.create_torrent.return_value = "ab" * 20

        result = handler.handle_creating(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_TARGET_ADDING
        assert torrent.transfer is not None
        assert torrent.transfer["hash"] == "ab" * 20
        assert torrent.transfer["on_source"] is True
        conn.from_client.create_torrent.assert_called_once()
        conn.from_client.force_reannounce.assert_called_once_with("ab" * 20)
        handler.tracker.register_transfer.assert_called_once()
        history.create_transfer.assert_called_once()
        history.start_transfer.assert_called_once_with(99)
        assert torrent._transfer_id == 99

    def test_restart_existing_hash_on_source_skips_create(self):
        """When transfer data has hash + on_source=True and exists, skips create_torrent."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        torrent.transfer = {
            "id": "abc123",
            "name": "[TR-abc123] Test.Movie.2024",
            "hash": "ab" * 20,
            "on_source": True,
            "on_target": False,
            "retry_count": 0,
        }
        conn = _make_connection()
        # _get_torrent_by_hash finds it on source
        conn.from_client.has_torrent.return_value = True
        conn.from_client.get_torrent_info.return_value = {"name": "Test.Movie.2024"}

        result = handler.handle_creating(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_TARGET_ADDING
        conn.from_client.create_torrent.assert_not_called()
        handler.tracker.register_transfer.assert_called_once()

    def test_restart_existing_hash_but_torrent_gone_creates_new(self):
        """When transfer data has hash + on_source=True but gone, creates new."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.size = 50_000
        torrent.state = TorrentState.TORRENT_CREATING
        torrent.transfer = {
            "id": "abc123",
            "name": "[TR-abc123] Test.Movie.2024",
            "hash": "ab" * 20,
            "on_source": True,
            "on_target": False,
            "retry_count": 0,
        }
        conn = _make_connection()
        # _get_torrent_by_hash does NOT find it
        conn.from_client.has_torrent.return_value = False
        conn.from_client.get_torrent_info.return_value = {
            "save_path": "/downloads",
            "name": "Test.Movie.2024",
            "total_size": 50_000,
        }
        conn.from_client.create_torrent.return_value = "cd" * 20

        result = handler.handle_creating(torrent, conn)

        assert result is True
        assert torrent.transfer["hash"] == "cd" * 20
        conn.from_client.create_torrent.assert_called_once()

    def test_get_torrent_info_returns_none_triggers_retry(self):
        """When source_client.get_torrent_info() returns None, calls _handle_retry."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        conn = _make_connection()
        conn.from_client.get_torrent_info.return_value = None

        result = handler.handle_creating(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_create_torrent_returns_none_triggers_retry(self):
        """When source_client.create_torrent() returns None, calls _handle_retry."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        conn = _make_connection()
        conn.from_client.get_torrent_info.return_value = {
            "save_path": "/downloads",
            "name": "Test.Movie.2024",
        }
        conn.from_client.create_torrent.return_value = None

        result = handler.handle_creating(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_history_exception_does_not_block_transition(self):
        """History service exception still allows state transition."""
        history = Mock()
        history.create_transfer.side_effect = Exception("DB locked")
        handler = _make_handler(history_service=history)
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        conn = _make_connection()
        conn.from_client.get_torrent_info.return_value = {
            "save_path": "/downloads",
            "name": "Test.Movie.2024",
        }
        conn.from_client.create_torrent.return_value = "ab" * 20

        result = handler.handle_creating(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_TARGET_ADDING

    def test_general_exception_triggers_retry(self):
        """Unexpected exception calls _handle_retry."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        conn = _make_connection()
        conn.from_client.get_torrent_info.side_effect = RuntimeError("boom")

        result = handler.handle_creating(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_uses_existing_transfer_data_on_partial_restart(self):
        """When torrent.transfer is populated (no hash yet), reuses id/name."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_CREATING
        torrent.transfer = {
            "id": "xyz789",
            "name": "[TR-xyz789] Test.Movie.2024",
            "hash": None,
            "on_source": False,
            "on_target": False,
            "retry_count": 0,
        }
        conn = _make_connection()
        conn.from_client.get_torrent_info.return_value = {
            "save_path": "/downloads",
            "name": "Test.Movie.2024",
        }
        conn.from_client.create_torrent.return_value = "ef" * 20

        result = handler.handle_creating(torrent, conn)

        assert result is True
        # Should reuse existing id/name, not generate new ones
        assert torrent.transfer["id"] == "xyz789"
        assert torrent.transfer["name"] == "[TR-xyz789] Test.Movie.2024"
        assert torrent.transfer["hash"] == "ef" * 20


# --- Test handle_target_adding (U2) ---

class TestHandleTargetAdding:
    """Tests for TorrentTransferHandler.handle_target_adding()."""

    def _make_creating_done_torrent(self, **transfer_overrides):
        """Create a torrent ready for handle_target_adding."""
        t = Torrent(name="Test.Movie.2024", id="orig_hash")
        t.state = TorrentState.TORRENT_TARGET_ADDING
        t.transfer = {
            "hash": "ab" * 20,
            "name": "[TR-abc123] Test.Movie.2024",
            "on_source": True,
            "on_target": False,
            "retry_count": 0,
            **transfer_overrides,
        }
        return t

    def test_happy_path_adds_magnet_to_target_and_transitions(self):
        """Gets magnet, adds to target, transitions to TORRENT_DOWNLOADING."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection()
        conn.from_client.get_magnet_uri.return_value = "magnet:?xt=urn:btih:ab" * 2
        conn.to_client.add_torrent_magnet.return_value = "ab" * 20

        result = handler.handle_target_adding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_DOWNLOADING
        assert torrent.transfer["on_target"] is True
        assert torrent.transfer["last_progress_at"] is not None
        conn.from_client.get_magnet_uri.assert_called_once_with("ab" * 20)
        conn.to_client.add_torrent_magnet.assert_called_once()

    def test_no_transfer_data_triggers_retry(self):
        """When torrent.transfer is None, calls _handle_retry."""
        handler = _make_handler()
        torrent = Torrent(name="Test.Movie.2024", id="orig_hash")
        torrent.state = TorrentState.TORRENT_TARGET_ADDING
        torrent.transfer = None

        result = handler.handle_target_adding(torrent, _make_connection())

        assert result is False

    def test_no_hash_triggers_retry(self):
        """When transfer data has no hash, calls _handle_retry."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent(hash=None)

        result = handler.handle_target_adding(torrent, _make_connection())

        assert result is False

    def test_restart_torrent_already_on_target_skips_add(self):
        """When on_target=True and torrent exists, transitions directly."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent(on_target=True)
        conn = _make_connection()
        conn.to_client.has_torrent.return_value = True
        conn.to_client.get_torrent_info.return_value = {"name": "test"}

        result = handler.handle_target_adding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.TORRENT_DOWNLOADING
        conn.from_client.get_magnet_uri.assert_not_called()

    def test_on_target_true_but_torrent_gone_resets_flag(self):
        """When on_target=True but missing from target, resets and re-adds."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent(on_target=True)
        conn = _make_connection()
        conn.to_client.has_torrent.return_value = False
        conn.to_client.get_torrent_info.return_value = None
        conn.from_client.get_magnet_uri.return_value = "magnet:?xt=urn:btih:test"
        conn.to_client.add_torrent_magnet.return_value = "ab" * 20

        result = handler.handle_target_adding(torrent, conn)

        assert result is True
        assert torrent.transfer["on_target"] is True

    def test_get_magnet_uri_returns_none_triggers_retry(self):
        """When source get_magnet_uri returns None, calls _handle_retry."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection()
        conn.from_client.get_magnet_uri.return_value = None

        result = handler.handle_target_adding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_add_torrent_magnet_returns_none_triggers_retry(self):
        """When target add_torrent_magnet returns None, calls _handle_retry."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection()
        conn.from_client.get_magnet_uri.return_value = "magnet:?xt=urn:btih:test"
        conn.to_client.add_torrent_magnet.return_value = None

        result = handler.handle_target_adding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_hash_mismatch_logs_warning_but_continues(self):
        """Hash mismatch still sets on_target and transitions."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection()
        conn.from_client.get_magnet_uri.return_value = "magnet:?xt=urn:btih:test"
        conn.to_client.add_torrent_magnet.return_value = "ff" * 20  # Different hash

        result = handler.handle_target_adding(torrent, conn)

        assert result is True
        assert torrent.transfer["on_target"] is True
        assert torrent.state == TorrentState.TORRENT_DOWNLOADING

    def test_download_location_set_from_connection(self):
        """Passes destination_torrent_download_path as download_location."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection(destination_path="/custom/path")
        conn.from_client.get_magnet_uri.return_value = "magnet:?test"
        conn.to_client.add_torrent_magnet.return_value = "ab" * 20

        handler.handle_target_adding(torrent, conn)

        call_args = conn.to_client.add_torrent_magnet.call_args
        options = call_args[0][1]
        assert options["download_location"] == "/custom/path"

    def test_general_exception_triggers_retry(self):
        """Unexpected exception calls _handle_retry."""
        handler = _make_handler()
        torrent = self._make_creating_done_torrent()
        conn = _make_connection()
        conn.from_client.get_magnet_uri.side_effect = RuntimeError("boom")

        result = handler.handle_target_adding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1


# --- Test handle_seeding (U3) ---

class TestHandleSeeding:
    """Tests for TorrentTransferHandler.handle_seeding()."""

    def _make_seeding_torrent(self, **transfer_overrides):
        """Create a torrent in TORRENT_SEEDING state."""
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

    def test_happy_path_adds_original_and_transitions_to_copied(self):
        """Verifies seeding, adds original magnet, transitions to COPIED."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = self._make_seeding_torrent()
        torrent._transfer_id = 42
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.get_magnet_uri.return_value = "magnet:?original"
        conn.to_client.add_torrent_magnet.return_value = "orig_added_hash"

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        assert torrent.transfer["original_on_target"] is True
        conn.from_client.get_magnet_uri.assert_called_once_with("orig_hash")
        conn.to_client.add_torrent_magnet.assert_called_once()
        history.complete_transfer.assert_called_once_with(42, final_bytes=100_000)

    def test_transfer_torrent_not_seeding_returns_false(self):
        """Returns False when transfer torrent is still downloading."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Downloading"}

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.state == TorrentState.TORRENT_SEEDING  # Unchanged

    def test_transfer_torrent_missing_triggers_retry(self):
        """When get_transfer_progress returns None, triggers retry."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = None

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["on_target"] is False
        assert torrent.transfer["retry_count"] == 1

    def test_original_already_on_target_and_exists_transitions(self):
        """When original_on_target=True and exists, transitions to COPIED."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = self._make_seeding_torrent(original_on_target=True)
        torrent._transfer_id = 10
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.has_torrent.return_value = True

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.state == TorrentState.COPIED
        conn.from_client.get_magnet_uri.assert_not_called()
        history.complete_transfer.assert_called_once()

    def test_original_on_target_but_gone_resets_flag(self):
        """When original_on_target=True but not there, resets and re-adds."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent(original_on_target=True)
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.to_client.has_torrent.return_value = False
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = "added"

        result = handler.handle_seeding(torrent, conn)

        assert result is True
        assert torrent.transfer["original_on_target"] is True

    def test_get_original_magnet_returns_none_triggers_retry(self):
        """When get_magnet_uri for original returns None, triggers retry."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.get_magnet_uri.return_value = None

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_add_original_magnet_returns_none_triggers_retry(self):
        """When add_torrent_magnet for original returns None, triggers retry."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection()
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = None

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_general_exception_triggers_retry(self):
        """Unexpected exception triggers retry."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection()
        conn.to_client.get_transfer_progress.side_effect = RuntimeError("boom")

        result = handler.handle_seeding(torrent, conn)

        assert result is False
        assert torrent.transfer["retry_count"] == 1

    def test_no_transfer_data_triggers_retry(self):
        """Missing transfer data triggers retry."""
        handler = _make_handler()
        torrent = Torrent(name="Test", id="abc")
        torrent.state = TorrentState.TORRENT_SEEDING
        torrent.transfer = None

        result = handler.handle_seeding(torrent, _make_connection())

        assert result is False

    def test_download_location_set_for_original(self):
        """Passes destination_torrent_download_path for original magnet add."""
        handler = _make_handler()
        torrent = self._make_seeding_torrent()
        conn = _make_connection(destination_path="/custom/downloads")
        conn.to_client.get_transfer_progress.return_value = {"state": "Seeding"}
        conn.from_client.get_magnet_uri.return_value = "magnet:?orig"
        conn.to_client.add_torrent_magnet.return_value = "added"

        handler.handle_seeding(torrent, conn)

        call_args = conn.to_client.add_torrent_magnet.call_args
        options = call_args[0][1]
        assert options["download_location"] == "/custom/downloads"


# --- Test _complete_history (U4) ---

class TestCompleteHistory:
    """Tests for TorrentTransferHandler._complete_history()."""

    def test_calls_service_with_correct_args(self):
        """Calls history_service.complete_transfer with transfer_id and total_size."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = _make_torrent(total_size=500_000, _transfer_id=42)

        handler._complete_history(torrent)

        history.complete_transfer.assert_called_once_with(42, final_bytes=500_000)

    def test_no_transfer_id_is_noop(self):
        """Does nothing when torrent._transfer_id is None."""
        history = Mock()
        handler = _make_handler(history_service=history)
        torrent = _make_torrent()
        torrent._transfer_id = None

        handler._complete_history(torrent)

        history.complete_transfer.assert_not_called()

    def test_no_history_service_is_noop(self):
        """Does nothing when history service is None."""
        handler = _make_handler(history_service=None)
        torrent = _make_torrent(_transfer_id=42)

        handler._complete_history(torrent)

    def test_exception_is_swallowed(self):
        """Logs warning but doesn't raise when history_service throws."""
        history = Mock()
        history.complete_transfer.side_effect = Exception("DB error")
        handler = _make_handler(history_service=history)
        torrent = _make_torrent(total_size=100, _transfer_id=42)

        # Should not raise
        handler._complete_history(torrent)


# --- Test _get_torrent_by_hash (U5) ---

class TestGetTorrentByHash:
    """Tests for TorrentTransferHandler._get_torrent_by_hash()."""

    def test_returns_info_when_torrent_exists(self):
        """Returns torrent info dict when client has the torrent."""
        handler = _make_handler()
        client = Mock()
        client.has_torrent.return_value = True
        client.get_torrent_info.return_value = {"name": "test", "state": "Seeding"}

        result = handler._get_torrent_by_hash(client, "abc123")

        assert result == {"name": "test", "state": "Seeding"}
        # Verify a temp Torrent with id=hash was created
        call_args = client.has_torrent.call_args[0][0]
        assert call_args.id == "abc123"

    def test_returns_none_when_torrent_not_found(self):
        """Returns None when client does not have the torrent."""
        handler = _make_handler()
        client = Mock()
        client.has_torrent.return_value = False

        result = handler._get_torrent_by_hash(client, "abc123")

        assert result is None

    def test_returns_none_on_exception(self):
        """Returns None when client raises an exception."""
        handler = _make_handler()
        client = Mock()
        client.has_torrent.side_effect = Exception("connection error")

        result = handler._get_torrent_by_hash(client, "abc123")

        assert result is None