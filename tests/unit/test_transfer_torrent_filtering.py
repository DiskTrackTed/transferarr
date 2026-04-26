"""Unit tests for transfer torrent filtering.

Tests that transfer torrents are correctly filtered from:
1. Media manager queue processing (prevents them from entering self.torrents)
2. All-client torrent listings (prevents them from appearing on Torrents page)
"""
from unittest.mock import Mock, MagicMock, patch

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.media_managers import RadarrManager, SonarrManager
from transferarr.web.services.torrent_service import TorrentService


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

TRANSFER_HASH = "ab" * 20  # 40-char hex hash


def _make_tracked_torrent(name="Test.Movie.2024", transfer_hash=None, **transfer_overrides):
    """Create a tracked Torrent with optional transfer data."""
    t = Torrent(name=name, id="original_hash_123")
    t.state = TorrentState.TORRENT_DOWNLOADING
    if transfer_hash:
        t.transfer = {
            "hash": transfer_hash,
            "on_source": True,
            "on_target": True,
            **transfer_overrides,
        }
    return t


def _make_queue_item(download_id, title="Some.Movie.2024"):
    """Create a mock Radarr/Sonarr queue item."""
    item = Mock()
    item.download_id = download_id
    item.title = title
    return item


def _make_queue_response(items, total_records=None):
    """Create a mock Radarr/Sonarr queue API response."""
    resp = Mock()
    resp.records = items
    resp.total_records = total_records if total_records is not None else len(items)
    return resp


# ──────────────────────────────────────────────────
# RadarrManager: Transfer torrent filtering
# ──────────────────────────────────────────────────

class TestRadarrSkipsTransferTorrents:
    """Tests that RadarrManager.get_queue_updates() skips transfer torrents."""

    def _make_radarr(self):
        """Create a RadarrManager with mocked API client."""
        with patch.object(RadarrManager, '__init__', lambda self, config: None):
            mgr = RadarrManager.__new__(RadarrManager)
            import logging
            mgr.logger = logging.getLogger("test")
            mgr.config = {}
            mgr.radarr_config = Mock()
            return mgr

    def test_skips_queue_item_matching_transfer_hash(self):
        """Queue item whose download_id matches a tracked transfer hash is skipped."""
        radarr_mgr = self._make_radarr()
        
        # Existing tracked torrent with a transfer hash
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH)
        torrents = [tracked]
        
        # Radarr queue has the transfer torrent
        transfer_item = _make_queue_item(TRANSFER_HASH.upper(), "Transfer.Torrent")
        queue_resp = _make_queue_response([transfer_item])
        
        with patch("radarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("radarr.QueueApi", return_value=mock_queue_api):
                radarr_mgr.get_queue_updates(torrents, Mock())
        
        # Should still only have the original tracked torrent
        assert len(torrents) == 1
        assert torrents[0].name == "Test.Movie.2024"

    def test_adds_normal_queue_item(self):
        """Queue item that is NOT a transfer torrent gets added normally."""
        radarr_mgr = self._make_radarr()
        
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH)
        torrents = [tracked]
        
        normal_item = _make_queue_item("deadbeef" * 5, "Normal.Movie.2024")
        queue_resp = _make_queue_response([normal_item])
        
        with patch("radarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("radarr.QueueApi", return_value=mock_queue_api):
                radarr_mgr.get_queue_updates(torrents, Mock())
        
        # Normal torrent should be added
        assert len(torrents) == 2
        assert torrents[1].name == "Normal.Movie.2024"

    def test_case_insensitive_hash_match(self):
        """Transfer hash comparison is case-insensitive."""
        radarr_mgr = self._make_radarr()
        
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH.lower())
        torrents = [tracked]
        
        # Queue item has uppercase hash
        transfer_item = _make_queue_item(TRANSFER_HASH.upper(), "Transfer.Torrent")
        queue_resp = _make_queue_response([transfer_item])
        
        with patch("radarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("radarr.QueueApi", return_value=mock_queue_api):
                radarr_mgr.get_queue_updates(torrents, Mock())
        
        assert len(torrents) == 1  # Transfer torrent not added

    def test_skips_when_no_transfer_data(self):
        """Torrents without transfer data don't cause errors."""
        radarr_mgr = self._make_radarr()
        
        # Tracked torrent with no transfer
        tracked = Torrent(name="Test", id="abc123")
        tracked.state = TorrentState.HOME_SEEDING
        torrents = [tracked]
        
        normal_item = _make_queue_item("deadbeef" * 5, "New.Movie")
        queue_resp = _make_queue_response([normal_item])
        
        with patch("radarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("radarr.QueueApi", return_value=mock_queue_api):
                radarr_mgr.get_queue_updates(torrents, Mock())
        
        assert len(torrents) == 2  # Normal torrent added

    def test_marks_new_torrent_dirty_only_after_append(self):
        """New queue items are appended before mark_dirty queues persistence."""
        radarr_mgr = self._make_radarr()
        appended_before_dirty = {"value": False}

        class TrackingList(list):
            pass

        torrents = TrackingList()
        normal_item = _make_queue_item("deadbeef" * 5, "Normal.Movie.2024")
        queue_resp = _make_queue_response([normal_item])

        class FakeTorrent:
            def __init__(self, **kwargs):
                self.name = kwargs["name"]
                self.id = kwargs["id"]
                self.transfer = None

            def mark_dirty(self):
                appended_before_dirty["value"] = self in torrents
                assert self in torrents

        with patch("radarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp

            with patch("radarr.QueueApi", return_value=mock_queue_api), \
                 patch("transferarr.services.media_managers.Torrent", FakeTorrent):
                radarr_mgr.get_queue_updates(torrents, Mock())

        assert appended_before_dirty["value"] is True
        assert len(torrents) == 1


# ──────────────────────────────────────────────────
# SonarrManager: Transfer torrent filtering
# ──────────────────────────────────────────────────

class TestSonarrSkipsTransferTorrents:
    """Tests that SonarrManager.get_queue_updates() skips transfer torrents."""

    def _make_sonarr(self):
        """Create a SonarrManager with mocked API client."""
        with patch.object(SonarrManager, '__init__', lambda self, config: None):
            mgr = SonarrManager.__new__(SonarrManager)
            import logging
            mgr.logger = logging.getLogger("test")
            mgr.config = {}
            mgr.sonarr_config = Mock()
            return mgr

    def test_skips_queue_item_matching_transfer_hash(self):
        """Queue item whose download_id matches a tracked transfer hash is skipped."""
        sonarr_mgr = self._make_sonarr()
        
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH)
        torrents = [tracked]
        
        transfer_item = _make_queue_item(TRANSFER_HASH.upper(), "Transfer.Episode")
        queue_resp = _make_queue_response([transfer_item])
        
        with patch("sonarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("sonarr.QueueApi", return_value=mock_queue_api):
                sonarr_mgr.get_queue_updates(torrents, Mock())
        
        assert len(torrents) == 1
        assert torrents[0].name == "Test.Movie.2024"

    def test_adds_normal_queue_item(self):
        """Queue item that is NOT a transfer torrent gets added normally."""
        sonarr_mgr = self._make_sonarr()
        
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH)
        torrents = [tracked]
        
        normal_item = _make_queue_item("deadbeef" * 5, "Normal.Episode.S01E01")
        queue_resp = _make_queue_response([normal_item])
        
        with patch("sonarr.ApiClient") as mock_client_cls:
            mock_ctx = MagicMock()
            mock_client_cls.return_value.__enter__ = Mock(return_value=mock_ctx)
            mock_client_cls.return_value.__exit__ = Mock(return_value=False)
            mock_queue_api = Mock()
            mock_queue_api.get_queue.return_value = queue_resp
            
            with patch("sonarr.QueueApi", return_value=mock_queue_api):
                sonarr_mgr.get_queue_updates(torrents, Mock())
        
        assert len(torrents) == 2
        assert torrents[1].name == "Normal.Episode.S01E01"


# ──────────────────────────────────────────────────
# TorrentService: _get_transfer_hashes
# ──────────────────────────────────────────────────

class TestGetTransferHashes:
    """Tests for TorrentService._get_transfer_hashes()."""

    def _make_service(self, torrents):
        """Create a TorrentService with mock TorrentManager."""
        manager = Mock()
        manager.torrents = torrents
        return TorrentService(manager)

    def test_returns_empty_set_when_no_transfers(self):
        """No transfer data → empty set."""
        t = Torrent(name="Test", id="abc")
        t.state = TorrentState.HOME_SEEDING
        service = self._make_service([t])
        
        assert service._get_transfer_hashes() == set()

    def test_returns_transfer_hashes(self):
        """Collects hashes from torrents with transfer data."""
        t = _make_tracked_torrent(transfer_hash="aabb" * 10)
        service = self._make_service([t])
        
        hashes = service._get_transfer_hashes()
        assert hashes == {"aabb" * 10}

    def test_returns_lowercase_hashes(self):
        """Hashes are normalized to lowercase."""
        t = _make_tracked_torrent(transfer_hash="AABB" * 10)
        service = self._make_service([t])
        
        hashes = service._get_transfer_hashes()
        assert "aabb" * 10 in hashes

    def test_skips_empty_hash(self):
        """Skips torrents with empty transfer hash."""
        t = _make_tracked_torrent(transfer_hash="")
        service = self._make_service([t])
        
        assert service._get_transfer_hashes() == set()

    def test_skips_none_transfer(self):
        """Skips torrents with None transfer dict."""
        t = Torrent(name="Test", id="abc")
        t.state = TorrentState.HOME_SEEDING
        t.transfer = None
        service = self._make_service([t])
        
        assert service._get_transfer_hashes() == set()

    def test_multiple_transfers(self):
        """Collects hashes from multiple torrents."""
        t1 = _make_tracked_torrent(name="Movie1", transfer_hash="aa" * 20)
        t2 = _make_tracked_torrent(name="Movie2", transfer_hash="bb" * 20)
        service = self._make_service([t1, t2])
        
        hashes = service._get_transfer_hashes()
        assert hashes == {"aa" * 20, "bb" * 20}


# ──────────────────────────────────────────────────
# TorrentService: get_all_client_torrents filtering
# ──────────────────────────────────────────────────

class TestAllClientTorrentsFiltering:
    """Tests that get_all_client_torrents() filters transfer torrents."""

    def _make_service(self, torrents, clients):
        """Create a TorrentService with mock clients."""
        manager = Mock()
        manager.torrents = torrents
        manager.download_clients = clients
        return TorrentService(manager)

    def _make_client(self, torrents_dict):
        """Create a mock download client returning the given torrents."""
        client = Mock()
        client.is_connected.return_value = True
        client.get_all_torrents_status.return_value = torrents_dict
        return client

    def test_filters_transfer_hash_from_client(self):
        """Transfer torrent hash is removed from client's torrent listing."""
        transfer_hash = "ab" * 20
        tracked = _make_tracked_torrent(transfer_hash=transfer_hash)
        
        client_torrents = {
            transfer_hash: {"name": "Transfer.Torrent", "state": "Downloading", "progress": 50},
            "cc" * 20: {"name": "Normal.Movie", "state": "Seeding", "progress": 100},
        }
        client = self._make_client(client_torrents)
        
        service = self._make_service([tracked], {"source-deluge": client})
        result = service.get_all_client_torrents()
        
        assert transfer_hash not in result["source-deluge"]
        assert "cc" * 20 in result["source-deluge"]

    def test_no_filtering_when_no_transfers(self):
        """All torrents returned when no active transfers."""
        t = Torrent(name="Test", id="abc")
        t.state = TorrentState.HOME_SEEDING
        
        client_torrents = {
            "aa" * 20: {"name": "Movie.A", "state": "Seeding", "progress": 100},
            "bb" * 20: {"name": "Movie.B", "state": "Seeding", "progress": 100},
        }
        client = self._make_client(client_torrents)
        
        service = self._make_service([t], {"source-deluge": client})
        result = service.get_all_client_torrents()
        
        assert len(result["source-deluge"]) == 2

    def test_case_insensitive_hash_filtering(self):
        """Transfer hash filtering is case-insensitive."""
        transfer_hash_lower = "ab" * 20
        tracked = _make_tracked_torrent(transfer_hash=transfer_hash_lower)
        
        # Deluge returns uppercase hash as key
        client_torrents = {
            transfer_hash_lower.upper(): {"name": "Transfer", "state": "Downloading", "progress": 50},
            "cc" * 20: {"name": "Normal", "state": "Seeding", "progress": 100},
        }
        client = self._make_client(client_torrents)
        
        service = self._make_service([tracked], {"source-deluge": client})
        result = service.get_all_client_torrents()
        
        assert len(result["source-deluge"]) == 1
        assert "cc" * 20 in result["source-deluge"]

    def test_filters_across_multiple_clients(self):
        """Transfer hash is filtered from all clients."""
        transfer_hash = "ab" * 20
        tracked = _make_tracked_torrent(transfer_hash=transfer_hash)
        
        source_torrents = {
            transfer_hash: {"name": "Transfer", "state": "Seeding", "progress": 100},
            "cc" * 20: {"name": "Original", "state": "Seeding", "progress": 100},
        }
        target_torrents = {
            transfer_hash: {"name": "Transfer", "state": "Downloading", "progress": 50},
            "cc" * 20: {"name": "Original", "state": "Checking", "progress": 0},
        }
        
        service = self._make_service(
            [tracked],
            {
                "source-deluge": self._make_client(source_torrents),
                "target-deluge": self._make_client(target_torrents),
            }
        )
        result = service.get_all_client_torrents()
        
        assert transfer_hash not in result["source-deluge"]
        assert transfer_hash not in result["target-deluge"]
        assert "cc" * 20 in result["source-deluge"]
        assert "cc" * 20 in result["target-deluge"]

    def test_disconnected_client_returns_empty(self):
        """Disconnected client returns empty dict (no crash)."""
        tracked = _make_tracked_torrent(transfer_hash=TRANSFER_HASH)
        
        client = Mock()
        client.is_connected.return_value = False
        
        service = self._make_service([tracked], {"source-deluge": client})
        result = service.get_all_client_torrents()
        
        assert result["source-deluge"] == {}
