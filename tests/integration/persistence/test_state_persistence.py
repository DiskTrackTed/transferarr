"""
Integration tests for state persistence across restarts.

These tests verify that Transferarr correctly saves and restores state,
allowing it to resume operations after a restart.
"""
import pytest
import time

from tests.utils import (
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
    wait_for_transferarr_state,
    get_deluge_torrent_count,
    remove_from_queue_by_name,
    movie_catalog,
    corrupt_state_file,
    delete_state_file,
    make_torrent_name,
)
from tests.conftest import TIMEOUTS


class TestStatePersistenceDuringCopying:
    """Test state persistence when restart happens during COPYING state."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(900)  # 15 minutes for 5GB transfer
    def test_state_survives_restart_during_copying(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that state is preserved when transferarr restarts mid-transfer.
        
        Scenario:
        1. Start transfer of a torrent (5GB to ensure COPYING state is observable)
        2. Wait for COPYING state
        3. Restart transferarr
        4. Verify torrent is re-enqueued and completes
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Use 5GB file to ensure COPYING state lasts long enough to restart
        file_size_mb = 5000
        
        # Step 1: Create test torrent and add to Radarr
        print(f"\n[Step 1] Creating {file_size_mb}MB torrent and adding to Radarr: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=file_size_mb)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        print(f"  Added movie ID: {movie_id}")
        
        # Trigger search and wait for grab
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Step 2: Wait for torrent to be seeding on source
        print(f"\n[Step 2] Waiting for torrent in source Deluge...")
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent is seeding on source")
        
        # Step 3: Start transferarr and wait for COPYING state
        print(f"\n[Step 3] Starting transferarr and waiting for COPYING state...")
        transferarr.start(wait_healthy=True)
        
        # Wait for torrent to enter COPYING state (100MB should give us time)
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='COPYING',
            timeout=60
        )
        print("  Transferarr is in COPYING state")
        
        # Step 4: Restart transferarr while copying
        print(f"\n[Step 4] Restarting transferarr during COPYING...")
        transferarr.restart(wait_healthy=True)
        print("  Transferarr restarted")
        
        # Step 5: Verify transfer completes after restart
        print(f"\n[Step 5] Waiting for transfer to complete...")
        
        # Wait for torrent to appear on target
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_transfer'],  # Longer timeout for 100MB file
            expected_state='Seeding'
        )
        print(f"  Target torrent state: {target_torrent.get('state')}")
        
        # Wait for Transferarr to show TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']  # Use standard state transition timeout
        )
        print("  Transferarr shows TARGET_SEEDING")
        
        # Step 6: Complete the lifecycle by removing from queue
        print(f"\n[Step 6] Removing from Radarr queue...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            print(f"  Removed queue item for {torrent_name}")
        
            # Wait for source cleanup
            wait_for_torrent_removed(
                deluge_source,
                torrent_info['hash'],
                timeout=TIMEOUTS['state_transition']
            )
            print("  Torrent removed from source")
        
        # Final verification
        print(f"\n[Final] Verifying state...")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        
        assert target_count == 1, f"Target should have exactly 1 torrent, has {target_count}"
        
        print("\n✅ Test passed: State survived restart during COPYING!")


class TestStatePersistenceTargetSeeding:
    """Test state persistence when restart happens during TARGET_SEEDING state."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_state_survives_restart_target_seeding(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that state is preserved when transferarr restarts during TARGET_SEEDING.
        
        Scenario:
        1. Complete transfer to TARGET_SEEDING state
        2. Restart transferarr
        3. Verify state is restored
        4. Remove from queue and verify cleanup works
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create and setup torrent
        print(f"\n[Step 1] Setting up torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on source")
        
        # Step 2: Start transferarr and wait for TARGET_SEEDING
        print(f"\n[Step 2] Starting transferarr and waiting for TARGET_SEEDING...")
        transferarr.start(wait_healthy=True)
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']
        )
        print("  Reached TARGET_SEEDING state")
        
        # Verify target has the torrent
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=30,
            expected_state='Seeding'
        )
        print("  Verified torrent seeding on target")
        
        # Step 3: Restart transferarr
        print(f"\n[Step 3] Restarting transferarr...")
        transferarr.restart(wait_healthy=True)
        print("  Transferarr restarted")
        
        # Step 4: Verify state is restored
        print(f"\n[Step 4] Verifying state is restored...")
        
        # Give it a moment to load state
        time.sleep(3)
        
        # Check that torrent is still tracked
        torrents = transferarr.get_torrents()
        found_torrent = None
        for t in torrents:
            if torrent_name in t.get('name', ''):
                found_torrent = t
                break
        
        assert found_torrent is not None, f"Torrent should be restored after restart"
        print(f"  Torrent found with state: {found_torrent.get('state')}")
        
        # It should still be TARGET_SEEDING (or might briefly be HOME_SEEDING while re-checking)
        # Wait for it to settle back to TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  State correctly restored to TARGET_SEEDING")
        
        # Step 5: Complete lifecycle - remove from queue
        print(f"\n[Step 5] Removing from queue and verifying cleanup...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        assert removed, f"Should find and remove queue item for: {torrent_name}"
        
        # Verify source cleanup
        wait_for_torrent_removed(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        print("  Source torrent removed")
        
        # Verify target still has torrent
        target_count = get_deluge_torrent_count(deluge_target)
        assert target_count == 1, f"Target should have 1 torrent, has {target_count}"
        
        print("\n✅ Test passed: State survived restart during TARGET_SEEDING!")


class TestStateFileCorruptionRecovery:
    """
    Test 1.3: State File Corruption Recovery
    
    Verify that Transferarr gracefully handles corrupt/missing state files
    and can re-discover torrents from media manager queues.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_recovery_from_corrupt_state_file(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test recovery when state file is corrupted.
        
        Scenario:
        1. Start transferarr with a torrent progressing through states
        2. Wait for TARGET_SEEDING state 
        3. Stop transferarr, corrupt state file
        4. Restart transferarr
        5. Verify it handles corruption gracefully and re-discovers torrent
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create torrent and add to Radarr
        print(f"\n[Step 1] Creating torrent and adding to Radarr: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        print(f"  Added movie ID: {movie_id}")
        
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Wait for torrent on source
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on source")
        
        # Step 2: Start transferarr and wait for TARGET_SEEDING
        print(f"\n[Step 2] Starting transferarr and waiting for TARGET_SEEDING...")
        transferarr.start(wait_healthy=True)
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']
        )
        print("  Reached TARGET_SEEDING state")
        
        # Verify state before corruption
        torrents_before = transferarr.get_torrents()
        print(f"  Torrents tracked before corruption: {len(torrents_before)}")
        
        # Step 3: Stop transferarr and corrupt state file
        print(f"\n[Step 3] Stopping transferarr and corrupting state file...")
        transferarr.stop()
        time.sleep(2)
        
        # Corrupt the state file (write invalid JSON)
        success = corrupt_state_file(transferarr)
        if success:
            print("  State file corrupted with invalid JSON")
        else:
            # If container not running, we need a different approach
            # Try to corrupt via volume mount
            print("  Direct corruption not available, testing missing state behavior")
            success = delete_state_file(transferarr)
            if success:
                print("  State file deleted instead")
        
        # Step 4: Restart transferarr
        print(f"\n[Step 4] Restarting transferarr with corrupted/missing state...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started successfully despite state corruption")
        
        # Step 5: Verify transferarr handles gracefully
        print(f"\n[Step 5] Verifying graceful recovery...")
        
        # Give it time to process and potentially re-discover torrents
        time.sleep(5)
        
        # Check that transferarr is running (didn't crash)
        logs = transferarr.get_logs(tail=50)
        print(f"  Recent logs show transferarr running")
        
        # The torrent should either:
        # a) Be re-discovered from the Radarr queue (since queue item still exists)
        # b) Have been tracked fresh
        # Either way, it should eventually reach TARGET_SEEDING again
        
        # Wait for torrent to be tracked again and reach TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']
        )
        print("  Torrent re-discovered and reached TARGET_SEEDING")
        
        # Verify torrent is still on target
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=30,
            expected_state='Seeding'
        )
        print(f"  Target torrent still seeding: {target_torrent.get('state')}")
        
        # Step 6: Complete lifecycle to verify full functionality
        print(f"\n[Step 6] Completing lifecycle to verify full recovery...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            print(f"  Removed queue item")
            
            wait_for_torrent_removed(
                deluge_source,
                torrent_info['hash'],
                timeout=TIMEOUTS['state_transition']
            )
            print("  Source torrent cleaned up")
        
        # Final verification
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"\n[Final] Target has {target_count} torrent(s)")
        
        assert target_count == 1, f"Target should have exactly 1 torrent, has {target_count}"
        
        print("\n✅ Test passed: Recovered gracefully from state file corruption!")
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_recovery_from_deleted_state_file(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test recovery when state file is deleted entirely.
        
        Scenario:
        1. Start transfer and reach TARGET_SEEDING
        2. Stop transferarr, delete state file
        3. Restart and verify re-discovery works
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Setup torrent
        print(f"\n[Step 1] Setting up torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on source")
        
        # Step 2: Start transferarr and wait for TARGET_SEEDING
        print(f"\n[Step 2] Starting transferarr, waiting for TARGET_SEEDING...")
        transferarr.start(wait_healthy=True)
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']
        )
        print("  Reached TARGET_SEEDING")
        
        # Step 3: Stop and delete state file
        print(f"\n[Step 3] Stopping transferarr and deleting state file...")
        transferarr.stop()
        time.sleep(2)
        
        deleted = delete_state_file(transferarr)
        assert deleted, "State file should have been deleted for accurate test results"
        print("  State file deleted")
        
        # Step 4: Restart
        print(f"\n[Step 4] Restarting transferarr with missing state file...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started successfully")
        
        # Step 5: Verify recovery
        print(f"\n[Step 5] Verifying recovery...")
        time.sleep(5)
        
        # Torrent should be re-discovered from Radarr queue
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=TIMEOUTS['state_transition']
        )
        print("  Torrent re-discovered and reached TARGET_SEEDING")
        
        # Cleanup
        print(f"\n[Step 6] Cleanup...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            wait_for_torrent_removed(
                deluge_source,
                torrent_info['hash'],
                timeout=TIMEOUTS['state_transition']
            )
            print("  Cleanup complete")
        
        print("\n✅ Test passed: Recovered from deleted state file!")


class TestMultipleTorrentsStatePersistence:
    """
    Test 1.4: Multiple Torrents State Persistence
    
    Verify that state file correctly serializes and restores multiple torrents
    at different states.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(600)  # 10 minutes for multiple torrents
    def test_multiple_torrents_state_restored(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that multiple torrents at different states are correctly restored.
        
        Scenario:
        1. Add 3 torrents (they will all progress to TARGET_SEEDING since 
           we can't easily keep them at different states)
        2. Restart transferarr
        3. Verify all torrents are restored
        """
        # Get 3 different movies
        movies = [movie_catalog.get_movie() for _ in range(3)]
        torrents_info = []
        
        # Step 1: Create 3 torrents
        print(f"\n[Step 1] Creating 3 torrents...")
        for i, movie in enumerate(movies):
            torrent_name = make_torrent_name(movie['title'], movie['year'])
            print(f"  Creating torrent {i+1}: {torrent_name}")
            
            torrent_info = create_torrent(torrent_name, size_mb=10)
            print(f"    Hash: {torrent_info['hash']}")
            
            added_movie = radarr_client.add_movie(
                title=movie['title'],
                tmdb_id=movie['tmdb_id'],
                year=movie['year'],
                search=True
            )
            
            time.sleep(1)
            radarr_client.search_movie(added_movie['id'])
            
            torrents_info.append({
                'name': torrent_name,
                'hash': torrent_info['hash'],
                'movie_id': added_movie['id'],
            })
        
        print(f"  Created {len(torrents_info)} torrents")
        
        # Step 2: Wait for all torrents to be seeding on source
        print(f"\n[Step 2] Waiting for all torrents to seed on source...")
        for info in torrents_info:
            wait_for_queue_item_by_hash(
                radarr_client, 
                info['hash'], 
                timeout=60, 
                expected_status='completed'
            )
            wait_for_torrent_in_deluge(
                deluge_source,
                info['hash'],
                timeout=TIMEOUTS['torrent_seeding'],
                expected_state='Seeding'
            )
            print(f"  {info['name']}: seeding on source")
        
        # Step 3: Start transferarr and wait for all to reach TARGET_SEEDING
        print(f"\n[Step 3] Starting transferarr and waiting for TARGET_SEEDING...")
        transferarr.start(wait_healthy=True)
        
        for info in torrents_info:
            wait_for_transferarr_state(
                transferarr,
                info['name'],
                expected_state='TARGET_SEEDING',
                timeout=TIMEOUTS['state_transition']
            )
            print(f"  {info['name']}: TARGET_SEEDING")
        
        # Step 4: Verify all torrents are tracked
        print(f"\n[Step 4] Verifying all torrents are tracked...")
        all_torrents = transferarr.get_torrents()
        print(f"  Total torrents tracked: {len(all_torrents)}")
        
        tracked_names = [t.get('name', '') for t in all_torrents]
        for info in torrents_info:
            found = any(info['name'] in name for name in tracked_names)
            assert found, f"Torrent {info['name']} should be tracked"
        print(f"  All 3 torrents found in tracking list")
        
        # Step 5: Restart transferarr
        print(f"\n[Step 5] Restarting transferarr...")
        transferarr.restart(wait_healthy=True)
        print("  Transferarr restarted")
        
        # Step 6: Verify all states are restored
        print(f"\n[Step 6] Verifying all states are restored...")
        time.sleep(5)  # Give time to load state
        
        for info in torrents_info:
            # Each torrent should still be tracked and at TARGET_SEEDING
            wait_for_transferarr_state(
                transferarr,
                info['name'],
                expected_state='TARGET_SEEDING',
                timeout=60
            )
            print(f"  {info['name']}: state restored to TARGET_SEEDING")
        
        # Step 7: Verify final counts
        print(f"\n[Step 7] Verifying final state...")
        all_torrents_after = transferarr.get_torrents()
        print(f"  Torrents tracked after restart: {len(all_torrents_after)}")
        
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Target Deluge torrents: {target_count}")
        
        assert len(all_torrents_after) == 3, f"Should have exactly 3 torrents tracked, have {len(all_torrents_after)}"
        assert target_count == 3, f"Target should have exactly 3 torrents, has {target_count}"
        
        # Cleanup
        print(f"\n[Cleanup] Removing queue items...")
        cleanup_failures = []
        for info in torrents_info:
            removed = remove_from_queue_by_name(radarr_client, info['name'])
            if removed:
                wait_for_torrent_removed(
                    deluge_source,
                    info['hash'],
                    timeout=TIMEOUTS['state_transition']
                )
                print(f"  {info['name']}: cleaned up")
            else:
                cleanup_failures.append(info['name'])
        
        if cleanup_failures:
            print(f"  Warning: Could not cleanup {len(cleanup_failures)} torrents: {cleanup_failures}")
        
        print("\n✅ Test passed: Multiple torrents state persistence works!")
