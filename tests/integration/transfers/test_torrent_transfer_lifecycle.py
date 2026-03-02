"""Integration tests for torrent transfer full lifecycle (Phase 7).

Tests the complete torrent transfer lifecycle including:
- Full migration from MANAGER_QUEUED to removal
- Sonarr episode transfers
- Cleanup of transfer torrents from both clients
- Original torrent removal from source
- Transfer data cleared after completion
- Tracker unregistration
"""

import pytest
import time
import requests

from tests.conftest import TIMEOUTS, SERVICES
from tests.utils import (
    movie_catalog,
    show_catalog,
    make_torrent_name,
    make_episode_name,
    wait_for_queue_item_by_hash,
    wait_for_sonarr_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    wait_for_condition,
    wait_for_torrent_removed,
    decode_bytes,
    find_queue_item_by_name,
    find_sonarr_queue_item_by_name,
)
from tests.integration.transfers.test_torrent_transfer_download import find_transfer_torrent


@pytest.fixture
def torrent_transfer_config():
    """Return the config type for torrent-based transfers."""
    return "torrent-transfer"


def get_transferarr_torrents():
    """Get current torrents from transferarr API."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    try:
        response = requests.get(
            f"http://{host}:{port}/api/v1/torrents",
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('data', [])
    except Exception:
        pass
    return []


def get_torrent_by_name(torrent_name: str) -> dict | None:
    """Get a specific torrent from transferarr API by name."""
    torrents = get_transferarr_torrents()
    for t in torrents:
        if torrent_name in t.get('name', ''):
            return t
    return None


def wait_for_torrent_removed_from_tracking(torrent_name: str, timeout: int = 120) -> bool:
    """Wait for a torrent to be removed from transferarr's tracking list."""
    def check_removed():
        return get_torrent_by_name(torrent_name) is None
    
    return wait_for_condition(
        check_removed,
        timeout=timeout,
        poll_interval=3,
        description=f"torrent {torrent_name} removed from tracking"
    )


class TestTorrentTransferLifecycle:
    """Tests for full torrent transfer lifecycle."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)  # Extended for full lifecycle
    def test_full_torrent_transfer_lifecycle(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test complete lifecycle: MANAGER_QUEUED → transfer → cleanup → removed.
        
        This test verifies the full lifecycle of a torrent-based transfer:
        1. Radarr adds movie to queue
        2. Torrent found on source (HOME_SEEDING)
        3. Transfer torrent created and transferred
        4. Original torrent added to target (TARGET_SEEDING)
        5. Transfer torrent cleaned up
        6. Radarr processes and removes from queue
        7. Original torrent removed from source
        8. Torrent removed from tracking
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Create and add torrent
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        # Wait for Radarr to grab torrent
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        # Wait for source to be seeding
        wait_for_torrent_in_deluge(
            deluge_source, original_hash, 
            timeout=60, expected_state='Seeding'
        )
        
        # Start transferarr
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify original is seeding on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )
        
        # Remove from Radarr queue to trigger cleanup
        queue_item = find_queue_item_by_name(radarr_client, torrent_name)
        assert queue_item, f"Could not find queue item for {torrent_name}"
        radarr_client.remove_from_queue(queue_item['id'])
        
        # Wait for original to be removed from source
        wait_for_torrent_removed(
            deluge_source, original_hash,
            timeout=TIMEOUTS['state_transition']
        )
        
        # Wait for torrent to be removed from tracking
        removed = wait_for_torrent_removed_from_tracking(
            torrent_name, timeout=60
        )
        assert removed, "Torrent should be removed from tracking after lifecycle complete"
        
        # Verify original is still on target (not removed)
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        assert any(h.lower() == original_hash.lower() for h in torrents.keys()), \
            "Original torrent should still be on target after cleanup"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_torrent_transfer_sonarr_episode(
        self,
        create_torrent,
        sonarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test torrent transfer with Sonarr TV episode."""
        show = show_catalog.get_show()
        
        # Add series to Sonarr
        added_series = sonarr_client.add_series(
            title=show['title'],
            tvdb_id=show['tvdb_id'],
            search=False
        )
        series_id = added_series['id']
        
        # Wait for episodes to be populated
        episodes = []
        for _ in range(20):
            episodes = sonarr_client.get_episodes(series_id)
            if episodes:
                break
            time.sleep(1)
        
        assert episodes, "Episodes should be populated"
        
        # Find first regular episode (season > 0)
        regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
        target_ep = regular_episodes[0] if regular_episodes else episodes[0]
        
        # Create episode torrent
        torrent_name = make_episode_name(
            added_series['title'],
            target_ep['seasonNumber'],
            target_ep['episodeNumber']
        )
        
        torrent_info = create_torrent(torrent_name, size_mb=150)
        original_hash = torrent_info['hash']
        
        # Trigger search
        time.sleep(5)  # Wait for indexer to see torrent
        sonarr_client.search_series(series_id)
        
        # Wait for Sonarr to grab
        wait_for_sonarr_queue_item_by_hash(sonarr_client, original_hash, timeout=120)
        
        # Wait for source to seed
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )
        
        # Start transferarr
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_removed_from_target(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent is removed from target after cleanup."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING (cleanup happens then)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Allow cleanup time
        time.sleep(5)
        
        # Verify transfer torrent is NOT on target
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        
        assert transfer_hash is None, \
            f"Transfer torrent should be removed from target, but found {transfer_hash[:8] if transfer_hash else 'None'}..."
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_removed_from_source(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent is removed from source after cleanup."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING (cleanup happens then)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Allow cleanup time
        time.sleep(5)
        
        # Verify transfer torrent is NOT on source
        transfer_hash, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        
        assert transfer_hash is None, \
            f"Transfer torrent should be removed from source, but found {transfer_hash[:8] if transfer_hash else 'None'}..."
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_original_removed_from_source(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that original torrent is removed from source after media manager confirms."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify original still on source (Radarr hasn't finished yet)
        torrents = deluge_source.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        assert any(h.lower() == original_hash.lower() for h in torrents.keys()), \
            "Original should still be on source before Radarr confirmation"
        
        # Remove from Radarr queue to trigger cleanup
        queue_item = find_queue_item_by_name(radarr_client, torrent_name)
        assert queue_item, f"Could not find queue item for {torrent_name}"
        radarr_client.remove_from_queue(queue_item['id'])
        
        # Wait for original to be removed from source
        wait_for_torrent_removed(
            deluge_source, original_hash,
            timeout=TIMEOUTS['state_transition']
        )
        
        # Verify it's actually gone
        torrents = deluge_source.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        assert not any(h.lower() == original_hash.lower() for h in torrents.keys()), \
            "Original should be removed from source after Radarr confirmation"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_transfer_data_cleared(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer data is cleared from state after completion."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify transfer data exists (transfer cleanup happened, but torrent still tracked)
        torrent_data = get_torrent_by_name(torrent_name)
        assert torrent_data is not None, "Torrent should still be tracked"
        
        # Transfer data should have cleaned_up flag
        transfer = torrent_data.get('transfer', {})
        assert transfer.get('cleaned_up') == True, \
            "Transfer should be marked as cleaned_up"
        
        # Remove from Radarr queue to complete lifecycle
        queue_item = find_queue_item_by_name(radarr_client, torrent_name)
        assert queue_item, f"Could not find queue item for {torrent_name}"
        radarr_client.remove_from_queue(queue_item['id'])
        
        # Wait for torrent to be removed from tracking
        removed = wait_for_torrent_removed_from_tracking(torrent_name, timeout=60)
        assert removed, "Torrent should be removed from tracking"
        
        # After removal, the torrent should not appear in API at all
        final_data = get_torrent_by_name(torrent_name)
        assert final_data is None, \
            f"Torrent should not be in tracking list after completion, got: {final_data}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_tracker_unregisters_hash(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that tracker unregisters the transfer hash after cleanup.
        
        We verify this by checking the 'cleaned_up' flag is set and the
        transfer torrent is gone. The actual tracker unregistration is
        internal, but if it failed the transfer torrent removal would also fail.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for transfer to start - capture transfer hash
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING'],
            timeout=120
        )
        
        # Get transfer hash before cleanup
        torrent_data = get_torrent_by_name(torrent_name)
        transfer_hash = torrent_data.get('transfer', {}).get('hash') if torrent_data else None
        assert transfer_hash, "Should have transfer hash during download"
        
        # Wait for TARGET_SEEDING (cleanup happens)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Allow cleanup time
        time.sleep(5)
        
        # Verify cleanup completed
        torrent_data = get_torrent_by_name(torrent_name)
        assert torrent_data is not None, "Torrent should still be tracked"
        
        transfer = torrent_data.get('transfer', {})
        assert transfer.get('cleaned_up') == True, \
            "Transfer should be marked as cleaned_up (indicates tracker unregistered)"
        
        # Both transfer torrents should be gone (confirms unregister worked)
        source_transfer, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        target_transfer, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        
        assert source_transfer is None, "Transfer torrent should be removed from source"
        assert target_transfer is None, "Transfer torrent should be removed from target"


class TestTorrentTransferHistory:
    """Integration tests for history records of torrent transfers (I1)."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_history_transfer_method_is_torrent(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
    ):
        """After torrent transfer completes, history API shows transfer_method='torrent'.

        Verifies the raw API response (not just the UI) contains the correct
        transfer_method field for torrent-based transfers.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)

        transferarr.start(
            config_type="torrent-transfer",
            wait_healthy=True,
        )

        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # Query the history API for the completed transfer
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        response = requests.get(
            f"http://{host}:{port}/api/v1/transfers",
            params={"search": torrent_name[:20]},
            timeout=10,
        )
        assert response.status_code == 200
        transfers = response.json().get('data', {}).get('transfers', [])

        matching = [t for t in transfers if torrent_name[:20] in t.get('torrent_name', '')]
        assert len(matching) >= 1, \
            f"Expected history record for {torrent_name}, got {transfers}"

        record = matching[0]
        assert record.get('transfer_method') == 'torrent', \
            f"Expected transfer_method='torrent', got '{record.get('transfer_method')}'"


class TestMultiFileTorrentTransfer:
    """Integration tests for multi-file torrent transfers (I2)."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_multi_file_torrent_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
    ):
        """Torrent transfer works for a multi-file (directory) torrent.

        Multi-file torrents exercise a different data_path construction in
        handle_creating() because the source torrent's name is a directory,
        not a single file.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10, multi_file=True)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)

        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        transferarr.start(config_type="torrent-transfer", wait_healthy=True)

        # Wait for the transfer to complete
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # Verify original torrent is seeding on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )
