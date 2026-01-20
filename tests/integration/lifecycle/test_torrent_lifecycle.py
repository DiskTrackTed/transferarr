"""
Integration tests for the complete torrent transfer lifecycle.

These tests verify the happy path: torrent goes from Radarr queue through
Transferarr to the target Deluge instance, then gets cleaned up from source.
"""
import pytest
from tests.utils import movie_catalog, make_torrent_name, wait_for_queue_item_by_hash, wait_for_torrent_in_deluge, wait_for_transferarr_state
from tests.conftest import TIMEOUTS


class TestTorrentLifecycle:
    """Test the complete torrent transfer lifecycle."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_complete_transfer_lifecycle(self, lifecycle_runner):
        """Test the complete torrent lifecycle from Radarr to target."""
        lifecycle_runner.run_migration_test('radarr', item_type='movie', verify_cleanup=True)


class TestTorrentDiscovery:
    """Test that transferarr correctly discovers and tracks torrents."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(120)
    def test_discovers_existing_torrent(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr discovers a torrent that was already
        in the queue before it started.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Create torrent and add to queue BEFORE starting transferarr
        print(f"\n[Step 1] Creating torrent and adding to queue...")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        
        # Wait for torrent to be grabbed (use hash-based matching)
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info['hash'], timeout=60, expected_state='Seeding')
        
        print(f"  Torrent is seeding on source before transferarr starts")
        
        # Now start transferarr
        print(f"\n[Step 2] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Verify it discovers the torrent
        print(f"\n[Step 3] Waiting for transferarr to discover torrent...")
        torrent_state = wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='HOME_SEEDING',
            timeout=30
        )
        
        print(f"  Transferarr discovered torrent: {torrent_state}")
        print("\n✅ Test passed: Existing torrent discovered!")
