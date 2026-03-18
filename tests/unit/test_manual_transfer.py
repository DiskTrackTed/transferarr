"""Unit tests for ManualTransferService and TorrentManager.create_manual_transfers()."""

from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest

from transferarr.models.torrent import Torrent, TorrentState
from transferarr.services.torrent_service import TorrentManager
from transferarr.web.services import ManualTransferService, NotFoundError, ValidationError


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

def _make_mock_manager(**overrides):
    """Create a mock TorrentManager with sensible defaults."""
    manager = Mock(spec=TorrentManager)
    manager.download_clients = overrides.get("download_clients", {
        "source-deluge": Mock(name="source-deluge"),
        "target-deluge": Mock(name="target-deluge"),
    })
    # Set the .name attribute properly (Mock spec interferes with 'name')
    manager.download_clients["source-deluge"].name = "source-deluge"
    manager.download_clients["target-deluge"].name = "target-deluge"

    # Build connections
    conn = Mock()
    conn.from_client = manager.download_clients["source-deluge"]
    conn.to_client = manager.download_clients["target-deluge"]
    conn.name = "source-to-target"
    conn.is_torrent_transfer = False
    manager.connections = overrides.get("connections", {"source-to-target": conn})

    manager.torrents = overrides.get("torrents", [])
    manager.torrent_transfer_handler = overrides.get("torrent_transfer_handler", None)
    return manager


def _make_torrents_data(hashes, state="Seeding", save_path="/downloads/movies",
                        names=None, time_added=None):
    """Build a dict like get_all_torrents_status() returns.

    Args:
        hashes: List of torrent hashes
        state: State for all torrents (default: "Seeding")
        save_path: Parent directory for all torrents (default: "/downloads/movies")
        names: Optional list of torrent names (one per hash). If None, auto-generated.
        time_added: Optional list of epoch timestamps (one per hash). If None, auto-incremented.
    """
    data = {}
    for i, h in enumerate(hashes):
        name = names[i] if names else f"Torrent-{h[:6]}"
        data[h] = {
            "name": name,
            "state": state,
            "progress": 100,
            "save_path": save_path,
            "total_size": 1024 * 1024 * 100,
            "time_added": time_added[i] if time_added else (1700000000 + i),
        }
    return data


def _make_torrent_info(torrent_hash, **overrides):
    """Build a full torrent info dict like get_torrent_info() returns (includes 'files')."""
    info = {
        "name": f"Torrent-{torrent_hash[:6]}",
        "state": "Seeding",
        "progress": 100,
        "save_path": "/downloads/movies",
        "total_size": 1024 * 1024 * 100,
        "files": [{"path": f"Torrent-{torrent_hash[:6]}/file.mkv", "size": 1024 * 1024 * 100}],
    }
    info.update(overrides)
    return info


# ──────────────────────────────────────────────────
# ManualTransferService.get_destinations
# ──────────────────────────────────────────────────

class TestGetDestinations:
    """Tests for ManualTransferService.get_destinations()."""

    def test_returns_destinations_for_source(self):
        manager = _make_mock_manager()
        service = ManualTransferService(manager)

        result = service.get_destinations("source-deluge")
        assert len(result) == 1
        assert result[0]["client"] == "target-deluge"
        assert result[0]["connection"] == "source-to-target"
        assert result[0]["transfer_type"] == "file"

    def test_returns_torrent_transfer_type(self):
        manager = _make_mock_manager()
        conn = list(manager.connections.values())[0]
        conn.is_torrent_transfer = True

        service = ManualTransferService(manager)
        result = service.get_destinations("source-deluge")
        assert result[0]["transfer_type"] == "torrent"

    def test_raises_not_found_for_unknown_client(self):
        manager = _make_mock_manager()
        service = ManualTransferService(manager)

        with pytest.raises(NotFoundError):
            service.get_destinations("nonexistent-client")

    def test_returns_empty_when_no_connections(self):
        manager = _make_mock_manager(connections={})
        service = ManualTransferService(manager)

        result = service.get_destinations("source-deluge")
        assert result == []

    def test_deduplicates_destinations(self):
        """Multiple connections to the same target should only list it once."""
        manager = _make_mock_manager()
        # Add a second connection to same target
        conn2 = Mock()
        conn2.from_client = manager.download_clients["source-deluge"]
        conn2.to_client = manager.download_clients["target-deluge"]
        conn2.name = "source-to-target-2"
        conn2.is_torrent_transfer = True
        manager.connections["source-to-target-2"] = conn2

        service = ManualTransferService(manager)
        result = service.get_destinations("source-deluge")
        # Should deduplicate by client name — first connection wins
        assert len(result) == 1
        assert result[0]["client"] == "target-deluge"


# ──────────────────────────────────────────────────
# ManualTransferService.detect_cross_seeds
# ──────────────────────────────────────────────────

class TestDetectCrossSeeds:
    """Tests for ManualTransferService.detect_cross_seeds()."""

    def test_groups_by_name_and_size(self):
        """Torrents sharing both name AND total_size are cross-seeds."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Movie.2024.1080p", "state": "Seeding", "total_size": 1000},
            "hash2": {"save_path": "/downloads/movies", "name": "Movie.2024.1080p", "state": "Seeding", "total_size": 1000},
            "hash3": {"save_path": "/downloads/movies", "name": "Other.Movie.2023", "state": "Seeding", "total_size": 1000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)

        key = "Movie.2024.1080p|1000"
        assert key in result
        assert set(result[key]) == {"hash1", "hash2"}
        # hash3 has different name — not a cross-seed
        assert len(result) == 1

    def test_ignores_single_torrent_paths(self):
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Unique.Movie", "state": "Seeding", "total_size": 1000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert result == {}

    def test_ignores_missing_total_size(self):
        """Torrents without total_size are skipped."""
        data = {
            "hash1": {"name": "Test", "state": "Seeding"},
            "hash2": {"name": "Test", "state": "Seeding", "total_size": None},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert result == {}

    def test_ignores_missing_name(self):
        """Torrents without a name field are skipped."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "state": "Seeding", "total_size": 1000},
            "hash2": {"save_path": "/downloads/movies", "name": None, "state": "Seeding", "total_size": 1000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert result == {}

    def test_same_dir_different_names_not_cross_seeds(self):
        """Torrents in the same directory but with different names are NOT cross-seeds."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Movie.A.2024", "state": "Seeding", "total_size": 1000},
            "hash2": {"save_path": "/downloads/movies", "name": "Movie.B.2023", "state": "Seeding", "total_size": 1000},
            "hash3": {"save_path": "/downloads/movies", "name": "Movie.C.2022", "state": "Seeding", "total_size": 1000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert result == {}

    def test_same_name_different_dirs_are_cross_seeds(self):
        """Torrents with the same name+size in different directories ARE cross-seeds.
        This is the cross-seed symlink scenario: the tool creates symlinks in a
        separate linkdir, so save_path differs but the data is the same."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
            "hash2": {"save_path": "/downloads/linkdir/LST", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert len(result) == 1
        group_hashes = list(result.values())[0]
        assert set(group_hashes) == {"hash1", "hash2"}

    def test_same_name_different_size_not_cross_seeds(self):
        """Torrents with the same name but different total_size are NOT cross-seeds."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
            "hash2": {"save_path": "/downloads/movies", "name": "Movie.2024", "state": "Seeding", "total_size": 9000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        assert result == {}

    def test_three_way_cross_seed_group(self):
        """Three torrents sharing the same data form a single group."""
        data = {
            "hash1": {"save_path": "/downloads/movies", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
            "hash2": {"save_path": "/downloads/movies", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
            "hash3": {"save_path": "/downloads/linkdir/TL", "name": "Movie.2024", "state": "Seeding", "total_size": 5000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)
        key = "Movie.2024|5000"
        assert key in result
        assert set(result[key]) == {"hash1", "hash2", "hash3"}

    def test_mixed_real_world_scenario(self):
        """Mix of cross-seeds, unique torrents, and different directories."""
        data = {
            # Two cross-seeds for same movie (different trackers)
            "aaa111": {"save_path": "/downloads/movies", "name": "Inception.2010.1080p", "state": "Seeding", "total_size": 8000},
            "aaa222": {"save_path": "/downloads/linkdir/TL", "name": "Inception.2010.1080p", "state": "Seeding", "total_size": 8000},
            # Different movie — NOT a cross-seed
            "bbb111": {"save_path": "/downloads/movies", "name": "Matrix.1999.1080p", "state": "Seeding", "total_size": 7000},
            # TV show cross-seeds (same name+size, different dirs)
            "ccc111": {"save_path": "/downloads/tv", "name": "Breaking.Bad.S01E01", "state": "Seeding", "total_size": 3000},
            "ccc222": {"save_path": "/downloads/tv", "name": "Breaking.Bad.S01E01", "state": "Seeding", "total_size": 3000},
        }
        service = ManualTransferService(Mock())
        result = service.detect_cross_seeds("client", data)

        assert len(result) == 2
        assert set(result["Inception.2010.1080p|8000"]) == {"aaa111", "aaa222"}
        assert set(result["Breaking.Bad.S01E01|3000"]) == {"ccc111", "ccc222"}


# ──────────────────────────────────────────────────
# ManualTransferService.validate_and_initiate
# ──────────────────────────────────────────────────

class TestValidateAndInitiate:
    """Tests for ManualTransferService.validate_and_initiate()."""

    def _make_service_with_data(self, torrents_data=None, tracked_torrents=None,
                                 torrent_transfer=False):
        """Helper to create a service with mocked dependencies."""
        manager = _make_mock_manager()
        manager.torrents = tracked_torrents or []

        # Mock get_all_torrents_status on the source client
        source = manager.download_clients["source-deluge"]
        source.get_all_torrents_status.return_value = torrents_data or {}

        # Set up transfer type
        conn = list(manager.connections.values())[0]
        conn.is_torrent_transfer = torrent_transfer

        # Mock create_manual_transfers
        manager.create_manual_transfers = Mock(return_value={
            "initiated": [],
            "errors": [],
            "total_initiated": 0,
            "total_errors": 0,
        })

        service = ManualTransferService(manager)
        return service, manager

    def test_raises_for_empty_hashes(self):
        service, _ = self._make_service_with_data()
        with pytest.raises(ValidationError, match="No torrent hashes"):
            service.validate_and_initiate({
                "hashes": [],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_raises_for_unknown_source(self):
        service, _ = self._make_service_with_data()
        with pytest.raises(NotFoundError):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "nonexistent",
                "destination_client": "target-deluge",
            })

    def test_raises_for_unknown_destination(self):
        service, _ = self._make_service_with_data()
        with pytest.raises(NotFoundError):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "nonexistent",
            })

    def test_raises_for_same_source_and_dest(self):
        service, _ = self._make_service_with_data()
        with pytest.raises(ValidationError, match="cannot be the same"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "source-deluge",
            })

    def test_raises_for_missing_connection(self):
        manager = _make_mock_manager(connections={})
        service = ManualTransferService(manager)
        source = manager.download_clients["source-deluge"]
        source.get_all_torrents_status.return_value = _make_torrents_data(["abc123"])

        with pytest.raises(ValidationError, match="No connection configured"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_raises_for_hash_not_on_client(self):
        service, _ = self._make_service_with_data(torrents_data={})
        with pytest.raises(ValidationError, match="not found"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_raises_for_not_seeding_torrent(self):
        data = _make_torrents_data(["abc123"], state="Downloading")
        service, _ = self._make_service_with_data(torrents_data=data)

        with pytest.raises(ValidationError, match="Seeding"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_raises_for_already_tracked_torrent(self):
        data = _make_torrents_data(["abc123"])
        tracked = [Torrent(name="tracked", id="abc123")]
        service, _ = self._make_service_with_data(
            torrents_data=data, tracked_torrents=tracked
        )

        with pytest.raises(ValidationError, match="already being tracked"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_raises_for_torrent_transfer_without_tracker(self):
        """Upfront rejection when connection is torrent-type but tracker is unavailable."""
        data = _make_torrents_data(["abc123"])
        service, _ = self._make_service_with_data(
            torrents_data=data, torrent_transfer=True
        )

        with pytest.raises(ValidationError, match="Tracker is not available"):
            service.validate_and_initiate({
                "hashes": ["abc123"],
                "source_client": "source-deluge",
                "destination_client": "target-deluge",
            })

    def test_delegates_to_create_manual_transfers(self):
        data = _make_torrents_data(["abc123"])
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        })

        manager.create_manual_transfers.assert_called_once()
        call_kwargs = manager.create_manual_transfers.call_args
        assert "abc123" in call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))

    def test_case_insensitive_hash_matching(self):
        data = {"ABC123": {
            "name": "Test",
            "state": "Seeding",
            "progress": 100,
            "save_path": "/movies",
            "total_size": 100,
        }}
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        })

        manager.create_manual_transfers.assert_called_once()

    def test_cross_seed_expansion(self):
        """When include_cross_seeds=True, siblings sharing name+size are included."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",  # Same name+path = cross-seed
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
        }
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["hash1"],  # Only select hash1
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        })

        # Both hash1 and hash2 should be in the call
        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert set(hashes) == {"hash1", "hash2"}

    def test_no_cross_seed_expansion_when_disabled(self):
        """When include_cross_seeds=False, only selected hashes are transferred."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
        }
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["hash1"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert hashes == ["hash1"]

    def test_cross_seed_skips_non_seeding_siblings(self):
        """Cross-seed siblings that aren't seeding are not included."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",
                "state": "Downloading",  # Not seeding
                "progress": 50,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
        }
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["hash1"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert set(hashes) == {"hash1"}  # hash2 excluded (not seeding)

    def test_cross_seed_skips_already_tracked_siblings(self):
        """Cross-seed siblings that are already tracked are not included."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
        }
        tracked = [Torrent(name="tracked", id="hash2")]
        service, manager = self._make_service_with_data(
            torrents_data=data, tracked_torrents=tracked
        )

        service.validate_and_initiate({
            "hashes": ["hash1"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert set(hashes) == {"hash1"}  # hash2 excluded (tracked)

    def test_cross_seed_expansion_same_name_only(self):
        """Expansion only includes siblings with matching name AND total_size."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",  # Same name+path = cross-seed
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash3": {
                "name": "Different.Movie.2023",  # Different name = NOT a cross-seed
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
        }
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["hash1"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert set(hashes) == {"hash1", "hash2"}  # hash3 excluded (different name)

    def test_cross_seed_expansion_different_dir_same_name(self):
        """Torrents with the same name+size but different save_path ARE cross-seeds (symlink scenario)."""
        data = {
            "hash1": {
                "name": "Movie.2024.1080p",
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/movies",
                "total_size": 100,
            },
            "hash2": {
                "name": "Movie.2024.1080p",  # Same name+size, different dir = cross-seed
                "state": "Seeding",
                "progress": 100,
                "save_path": "/downloads/linkdir/LST",
                "total_size": 100,
            },
        }
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["hash1"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        hashes = call_kwargs.kwargs.get("hashes", call_kwargs[1].get("hashes", []))
        assert set(hashes) == {"hash1", "hash2"}  # hash2 included (cross-seed via symlink)

    def test_passes_delete_source_cross_seeds_true(self):
        """delete_source_cross_seeds=True is forwarded to create_manual_transfers."""
        data = _make_torrents_data(["abc123"])
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "delete_source_cross_seeds": True,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        assert call_kwargs.kwargs.get("delete_source_cross_seeds") is True

    def test_passes_delete_source_cross_seeds_false(self):
        """delete_source_cross_seeds=False is forwarded to create_manual_transfers."""
        data = _make_torrents_data(["abc123"])
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "delete_source_cross_seeds": False,
        })

        call_kwargs = manager.create_manual_transfers.call_args
        assert call_kwargs.kwargs.get("delete_source_cross_seeds") is False

    def test_delete_source_cross_seeds_defaults_to_true(self):
        """When not specified, delete_source_cross_seeds defaults to True."""
        data = _make_torrents_data(["abc123"])
        service, manager = self._make_service_with_data(torrents_data=data)

        service.validate_and_initiate({
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        })

        call_kwargs = manager.create_manual_transfers.call_args
        assert call_kwargs.kwargs.get("delete_source_cross_seeds") is True


# ──────────────────────────────────────────────────
# TorrentManager.create_manual_transfers
# ──────────────────────────────────────────────────

class TestCreateManualTransfers:
    """Tests for TorrentManager.create_manual_transfers()."""

    def _make_manager(self, **overrides):
        """Create a minimal mock TorrentManager with the real method."""
        manager = Mock(spec=TorrentManager)
        manager.torrents = overrides.get("torrents", [])
        manager.save_torrents_state = Mock()
        manager.torrent_transfer_handler = overrides.get("handler", None)
        # Bind the real method
        manager.create_manual_transfers = TorrentManager.create_manual_transfers.__get__(manager)
        return manager

    def test_creates_torrent_and_enqueues_sftp_copy(self):
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.get_history_transfer_method.return_value = "sftp"

        result = manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 1
        assert result["total_errors"] == 0
        assert result["initiated"][0]["hash"] == "abc123"
        assert result["initiated"][0]["method"] == "sftp"
        conn.enqueue_copy_torrent.assert_called_once()

        # Should have added a Torrent to manager.torrents
        assert len(manager.torrents) == 1
        t = manager.torrents[0]
        assert t.id == "abc123"
        assert t.state == TorrentState.HOME_SEEDING  # enqueue sets COPYING async
        assert t.media_manager is None
        assert t.home_client == source
        assert t.target_client == dest

    def test_creates_torrent_transfer_with_handler(self):
        handler = Mock()
        manager = self._make_manager(handler=handler)
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = True

        result = manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 1
        assert result["initiated"][0]["method"] == "torrent"
        # handle_create_queue is NOT called inline (would block the HTTP request);
        # the torrent is left in TORRENT_CREATE_QUEUE for the update_torrents() loop.
        handler.handle_creating.assert_not_called()
        t = manager.torrents[0]
        assert t.state == TorrentState.TORRENT_CREATE_QUEUE

    def test_errors_when_no_handler_for_torrent_transfer(self):
        manager = self._make_manager(handler=None)
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = True

        result = manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 0
        assert result["total_errors"] == 1
        assert "Tracker not available" in result["errors"][0]["error"]
        # Verify torrent is NOT left in tracking list
        assert len(manager.torrents) == 0

    def test_handles_missing_torrent_info(self):
        """When hash not in all_torrents_data and get_torrent_info returns None."""
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = None
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False

        result = manager.create_manual_transfers(
            hashes=["missing_hash"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 0
        assert result["total_errors"] == 1
        assert "Could not fetch" in result["errors"][0]["error"]

    def test_handles_exception_gracefully(self):
        """Exceptions during individual torrent processing don't crash the whole batch."""
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.enqueue_copy_torrent.side_effect = Exception("SFTP connection failed")

        result = manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 0
        assert result["total_errors"] == 1

    def test_processes_multiple_hashes(self):
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.side_effect = [
            _make_torrent_info("hash1"),
            _make_torrent_info("hash2"),
            _make_torrent_info("hash3"),
        ]
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.get_history_transfer_method.return_value = "local"

        result = manager.create_manual_transfers(
            hashes=["hash1", "hash2", "hash3"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert result["total_initiated"] == 3
        assert len(manager.torrents) == 3
        assert conn.enqueue_copy_torrent.call_count == 3
        manager.save_torrents_state.assert_called_once()

    def test_saves_state_after_all_transfers(self):
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.get_history_transfer_method.return_value = "sftp"

        manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        manager.save_torrents_state.assert_called_once()

    def test_stores_delete_source_cross_seeds_on_torrent(self):
        """delete_source_cross_seeds flag is stored on the created Torrent."""
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.get_history_transfer_method.return_value = "sftp"

        manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
            delete_source_cross_seeds=False,
        )

        assert len(manager.torrents) == 1
        assert manager.torrents[0].delete_source_cross_seeds is False

    def test_delete_source_cross_seeds_defaults_to_true_on_torrent(self):
        """When not passed, delete_source_cross_seeds defaults to True on the Torrent."""
        manager = self._make_manager()
        source = Mock()
        source.name = "source-deluge"
        source.get_torrent_info.return_value = _make_torrent_info("abc123")
        dest = Mock()
        dest.name = "target-deluge"
        conn = Mock()
        conn.is_torrent_transfer = False
        conn.get_history_transfer_method.return_value = "sftp"

        manager.create_manual_transfers(
            hashes=["abc123"],
            source_client=source,
            dest_client=dest,
            connection=conn,
        )

        assert len(manager.torrents) == 1
        assert manager.torrents[0].delete_source_cross_seeds is True


# ──────────────────────────────────────────────────
# ManualTransferSchema validation
# ──────────────────────────────────────────────────

class TestManualTransferSchema:
    """Tests for ManualTransferSchema marshmallow validation."""

    def _load(self, data):
        from transferarr.web.schemas import ManualTransferSchema
        return ManualTransferSchema().load(data)

    def test_valid_request(self):
        result = self._load({
            "hashes": ["abc123"],
            "source_client": "source",
            "destination_client": "target",
        })
        assert result["hashes"] == ["abc123"]
        assert result["include_cross_seeds"] is False  # default

    def test_all_fields(self):
        result = self._load({
            "hashes": ["abc123", "def456"],
            "source_client": "source",
            "destination_client": "target",
            "include_cross_seeds": False,
        })
        assert result["include_cross_seeds"] is False

    def test_missing_hashes_raises(self):
        from marshmallow import ValidationError as MarshmallowValidationError
        with pytest.raises(MarshmallowValidationError):
            self._load({
                "source_client": "source",
                "destination_client": "target",
            })

    def test_empty_hashes_raises(self):
        from marshmallow import ValidationError as MarshmallowValidationError
        with pytest.raises(MarshmallowValidationError):
            self._load({
                "hashes": [],
                "source_client": "source",
                "destination_client": "target",
            })

    def test_missing_source_client_raises(self):
        from marshmallow import ValidationError as MarshmallowValidationError
        with pytest.raises(MarshmallowValidationError):
            self._load({
                "hashes": ["abc123"],
                "destination_client": "target",
            })

    def test_empty_source_client_raises(self):
        from marshmallow import ValidationError as MarshmallowValidationError
        with pytest.raises(MarshmallowValidationError):
            self._load({
                "hashes": ["abc123"],
                "source_client": "",
                "destination_client": "target",
            })

    def test_delete_source_cross_seeds_defaults_to_true(self):
        result = self._load({
            "hashes": ["abc123"],
            "source_client": "source",
            "destination_client": "target",
        })
        assert result["delete_source_cross_seeds"] is True

    def test_delete_source_cross_seeds_false(self):
        result = self._load({
            "hashes": ["abc123"],
            "source_client": "source",
            "destination_client": "target",
            "delete_source_cross_seeds": False,
        })
        assert result["delete_source_cross_seeds"] is False
