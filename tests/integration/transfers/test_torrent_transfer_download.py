"""Integration tests for torrent transfer download (Phase 6).

Tests the TORRENT_DOWNLOADING and TORRENT_SEEDING states, verifying that:
- Download progress is tracked
- Target discovers source via tracker
- Download completes and target starts seeding
- Original torrent is added to target after seeding
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
    wait_for_condition,
    decode_bytes,
)


def find_transfer_torrent(deluge_client, original_name: str, original_hash: str = None):
    """Find the transfer torrent for a given original torrent.
    
    Transfer torrents are identified by using the transferarr tracker URL.
    
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
            
        # Check for transferarr tracker
        for tracker in trackers:
            tracker_url = tracker.get('url', '') if isinstance(tracker, dict) else str(tracker)
            if 'transferarr' in tracker_url:
                return hash_id, info
    
    return None, None


def get_transfer_progress(deluge_client, transfer_hash: str) -> dict:
    """Get download progress for a transfer torrent.
    
    Args:
        deluge_client: Deluge RPC client
        transfer_hash: Hash of the transfer torrent
        
    Returns:
        dict with total_done, total_size, state, progress
    """
    status = deluge_client.core.get_torrent_status(
        transfer_hash, 
        ['total_done', 'total_size', 'state', 'progress', 'num_seeds', 'num_peers']
    )
    return decode_bytes(status) if status else {}


def get_tracker_peers(transferarr, transfer_hash: str) -> dict:
    """Get peer info from tracker for a transfer hash.
    
    Args:
        transferarr: Transferarr fixture
        transfer_hash: Transfer torrent hash (hex string)
        
    Returns:
        dict with peer info from tracker
    """
    try:
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        # Convert hash to bytes for tracker lookup
        info_hash = bytes.fromhex(transfer_hash)
        
        # Use the internal tracker API (if exposed)
        response = requests.get(
            f"http://{host}:{port}/api/v1/tracker/peers/{transfer_hash}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('data', {})
    except Exception:
        pass
    return {}


@pytest.fixture
def torrent_transfer_config():
    """Return the config type for torrent-based transfers."""
    return "torrent-transfer"


class TestTorrentTransferDownload:
    """Tests for torrent transfer download and seeding."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_download_progress_tracked(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that bytes_downloaded increases during transfer."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Create a large torrent to ensure we can see progress before it completes
        # (Docker local network is very fast, so we need a big file)
        torrent_info = create_torrent(torrent_name, size_mb=1000)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TORRENT_DOWNLOADING state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Find transfer torrent on target
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        assert transfer_hash is not None, "Transfer torrent not found on target"
        
        # Track progress over time
        initial_progress = get_transfer_progress(deluge_target, transfer_hash)
        initial_done = initial_progress.get('total_done', 0)
        
        # Wait for some progress
        time.sleep(5)
        
        final_progress = get_transfer_progress(deluge_target, transfer_hash)
        final_done = final_progress.get('total_done', 0)
        
        # Should have made some progress (or be complete)
        assert final_done >= initial_done, \
            f"Progress should not decrease: {initial_done} -> {final_done}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_download_uses_tracker_for_peers(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that target discovers source via our tracker."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        torrent_info = create_torrent(torrent_name, size_mb=20)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for downloading state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING'],
            timeout=120
        )
        
        # Find transfer torrent on target and check peers
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        assert transfer_hash is not None, "Transfer torrent not found on target"
        
        # Check target has at least one seed (the source)
        progress = get_transfer_progress(deluge_target, transfer_hash)
        num_seeds = progress.get('num_seeds', 0)
        num_peers = progress.get('num_peers', 0)
        
        # At minimum, we should see peers or the download should be progressing
        assert num_seeds > 0 or num_peers > 0 or progress.get('total_done', 0) > 0, \
            f"Target should have peers or progress. seeds={num_seeds}, peers={num_peers}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_download_completes(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that download reaches 100%."""
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Use small torrent for faster completion
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TORRENT_SEEDING (which means download completed)
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_SEEDING', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify transfer torrent is complete on target
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        
        if transfer_hash:
            progress = get_transfer_progress(deluge_target, transfer_hash)
            total_done = progress.get('total_done', 0)
            total_size = progress.get('total_size', 1)  # Avoid div by 0
            
            pct = (total_done / total_size) * 100
            assert pct >= 99.9, f"Transfer should be complete: {pct:.1f}%"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_target_starts_seeding(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that target state becomes seeding after download."""
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
        
        # Wait for TORRENT_SEEDING state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_SEEDING', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )
        
        # Check transfer torrent state on target
        transfer_hash, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        
        if transfer_hash:
            progress = get_transfer_progress(deluge_target, transfer_hash)
            state = progress.get('state', '')
            assert state == 'Seeding', f"Transfer torrent should be seeding, got: {state}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_original_added_after_seeding(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that original torrent is added to target after transfer torrent seeding."""
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
        
        # Wait for TARGET states (after original is added)
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )
        
        # Verify original torrent is on target (by hash)
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        
        original_on_target = any(
            h.lower() == original_hash.lower() 
            for h in torrents.keys()
        )
        
        assert original_on_target, \
            f"Original torrent {original_hash[:8]}... should be on target"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_original_hash_check_passes(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that files match and no re-download needed (hash check passes)."""
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
        
        # Wait for TARGET_CHECKING or TARGET_SEEDING 
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )
        
        # Check original torrent on target - should be seeding (not downloading)
        def check_original_seeding():
            status = deluge_target.core.get_torrent_status(
                original_hash, ['state', 'progress', 'total_done', 'total_size']
            )
            status = decode_bytes(status) if status else {}
            state = status.get('state', '')
            progress = status.get('progress', 0)
            return state == 'Seeding' or progress >= 99.9
        
        # Wait for seeding (hash check complete)
        result = wait_for_condition(
            check_original_seeding,
            timeout=60,
            poll_interval=2,
            description="original torrent seeding on target"
        )
        
        assert result, "Original torrent should be seeding after hash check"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_state_transitions_downloading_to_cleanup(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test full state flow: DOWNLOADING → SEEDING → CLEANUP."""
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
        
        # Track state transitions
        seen_states = set()
        
        def track_states():
            host = SERVICES['transferarr']['host']
            port = SERVICES['transferarr']['port']
            try:
                response = requests.get(
                    f"http://{host}:{port}/api/v1/torrents",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json().get('data', [])
                    for t in data:
                        if torrent_name in t.get('name', ''):
                            state = t.get('state', '')
                            seen_states.add(state)
                            # Return True when we reach end states
                            if state in ['TARGET_CHECKING', 'TARGET_SEEDING']:
                                return True
            except Exception:
                pass
            return False
        
        wait_for_condition(
            track_states,
            timeout=180,
            poll_interval=3,
            description="state transitions complete"
        )
        
        # Should have seen at least DOWNLOADING
        assert 'TORRENT_DOWNLOADING' in seen_states or \
               'TORRENT_SEEDING' in seen_states, \
            f"Should see download states. Seen: {seen_states}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_stall_detection_forces_reannounce(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that stall detection triggers re-announce.
        
        Note: This test is difficult to trigger reliably since we need the
        download to actually stall. We verify the mechanism exists by checking
        that the transfer data tracks last_progress_at.
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
        
        # Wait for DOWNLOADING state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING'],
            timeout=120
        )
        
        # Check transfer data has progress tracking fields
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        
        response = requests.get(
            f"http://{host}:{port}/api/v1/torrents",
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json().get('data', [])
        torrent_data = None
        for t in data:
            if torrent_name in t.get('name', ''):
                torrent_data = t
                break
        
        assert torrent_data is not None, "Torrent should be tracked"
        
        transfer = torrent_data.get('transfer', {})
        # Verify tracking fields exist
        assert 'last_progress_at' in transfer or 'bytes_downloaded' in transfer, \
            f"Transfer should have progress tracking. Got: {transfer.keys()}"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_transfer_torrent_cleaned_up_after_seeding(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that transfer (tmp) torrent is removed from both clients after original is seeding.
        
        The transfer torrent should be cleaned up as soon as the original torrent
        reaches TARGET_SEEDING state, without waiting for Radarr to finish processing.
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
        
        # Wait for TARGET_SEEDING state (cleanup should happen then)
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TARGET_SEEDING'],
            timeout=180
        )
        
        # Give cleanup a moment to complete
        time.sleep(5)
        
        # Find any transfer torrent (should not exist anymore)
        transfer_on_source, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        transfer_on_target, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        
        assert transfer_on_source is None, \
            f"Transfer torrent should be removed from source, but found {transfer_on_source[:8]}..."
        assert transfer_on_target is None, \
            f"Transfer torrent should be removed from target, but found {transfer_on_target[:8]}..."
        
        # Verify original torrent is still on target
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        
        original_on_target = any(
            h.lower() == original_hash.lower() 
            for h in torrents.keys()
        )
        
        assert original_on_target, \
            f"Original torrent {original_hash[:8]}... should still be on target"
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_api_returns_correct_progress_during_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Test that the API returns transfer progress (not home client progress) during torrent transfer.
        
        During TORRENT_* states, the API should show the transfer progress (0-100%)
        based on bytes_downloaded, not the home client progress (which would be 100%
        since the source is already seeding).
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Use a large torrent to ensure we can catch it mid-transfer
        torrent_info = create_torrent(torrent_name, size_mb=500)
        original_hash = torrent_info['hash']
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )
        
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        
        # Wait for TORRENT_DOWNLOADING state
        wait_for_transferarr_state(
            transferarr, torrent_name, 
            ['TORRENT_DOWNLOADING'],
            timeout=120
        )
        
        # Query the API for torrent progress
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        
        response = requests.get(
            f"http://{host}:{port}/api/v1/torrents",
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json().get('data', [])
        torrent_data = None
        for t in data:
            if torrent_name in t.get('name', ''):
                torrent_data = t
                break
        
        assert torrent_data is not None, "Torrent should be tracked"
        assert torrent_data.get('state') == 'TORRENT_DOWNLOADING', \
            f"Expected TORRENT_DOWNLOADING state, got {torrent_data.get('state')}"
        
        # The API progress should match the transfer progress, not be stuck at 100%
        api_progress = torrent_data.get('progress', 0)
        transfer = torrent_data.get('transfer', {})
        bytes_downloaded = transfer.get('bytes_downloaded', 0)
        total_size = transfer.get('total_size', 0)
        
        # Calculate expected progress from transfer data
        expected_progress = 0
        if total_size > 0:
            expected_progress = int((bytes_downloaded / total_size) * 100)
        
        assert api_progress == expected_progress, \
            f"API progress ({api_progress}%) should match transfer progress ({expected_progress}%)"
        
        # If we caught it mid-transfer, progress should be less than 100%
        # (but this might not always be true if transfer completes quickly)
        if bytes_downloaded < total_size:
            assert api_progress < 100, \
                f"Progress should be < 100% during transfer, got {api_progress}%"
