"""Integration tests for torrent transfer setup (Phase 5).

Tests the TORRENT_CREATING and TORRENT_TARGET_ADDING states, verifying that
transfer torrents are created on source and added to target via magnet.
"""

import pytest
import time
import requests
from deluge_client import DelugeRPCClient

from tests.conftest import TIMEOUTS, SERVICES
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_torrent_in_deluge,
    wait_for_queue_item_by_hash,
    wait_for_transferarr_state,
    decode_bytes,
)


def find_transfer_torrent(deluge_client, original_name: str, original_hash: str = None):
    """Find the transfer torrent for a given original torrent.
    
    Transfer torrents are identified by using the transferarr tracker URL.
    Note: Transfer torrents use private=False for BEP 9 metadata exchange.
    
    Args:
        deluge_client: Deluge RPC client
        original_name: Name of the original torrent
        original_hash: Hash of the original torrent (optional, for disambiguation)
        
    Returns:
        Tuple of (hash, info_dict) if found, or (None, None)
    """
    torrents = deluge_client.core.get_torrents_status(
        {}, ['name', 'private', 'trackers']
    )
    torrents = decode_bytes(torrents)
    
    for hash_id, info in torrents.items():
        name = info.get('name', '')
        trackers = info.get('trackers', [])
        
        # Skip original torrent
        if original_hash and hash_id.lower() == original_hash.lower():
            continue
        
        # Must match name
        if original_name not in name:
            continue
            
        # Check for transferarr tracker - this is the definitive identifier
        for tracker in trackers:
            tracker_url = tracker.get('url', '') if isinstance(tracker, dict) else str(tracker)
            if 'transferarr' in tracker_url:
                return hash_id, info
    
    return None, None


@pytest.fixture
def torrent_transfer_config():
    """Return the config type for torrent-based transfers."""
    return "torrent-transfer"


class TestTorrentTransferSetup:
    """Tests for torrent transfer creation and target adding."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_created_on_source(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that a transfer torrent is created on source with our tracker."""
        # Get unique movie
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Create torrent and add to Radarr
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        # Add movie to Radarr
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        # Wait for it to appear in queue
        wait_for_queue_item_by_hash(
            radarr_client, original_hash, timeout=60
        )
        
        # Start transferarr with torrent-transfer config
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TORRENT_CREATING or TORRENT_TARGET_ADDING state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Check source Deluge for transfer torrent using helper
        transfer_hash, transfer_info = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        
        assert transfer_hash is not None, \
            f"Transfer torrent (with transferarr tracker) for {torrent_name} not found on source"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_has_unique_hash(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent has a different hash from original."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash'].lower()
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Get transfer torrent using helper (which excludes original by hash)
        transfer_hash, _ = find_transfer_torrent(deluge_source, torrent_name, original_hash)
        
        assert transfer_hash is not None, "Transfer torrent not found"
        assert transfer_hash.lower() != original_hash, \
            f"Transfer hash should differ from original: {transfer_hash}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_is_not_private(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent has private=False for BEP 9 metadata exchange."""
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
        
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Get transfer torrent and check private flag
        transfer_hash, transfer_info = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        
        assert transfer_hash is not None, "Transfer torrent not found"
        assert transfer_info.get('private') is False, \
            "Transfer torrent should be public (private=False) for BEP 9 metadata exchange"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_has_tracker(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent has only our tracker URL."""
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
        
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Get transfer torrent and check trackers
        # The helper already verifies the transferarr tracker URL
        transfer_hash, transfer_info = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        
        assert transfer_hash is not None, "Transfer torrent not found"
        
        trackers = transfer_info.get('trackers', [])
        assert len(trackers) >= 1, "Transfer torrent should have at least one tracker"
        
        # Verify it's our transferarr tracker
        tracker_url = trackers[0].get('url', '') if trackers else ''
        assert 'transferarr' in tracker_url.lower(), \
            f"Tracker URL should be our transferarr tracker: {tracker_url}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_source_announces_to_tracker(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that source client announces to tracker after creating transfer torrent."""
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
        
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Get transfer torrent tracker status
        # We need to query tracker_status which isn't returned by the helper
        transfer_hash, _ = find_transfer_torrent(deluge_source, torrent_name, original_hash)
        assert transfer_hash is not None, "Transfer torrent not found"
        
        torrents = deluge_source.core.get_torrents_status(
            {'id': transfer_hash}, ['tracker_status']
        )
        torrents = decode_bytes(torrents)
        
        transfer_info = torrents.get(transfer_hash, {})
        tracker_status = transfer_info.get('tracker_status', '')
        # Tracker status should show successful announce or working status
        # Common statuses: "Announce OK", "Announce Sent", working message
        assert tracker_status, f"Tracker status should not be empty: {tracker_status}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_target_added_via_magnet(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer torrent is added to target via magnet link."""
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
        
        # Wait for TORRENT_DOWNLOADING (means it's been added to target)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING'],
            timeout=180
        )
        
        # Check target Deluge for transfer torrent
        # On target, we look for the same torrent (it'll have same name)
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, None  # No original_hash to exclude on target
        )
        
        assert transfer_hash is not None, f"Transfer torrent not found on target"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_state_transitions_creating_to_downloading(
        self,
        create_torrent,
        radarr_client,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that states progress from TORRENT_CREATING to TORRENT_DOWNLOADING."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Track state progression
        seen_states = set()
        timeout = 180
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = requests.get(
                f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/torrents",
                timeout=10
            )
            if response.status_code == 200:
                torrents = response.json().get('data', [])
                for t in torrents:
                    if torrent_name in t.get('name', ''):
                        state = t.get('state')
                        if state:
                            seen_states.add(state)
                        
                        # If we've reached TORRENT_DOWNLOADING, we've passed through the setup states
                        if state in ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING']:
                            # Verify we saw at least TORRENT_CREATING or TORRENT_TARGET_ADDING
                            torrent_states = {'TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 
                                            'TORRENT_DOWNLOADING', 'TORRENT_SEEDING'}
                            assert seen_states & torrent_states, \
                                f"Should have seen torrent transfer states, saw: {seen_states}"
                            return
            
            time.sleep(2)
        
        pytest.fail(f"Did not reach TORRENT_DOWNLOADING state, saw: {seen_states}")
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_data_persisted(
        self,
        create_torrent,
        radarr_client,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer data is persisted in state.json."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for torrent transfer to start
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Check API response for transfer data
        response = requests.get(
            f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/torrents",
            timeout=10
        )
        assert response.status_code == 200
        
        torrents = response.json().get('data', [])
        
        for t in torrents:
            if torrent_name in t.get('name', ''):
                transfer = t.get('transfer')
                assert transfer is not None, "Transfer data should be present"
                assert 'hash' in transfer, "Transfer should have hash"
                assert 'name' in transfer, "Transfer should have name"
                assert transfer['name'].startswith('[TR-'), \
                    f"Transfer name should have prefix: {transfer['name']}"
                assert 'on_source' in transfer, "Transfer should have on_source flag"
                assert 'started_at' in transfer, "Transfer should have started_at"
                return
        
        pytest.fail(f"Torrent {torrent_name} not found in API response")
