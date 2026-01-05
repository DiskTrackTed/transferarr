"""
Integration tests for multi-target client routing.

These tests verify that torrents are correctly routed to the expected target
client based on the configured connections.

Test setup:
- source-deluge → target-deluge (configured in multi-target config)
- target-deluge-2 is available but not connected

Prerequisites:
    docker compose -f docker/docker-compose.test.yml --profile multi-target up -d
"""
import pytest
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
)
from tests.conftest import TIMEOUTS


class TestClientRouting:
    """Test that torrents are routed to the correct target based on config."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_routes_to_configured_target(
        self,
        create_torrent,
        deluge_source,
        deluge_target,
        deluge_target_2,
        radarr_client,
        transferarr,
    ):
        """
        Test that a torrent routes to the configured target (target-deluge),
        and NOT to the unconfigured target (target-deluge-2).
        
        This uses the multi-target config which has:
        - source-deluge → target-deluge connection
        - target-deluge-2 exists as a download client but has no connection
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create torrent
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Hash: {torrent_info['hash']}")
        
        # Step 2: Add movie to Radarr
        print(f"\n[Step 2] Adding movie to Radarr...")
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        
        # Step 3: Wait for torrent on source
        print(f"\n[Step 3] Waiting for torrent on source-deluge...")
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=60,
            expected_state='Seeding'
        )
        
        # Step 4: Start transferarr with multi-target config
        print(f"\n[Step 4] Starting transferarr with multi-target config...")
        transferarr.start(wait_healthy=True, config_type='multi-target')
        
        # Step 5: Wait for transfer to complete
        print(f"\n[Step 5] Waiting for transfer...")
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            'TARGET_SEEDING',
            timeout=TIMEOUTS['torrent_transfer']
        )
        
        # Step 6: Verify torrent is on target-deluge, NOT target-deluge-2
        print(f"\n[Step 6] Verifying routing...")
        target1_torrents = deluge_target.core.get_torrents_status({}, ['name'])
        target2_torrents = deluge_target_2.core.get_torrents_status({}, ['name'])
        
        assert torrent_info['hash'] in target1_torrents, \
            f"Torrent should be on target-deluge. Found: {list(target1_torrents.keys())}"
        assert torrent_info['hash'] not in target2_torrents, \
            f"Torrent should NOT be on target-deluge-2. Found: {list(target2_torrents.keys())}"
        
        print("  ✅ Torrent correctly routed to configured target (target-deluge)")
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_lifecycle_with_multi_target_config(self, lifecycle_runner, deluge_target_2):
        """
        Test a full lifecycle using the LifecycleRunner with multi-target config.
        
        This verifies that the standard lifecycle works correctly when extra
        download clients are configured but not connected.
        """
        # Configure transferarr to use multi-target config
        lifecycle_runner.transferarr.stop()
        
        print("\n[Running full lifecycle with multi-target config]")
        
        # Override the start to use multi-target config
        original_start = lifecycle_runner.transferarr.start
        def start_with_multi_target(wait_healthy=True, config_type=None):
            original_start(wait_healthy=wait_healthy, config_type='multi-target')
        lifecycle_runner.transferarr.start = start_with_multi_target
        
        try:
            lifecycle_runner.run_migration_test('radarr', item_type='movie')
            
            # Verify target-deluge-2 has no torrents (should not be used)
            target2_torrents = deluge_target_2.core.get_torrents_status({}, ['name'])
            assert len(target2_torrents) == 0, \
                f"target-deluge-2 should have no torrents, found: {len(target2_torrents)}"
            print("  ✅ target-deluge-2 correctly unused")
        finally:
            # Restore original start method
            lifecycle_runner.transferarr.start = original_start
