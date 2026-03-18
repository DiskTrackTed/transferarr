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
        """Re-registers torrent in TORRENT_CREATING state and restores creation slot."""
        torrent = _make_torrent(state=TorrentState.TORRENT_CREATING)
        torrent.home_client = Mock()
        torrent.home_client.name = "source-deluge"
        torrent.target_client = None
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([torrent], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        tracker.register_transfer.assert_called_once()
        assert handler._creating_slots["source-deluge"] == torrent.id

    def test_registers_torrent_create_queue_state(self):
        """Re-registers torrent in TORRENT_CREATE_QUEUE state."""
        torrent = _make_torrent(state=TorrentState.TORRENT_CREATE_QUEUE)
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

    def test_creating_slot_not_restored_for_queue_state(self):
        """TORRENT_CREATE_QUEUE does NOT restore a creation slot."""
        torrent = _make_torrent(state=TorrentState.TORRENT_CREATE_QUEUE)
        torrent.home_client = Mock()
        torrent.home_client.name = "source-deluge"
        torrent.target_client = None
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([torrent], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        assert "source-deluge" not in handler._creating_slots

    def test_creating_slot_not_restored_for_downloading_state(self):
        """TORRENT_DOWNLOADING does NOT restore a creation slot."""
        torrent = _make_torrent(state=TorrentState.TORRENT_DOWNLOADING)
        torrent.home_client = Mock()
        torrent.home_client.name = "source-deluge"
        torrent.target_client = Mock()
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([torrent], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        assert "source-deluge" not in handler._creating_slots

    def test_creating_slot_skipped_when_no_home_client(self):
        """TORRENT_CREATING without home_client does not crash or set slot."""
        torrent = _make_torrent(state=TorrentState.TORRENT_CREATING)
        torrent.home_client = None
        torrent.target_client = None
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([torrent], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        assert handler._creating_slots == {}
        # Transfer hash should still be registered
        tracker.register_transfer.assert_called_once()

    def test_creating_slots_restored_per_client(self):
        """Two TORRENT_CREATING torrents on different clients get separate slots."""
        t1 = _make_torrent(name="Movie.1", state=TorrentState.TORRENT_CREATING,
                           transfer_hash="aa" * 20)
        t1.home_client = Mock()
        t1.home_client.name = "deluge-a"
        t1.target_client = None
        t2 = _make_torrent(name="Movie.2", state=TorrentState.TORRENT_CREATING,
                           transfer_hash="bb" * 20)
        t2.home_client = Mock()
        t2.home_client.name = "deluge-b"
        t2.target_client = None
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([t1, t2], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        assert handler._creating_slots["deluge-a"] == t1.id
        assert handler._creating_slots["deluge-b"] == t2.id
        assert tracker.register_transfer.call_count == 2

    def test_creating_slot_restored_without_transfer_hash(self):
        """TORRENT_CREATING with no transfer hash still restores the slot."""
        torrent = Torrent(name="Test", id="abc123")
        torrent.state = TorrentState.TORRENT_CREATING
        torrent.home_client = Mock()
        torrent.home_client.name = "source-deluge"
        torrent.target_client = None
        torrent.transfer = None  # No transfer data yet (creation in progress)
        tracker = Mock()
        handler = Mock()
        handler._creating_slots = {}

        manager = self._make_manager([torrent], tracker=tracker, handler=handler)
        manager._reregister_pending_transfers()

        # Slot restored even without transfer hash
        assert handler._creating_slots["source-deluge"] == "abc123"
        # But no tracker registration (no hash)
        tracker.register_transfer.assert_not_called()


# ──────────────────────────────────────────────────
# Test update_torrents TRANSFER_FAILED handling
# ──────────────────────────────────────────────────

class TestUpdateTorrentsTransferFailed:
    """Tests for TRANSFER_FAILED state handling in update_torrents()."""

    def _make_manager(self, torrents, download_clients=None):
        """Create a minimal mock TorrentManager."""
        manager = Mock(spec=TorrentManager)
        manager.torrents = torrents
        manager.download_clients = download_clients or {}
        manager.connections = {}
        manager.torrent_transfer_handler = None
        # Bind the real method
        manager.update_torrents = TorrentManager.update_torrents.__get__(manager)
        return manager

    def test_transfer_failed_is_skipped(self):
        """TRANSFER_FAILED torrents should not be processed (sticky state)."""
        torrent = Torrent(name="Failed.Movie.2024", id="abc123")
        torrent.state = TorrentState.TRANSFER_FAILED
        
        manager = self._make_manager([torrent])
        manager.update_torrents()
        
        # Torrent should still be in TRANSFER_FAILED (not touched)
        assert torrent.state == TorrentState.TRANSFER_FAILED
        # Should still be in the list (not removed)
        assert torrent in manager.torrents

    def test_transfer_failed_not_checked_against_clients(self):
        """TRANSFER_FAILED torrents should not query download clients."""
        torrent = Torrent(name="Failed.Movie.2024", id="abc123")
        torrent.state = TorrentState.TRANSFER_FAILED
        
        mock_client = Mock()
        manager = self._make_manager([torrent], download_clients={"test": mock_client})
        manager.update_torrents()
        
        # Client should never be queried for this torrent
        mock_client.has_torrent.assert_not_called()
        mock_client.get_torrent_state.assert_not_called()


# ──────────────────────────────────────────────────
# Test _should_delete_cross_seeds
# ──────────────────────────────────────────────────

class TestShouldDeleteCrossSeeds:
    """Tests for TorrentManager._should_delete_cross_seeds()."""

    def _make_manager(self):
        manager = Mock(spec=TorrentManager)
        manager._should_delete_cross_seeds = TorrentManager._should_delete_cross_seeds.__get__(manager)
        return manager

    def test_manual_transfer_true(self):
        """Manual transfer with delete_source_cross_seeds=True returns True."""
        manager = self._make_manager()
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=True)
        torrent.home_client = Mock()
        assert manager._should_delete_cross_seeds(torrent) is True

    def test_manual_transfer_false(self):
        """Manual transfer with delete_source_cross_seeds=False returns False."""
        manager = self._make_manager()
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=False)
        torrent.home_client = Mock()
        assert manager._should_delete_cross_seeds(torrent) is False

    def test_auto_transfer_uses_client_config_true(self):
        """Automatic transfer looks up current client in download_clients dict."""
        manager = self._make_manager()
        client = Mock()
        client.name = "source-deluge"
        client.delete_cross_seeds = True
        manager.download_clients = {"source-deluge": client}
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=None)
        torrent.set_home_client(client)
        assert manager._should_delete_cross_seeds(torrent) is True

    def test_auto_transfer_uses_client_config_false(self):
        """Automatic transfer looks up current client in download_clients dict."""
        manager = self._make_manager()
        client = Mock()
        client.name = "source-deluge"
        client.delete_cross_seeds = False
        manager.download_clients = {"source-deluge": client}
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=None)
        torrent.set_home_client(client)
        assert manager._should_delete_cross_seeds(torrent) is False

    def test_auto_transfer_picks_up_runtime_config_change(self):
        """Preferred path: uses download_clients dict, not stale torrent.home_client."""
        manager = self._make_manager()
        # Original client at set_home_client time had delete_cross_seeds=True
        original_client = Mock()
        original_client.name = "source-deluge"
        original_client.delete_cross_seeds = True
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=None)
        torrent.set_home_client(original_client)
        # Runtime config changed: new client instance with delete_cross_seeds=False
        updated_client = Mock()
        updated_client.name = "source-deluge"
        updated_client.delete_cross_seeds = False
        manager.download_clients = {"source-deluge": updated_client}
        # Should use updated_client (from dict), not stale original_client
        assert manager._should_delete_cross_seeds(torrent) is False

    def test_auto_transfer_fallback_when_client_not_in_dict(self):
        """Fallback: uses torrent.home_client when client not in download_clients."""
        manager = self._make_manager()
        manager.download_clients = {}  # Client removed from runtime config
        torrent = Torrent(name="Test", id="abc", delete_source_cross_seeds=None)
        torrent.home_client = Mock()
        torrent.home_client.delete_cross_seeds = True
        assert manager._should_delete_cross_seeds(torrent) is True


# ──────────────────────────────────────────────────
# Test _remove_source_cross_seeds
# ──────────────────────────────────────────────────

class TestSourceCrossSeedRemoval:
    """Tests for TorrentManager._remove_source_cross_seeds()."""

    def _make_manager(self, tracked_torrents=None, download_clients=None):
        """Create a minimal mock TorrentManager with the real methods."""
        manager = Mock(spec=TorrentManager)
        manager._remove_source_cross_seeds = TorrentManager._remove_source_cross_seeds.__get__(manager)
        manager._should_delete_cross_seeds = TorrentManager._should_delete_cross_seeds.__get__(manager)
        manager.torrents = tracked_torrents or []
        manager.download_clients = download_clients or {}
        return manager

    def _make_torrent_with_siblings(self, torrent_hash="hash_orig",
                                    name="Movie.2024.1080p", total_size=1000,
                                    sibling_hashes=None, delete_flag=True):
        """Create a torrent and mock client with cross-seed siblings.

        Returns (torrent, home_client, all_torrents_data).
        """
        torrent = Torrent(
            name=name, id=torrent_hash,
            delete_source_cross_seeds=delete_flag,
        )
        all_data = {
            torrent_hash: {
                "name": name,
                "total_size": total_size,
                "state": "Seeding",
            }
        }
        for sib in (sibling_hashes or []):
            all_data[sib] = {
                "name": name,
                "total_size": total_size,
                "state": "Seeding",
            }

        client = Mock()
        client.name = "source-deluge"
        client.get_all_torrents_status.return_value = all_data
        client.delete_cross_seeds = True
        torrent.set_home_client(client)
        return torrent, client, all_data

    def test_removes_single_sibling(self):
        """A single cross-seed sibling is removed with remove_data=True."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1"],
        )
        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_called_once_with("hash_sib1", remove_data=True)

    def test_removes_multiple_siblings(self):
        """All cross-seed siblings are removed."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1", "hash_sib2", "hash_sib3"],
        )
        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        assert client.remove_torrent.call_count == 3
        removed_hashes = {call.args[0] for call in client.remove_torrent.call_args_list}
        assert removed_hashes == {"hash_sib1", "hash_sib2", "hash_sib3"}

    def test_no_removal_when_no_siblings(self):
        """No removal calls when there are no cross-seed siblings."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=[],
        )
        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()

    def test_skipped_when_flag_false(self):
        """No removal when delete_source_cross_seeds is False."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1"],
            delete_flag=False,
        )
        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()
        client.get_all_torrents_status.assert_not_called()

    def test_uses_client_config_when_flag_none(self):
        """Uses current client's delete_cross_seeds when per-transfer flag is None."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1"],
            delete_flag=None,
        )
        client.delete_cross_seeds = True
        manager = self._make_manager(download_clients={"source-deluge": client})
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_called_once_with("hash_sib1", remove_data=True)

    def test_skipped_when_client_config_false(self):
        """No removal when client.delete_cross_seeds is False and per-transfer flag is None."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1"],
            delete_flag=None,
        )
        client.delete_cross_seeds = False
        manager = self._make_manager(download_clients={"source-deluge": client})
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()

    def test_different_name_not_removed(self):
        """Torrents with different names are NOT removed."""
        torrent, client, all_data = self._make_torrent_with_siblings(
            sibling_hashes=[],
        )
        # Add a torrent with different name
        all_data["hash_other"] = {
            "name": "Different.Movie.2023",
            "total_size": 1000,
            "state": "Seeding",
        }
        client.get_all_torrents_status.return_value = all_data

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()

    def test_different_size_not_removed(self):
        """Torrents with same name but different size are NOT removed."""
        torrent, client, all_data = self._make_torrent_with_siblings(
            sibling_hashes=[],
        )
        # Same name, different size
        all_data["hash_other"] = {
            "name": "Movie.2024.1080p",
            "total_size": 9999,
            "state": "Seeding",
        }
        client.get_all_torrents_status.return_value = all_data

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()

    def test_error_on_get_status_does_not_raise(self):
        """Exception in get_all_torrents_status is caught, no crash."""
        torrent = Torrent(name="Test", id="hash1", delete_source_cross_seeds=True)
        client = Mock()
        client.get_all_torrents_status.side_effect = Exception("Connection lost")
        torrent.home_client = client

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)  # Should not raise

    def test_error_on_remove_does_not_crash(self):
        """Exception removing a single sibling doesn't prevent removing others."""
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1", "hash_sib2"],
        )
        client.remove_torrent.side_effect = [Exception("RPC error"), None]

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

        # Both removal attempts were made
        assert client.remove_torrent.call_count == 2

    def test_none_all_torrents_does_not_crash(self):
        """get_all_torrents_status returning None doesn't crash."""
        torrent = Torrent(name="Test", id="hash1", delete_source_cross_seeds=True)
        client = Mock()
        client.get_all_torrents_status.return_value = None
        torrent.home_client = client

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)  # Should not raise
        client.remove_torrent.assert_not_called()

    def test_torrent_not_in_listing_does_not_crash(self):
        """If the torrent itself isn't in the listing, no crash."""
        torrent = Torrent(name="Test", id="hash1", delete_source_cross_seeds=True)
        client = Mock()
        client.get_all_torrents_status.return_value = {
            "other_hash": {"name": "Test", "total_size": 100},
        }
        torrent.home_client = client

        manager = self._make_manager()
        manager._remove_source_cross_seeds(torrent)

    def test_skips_sibling_currently_tracked_for_transfer(self):
        """Siblings in self.torrents (being transferred) are not removed."""
        # Create a sibling that IS currently tracked for transfer
        tracked_sibling = Torrent(name="Movie.2024.1080p", id="hash_sib1")
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1", "hash_sib2"],
        )
        manager = self._make_manager(tracked_torrents=[tracked_sibling])
        manager._remove_source_cross_seeds(torrent)

        # Only hash_sib2 should be removed; hash_sib1 is tracked
        client.remove_torrent.assert_called_once_with("hash_sib2", remove_data=True)

    def test_skips_all_siblings_when_all_tracked(self):
        """No removal when all siblings are currently tracked for transfer."""
        tracked1 = Torrent(name="Movie.2024.1080p", id="hash_sib1")
        tracked2 = Torrent(name="Movie.2024.1080p", id="hash_sib2")
        torrent, client, _ = self._make_torrent_with_siblings(
            sibling_hashes=["hash_sib1", "hash_sib2"],
        )
        manager = self._make_manager(tracked_torrents=[tracked1, tracked2])
        manager._remove_source_cross_seeds(torrent)

        client.remove_torrent.assert_not_called()
        client.remove_torrent.assert_not_called()


# ──────────────────────────────────────────────────
# Test early private torrent gate
# ──────────────────────────────────────────────────

class TestPrivateTorrentEarlyGate:
    """Tests for the early private torrent check before TORRENT_CREATE_QUEUE.

    When a torrent-based connection has no source access (magnet-only)
    and the original torrent is private, the torrent should immediately
    transition to TRANSFER_FAILED instead of entering the transfer pipeline.
    """

    def _make_manager_for_update(self, torrent, connection, handler=None):
        """Create a minimal TorrentManager to test update_torrents() HOME_SEEDING path."""
        manager = Mock(spec=TorrentManager)
        manager.torrents = [torrent]
        manager.connections = {"test-conn": connection}
        manager.torrent_transfer_handler = handler or Mock()
        manager.tracker = Mock()
        manager.media_managers = []
        manager.download_clients = {connection.from_client.name: connection.from_client}
        manager.running = False  # single iteration
        manager.update_torrents = TorrentManager.update_torrents.__get__(manager)
        return manager

    def _make_seeding_torrent(self, home_client_name="source-deluge",
                              target_client_name="target-deluge"):
        """Create a HOME_SEEDING torrent with home/target clients set."""
        t = Torrent(name="Test.Movie.2024", id="orig_hash")
        t.state = TorrentState.HOME_SEEDING
        home = Mock()
        home.name = home_client_name
        home.has_torrent.return_value = True
        home.get_torrent_state.return_value = TorrentState.HOME_SEEDING
        home.get_torrent_info.return_value = {
            "name": "Test.Movie.2024",
            "total_size": 1024 * 1024 * 100,
            "progress": 100,
            "state": "Seeding",
            "save_path": "/downloads",
        }
        t.set_home_client(home)
        target = Mock()
        target.name = target_client_name
        target.has_torrent.return_value = False  # not yet on target
        t.set_target_client(target)
        t.media_manager = Mock()
        return t

    def _make_torrent_connection(self, from_name="source-deluge",
                                 to_name="target-deluge",
                                 source_type=None):
        """Create a mock TransferConnection for torrent transfers."""
        conn = Mock()
        conn.from_client = Mock()
        conn.from_client.name = from_name
        conn.to_client = Mock()
        conn.to_client.name = to_name
        conn.is_torrent_transfer = True
        conn.source_type = source_type
        conn.name = "test-conn"
        return conn

    def test_private_torrent_magnet_only_sets_transfer_failed(self):
        """Private torrent in magnet-only mode goes straight to TRANSFER_FAILED."""
        torrent = self._make_seeding_torrent()
        conn = self._make_torrent_connection(source_type=None)
        torrent.home_client.is_private_torrent.return_value = True

        manager = self._make_manager_for_update(torrent, conn)
        manager.update_torrents()

        assert torrent.state == TorrentState.TRANSFER_FAILED

    def test_private_torrent_magnet_only_skips_create_queue(self):
        """Private torrent in magnet-only mode never reaches TORRENT_CREATE_QUEUE."""
        torrent = self._make_seeding_torrent()
        conn = self._make_torrent_connection(source_type=None)
        torrent.home_client.is_private_torrent.return_value = True

        manager = self._make_manager_for_update(torrent, conn)
        manager.update_torrents()

        # Should not have entered the create queue
        assert torrent.state != TorrentState.TORRENT_CREATE_QUEUE

    def test_non_private_torrent_magnet_only_proceeds(self):
        """Non-private torrent in magnet-only mode proceeds to TORRENT_CREATE_QUEUE."""
        torrent = self._make_seeding_torrent()
        conn = self._make_torrent_connection(source_type=None)
        torrent.home_client.is_private_torrent.return_value = False

        manager = self._make_manager_for_update(torrent, conn)
        manager.update_torrents()

        assert torrent.state == TorrentState.TORRENT_CREATE_QUEUE

    def test_private_torrent_with_source_access_proceeds(self):
        """Private torrent with source access configured proceeds normally."""
        torrent = self._make_seeding_torrent()
        conn = self._make_torrent_connection(source_type="sftp")
        # Private flag shouldn't even be checked
        torrent.home_client.is_private_torrent.return_value = True

        manager = self._make_manager_for_update(torrent, conn)
        manager.update_torrents()

        assert torrent.state == TorrentState.TORRENT_CREATE_QUEUE
        torrent.home_client.is_private_torrent.assert_not_called()

    def test_private_check_exception_allows_proceed(self):
        """Exception during private check allows torrent to proceed (re-checked later)."""
        torrent = self._make_seeding_torrent()
        conn = self._make_torrent_connection(source_type=None)
        torrent.home_client.is_private_torrent.side_effect = RuntimeError("RPC error")

        manager = self._make_manager_for_update(torrent, conn)
        manager.update_torrents()

        # Should proceed despite the error (will be re-checked in handle_seeding)
        assert torrent.state == TorrentState.TORRENT_CREATE_QUEUE


class TestPrivateTorrentEarlyGateManualTransfer:
    """Tests for the early private torrent check in create_manual_transfers()."""

    def _make_manager(self, handler=None):
        """Create a minimal TorrentManager for testing create_manual_transfers."""
        manager = Mock(spec=TorrentManager)
        manager.torrents = []
        manager.torrent_transfer_handler = handler or Mock()
        manager.save_torrents_state = Mock()
        manager.create_manual_transfers = TorrentManager.create_manual_transfers.__get__(manager)
        return manager

    def _make_source_client(self, torrent_info=None):
        """Create a mock source client."""
        client = Mock()
        client.name = "source-deluge"
        client.get_torrent_info.return_value = torrent_info or {
            "name": "Test.Movie.2024",
            "total_size": 1024 * 1024 * 100,
            "progress": 100,
        }
        return client

    def _make_torrent_connection(self, source_type=None):
        """Create a mock torrent TransferConnection."""
        conn = Mock()
        conn.is_torrent_transfer = True
        conn.source_type = source_type
        conn.name = "test-conn"
        return conn

    def test_private_torrent_magnet_only_returns_error(self):
        """Private torrent in magnet-only mode returns error in summary."""
        manager = self._make_manager()
        client = self._make_source_client()
        client.is_private_torrent.return_value = True
        conn = self._make_torrent_connection(source_type=None)

        result = manager.create_manual_transfers(
            ["abc123"], client, Mock(), conn
        )

        assert result["total_errors"] == 1
        assert result["total_initiated"] == 0
        assert "Private" in result["errors"][0]["error"] or "private" in result["errors"][0]["error"].lower()

    def test_private_torrent_magnet_only_not_tracked(self):
        """Private torrent in magnet-only mode is removed from tracked list."""
        manager = self._make_manager()
        client = self._make_source_client()
        client.is_private_torrent.return_value = True
        conn = self._make_torrent_connection(source_type=None)

        manager.create_manual_transfers(["abc123"], client, Mock(), conn)

        # Should have been removed from tracked torrents
        assert len(manager.torrents) == 0

    def test_non_private_torrent_magnet_only_succeeds(self):
        """Non-private torrent in magnet-only mode is initiated normally."""
        manager = self._make_manager()
        client = self._make_source_client()
        client.is_private_torrent.return_value = False
        conn = self._make_torrent_connection(source_type=None)

        result = manager.create_manual_transfers(
            ["abc123"], client, Mock(), conn
        )

        assert result["total_initiated"] == 1
        assert result["total_errors"] == 0

    def test_private_torrent_with_source_access_succeeds(self):
        """Private torrent with source_type='sftp' bypasses private check."""
        manager = self._make_manager()
        client = self._make_source_client()
        client.is_private_torrent.return_value = True
        conn = self._make_torrent_connection(source_type="sftp")

        result = manager.create_manual_transfers(
            ["abc123"], client, Mock(), conn
        )

        assert result["total_initiated"] == 1
        client.is_private_torrent.assert_not_called()

    def test_private_check_exception_allows_proceed(self):
        """Exception during private check allows manual transfer to proceed."""
        manager = self._make_manager()
        client = self._make_source_client()
        client.is_private_torrent.side_effect = RuntimeError("RPC error")
        conn = self._make_torrent_connection(source_type=None)

        result = manager.create_manual_transfers(
            ["abc123"], client, Mock(), conn
        )

        assert result["total_initiated"] == 1
        assert result["total_errors"] == 0