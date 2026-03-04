"""Unit tests for TorrentManager (torrent_service.py)."""

from unittest.mock import Mock

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.torrent_service import TorrentManager


# ──────────────────────────────────────────────────
# Helpers
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


# ──────────────────────────────────────────────────
# Test _reregister_pending_transfers
# ──────────────────────────────────────────────────

class TestReregisterPendingTransfers:
    """Tests for TorrentManager._reregister_pending_transfers()."""

    def _make_manager(self, torrents, tracker=None, handler=None):
        """Create a minimal mock TorrentManager with the method under test."""
        manager = Mock(spec=TorrentManager)
        manager.torrents = torrents
        manager.tracker = tracker or Mock()
        manager.torrent_transfer_handler = handler or Mock()
        # Bind the real method
        manager._reregister_pending_transfers = TorrentManager._reregister_pending_transfers.__get__(manager)
        return manager

    def test_registers_torrent_downloading_state(self):
        """Re-registers torrent in TORRENT_DOWNLOADING state."""
        torrent = _make_torrent(state=TorrentState.TORRENT_DOWNLOADING)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()
        # Should force re-announce on both clients
        torrent.home_client.force_reannounce.assert_called_once_with(torrent.transfer["hash"])
        torrent.target_client.force_reannounce.assert_called_once_with(torrent.transfer["hash"])

    def test_registers_torrent_creating_state(self):
        """Re-registers torrent in TORRENT_CREATING state."""
        torrent = _make_torrent(state=TorrentState.TORRENT_CREATING)
        torrent.home_client = Mock()
        torrent.target_client = None
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()

    def test_registers_torrent_seeding_state(self):
        """Re-registers torrent in TORRENT_SEEDING state."""
        torrent = _make_torrent(state=TorrentState.TORRENT_SEEDING)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()

    def test_registers_copied_with_uncleaned_transfer(self):
        """Re-registers COPIED torrent with un-cleaned transfer data."""
        torrent = _make_torrent(state=TorrentState.COPIED, cleaned_up=False)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()

    def test_registers_target_checking_with_uncleaned_transfer(self):
        """Re-registers TARGET_CHECKING torrent with un-cleaned transfer data."""
        torrent = _make_torrent(state=TorrentState.TARGET_CHECKING, cleaned_up=False)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()

    def test_skips_copied_with_cleaned_transfer(self):
        """Skips COPIED torrent with cleaned_up=True."""
        torrent = _make_torrent(state=TorrentState.COPIED, cleaned_up=True)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_not_called()

    def test_skips_home_seeding(self):
        """Skips torrent in HOME_SEEDING state."""
        torrent = _make_torrent(state=TorrentState.HOME_SEEDING)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_not_called()

    def test_skips_torrent_without_transfer_hash(self):
        """Skips torrent with no transfer hash."""
        torrent = Torrent(name="Test", id="abc")
        torrent.state = TorrentState.TORRENT_DOWNLOADING
        torrent.transfer = {"on_source": True}  # No "hash" key
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_not_called()

    def test_skips_torrent_without_transfer_data(self):
        """Skips torrent with no transfer data at all."""
        torrent = Torrent(name="Test", id="abc")
        torrent.state = TorrentState.TORRENT_DOWNLOADING
        torrent.transfer = None
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_not_called()

    def test_does_nothing_when_no_tracker(self):
        """Does nothing when tracker is None."""
        manager = Mock(spec=TorrentManager)
        manager.tracker = None
        manager.torrent_transfer_handler = Mock()
        manager.torrents = [_make_torrent()]
        manager._reregister_pending_transfers = TorrentManager._reregister_pending_transfers.__get__(manager)

        manager._reregister_pending_transfers()
        # No error, and no tracker calls

    def test_does_nothing_when_no_handler(self):
        """Does nothing when torrent_transfer_handler is None."""
        manager = Mock(spec=TorrentManager)
        manager.tracker = Mock()
        manager.torrent_transfer_handler = None
        manager.torrents = [_make_torrent()]
        manager._reregister_pending_transfers = TorrentManager._reregister_pending_transfers.__get__(manager)

        manager._reregister_pending_transfers()
        # No error

    def test_multiple_torrents_registered(self):
        """Re-registers multiple torrents."""
        t1 = _make_torrent(name="Movie.1", state=TorrentState.TORRENT_DOWNLOADING,
                           transfer_hash="aa" * 20)
        t1.home_client = Mock()
        t1.target_client = Mock()
        t2 = _make_torrent(name="Movie.2", state=TorrentState.TORRENT_SEEDING,
                           transfer_hash="bb" * 20)
        t2.home_client = Mock()
        t2.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([t1, t2], tracker=tracker)
        manager._reregister_pending_transfers()

        assert tracker.register_transfer.call_count == 2

    def test_reannounce_skipped_when_on_source_false(self):
        """Skips source re-announce when on_source is False."""
        torrent = _make_torrent(state=TorrentState.TORRENT_DOWNLOADING, on_source=False)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        torrent.home_client.force_reannounce.assert_not_called()
        torrent.target_client.force_reannounce.assert_called_once()

    def test_reannounce_skipped_when_on_target_false(self):
        """Skips target re-announce when on_target is False."""
        torrent = _make_torrent(state=TorrentState.TORRENT_DOWNLOADING, on_target=False)
        torrent.home_client = Mock()
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        torrent.home_client.force_reannounce.assert_called_once()
        torrent.target_client.force_reannounce.assert_not_called()

    def test_reannounce_error_does_not_abort(self):
        """Re-announce failure doesn't stop registration."""
        torrent = _make_torrent(state=TorrentState.TORRENT_DOWNLOADING)
        torrent.home_client = Mock()
        torrent.home_client.force_reannounce.side_effect = Exception("conn refused")
        torrent.target_client = Mock()
        tracker = Mock()

        manager = self._make_manager([torrent], tracker=tracker)
        manager._reregister_pending_transfers()

        # Registration succeeded despite re-announce failure
        tracker.register_transfer.assert_called_once()
