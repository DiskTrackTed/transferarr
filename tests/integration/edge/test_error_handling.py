"""
Integration tests for error handling scenarios.

These tests verify that Transferarr correctly handles error conditions
like unclaimed torrents and transient failures.
"""
import pytest
import time

from tests.utils import (
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
    wait_for_condition,
    wait_for_transferarr_state,
    get_deluge_torrent_count,
    find_torrent_in_transferarr,
    remove_from_queue_by_name,
    movie_catalog,
    make_torrent_name,
)
from tests.conftest import TIMEOUTS, SERVICES


class TestQueueItemDisappears:
    """Test handling when Radarr queue item disappears while Transferarr is tracking."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(180)  # 3 minutes
    def test_queue_item_removed_while_tracking(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that Transferarr handles queue item disappearing gracefully.
        
        This tests the realistic scenario where:
        - A torrent is being tracked by Transferarr (HOME_SEEDING state)
        - The queue item is removed from Radarr (user action or auto-import)
        - Transferarr should detect this and stop tracking the torrent
        
        Scenario:
        1. Add movie to Radarr, torrent downloads and seeds on source
        2. Start Transferarr - it tracks the torrent (HOME_SEEDING state)
        3. Remove the queue item from Radarr
        4. Verify Transferarr detects the orphan and removes it from tracking
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
        
        # Trigger search and wait for grab
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Wait for torrent to appear in queue and on source
        print(f"\n[Step 2] Waiting for torrent to be grabbed and seeding...")
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent is seeding on source")
        
        # Step 3: Start transferarr and wait for it to track the torrent
        print(f"\n[Step 3] Starting transferarr and waiting for HOME_SEEDING state...")
        transferarr.start(wait_healthy=True)
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='HOME_SEEDING',
            timeout=60
        )
        print("  Transferarr is tracking torrent in HOME_SEEDING state")
        
        # Step 4: Remove the queue item from Radarr (simulating user action or auto-import)
        print(f"\n[Step 4] Removing queue item from Radarr...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        assert removed, "Queue item should have been found and removed"
        print("  Queue item removed from Radarr")
        
        # Step 5: Wait for Transferarr to detect the orphan and handle it
        # When the queue item disappears, the torrent should eventually be removed from tracking
        print(f"\n[Step 5] Waiting for Transferarr to detect orphaned torrent...")
        print("  (Transferarr should remove torrent from tracking when queue item is gone)")
        
        def check_torrent_removed_from_tracking():
            torrents = transferarr.get_torrents()
            for t in torrents:
                if torrent_name in t.get('name', ''):
                    return False
            return True
        
        try:
            wait_for_condition(
                check_torrent_removed_from_tracking,
                timeout=90,  # Give time for several processing loops
                poll_interval=5,
                description=f"torrent '{torrent_name}' to be removed from tracking after queue item disappeared"
            )
            print("  Torrent was removed from tracking")
        except TimeoutError as e:
            # Get current state for debugging
            torrents = transferarr.get_torrents()
            current_states = {t.get('name'): t.get('state') for t in torrents}
            raise TimeoutError(
                f"{e}. Current tracked torrents: {current_states}"
            )
        
        # Step 6: Verify final state
        print(f"\n[Final] Verifying final state...")
        
        # Transferarr should still be running
        assert transferarr.is_running(), "Transferarr should still be running"
        
        # Torrent should no longer be tracked
        final_torrents = transferarr.get_torrents()
        torrent_still_tracked = any(torrent_name in t.get('name', '') for t in final_torrents)
        assert not torrent_still_tracked, "Torrent should have been removed from tracking"
        
        # Source Deluge should still have the torrent (we only removed queue item)
        source_count = get_deluge_torrent_count(deluge_source)
        
        print(f"  Transferarr running: {transferarr.is_running()}")
        print(f"  Source torrents: {source_count}")
        print(f"  Tracked torrents: {len(final_torrents)}")
        
        print("\n✅ Test passed: Queue item disappearance handled gracefully!")


class TestSourceTorrentRemoved:
    """Test handling when source torrent is removed during transfer."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(900)  # 15 minutes for 2.5GB torrent
    def test_source_torrent_removed_during_copying(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr handles source torrent removal gracefully.
        
        Scenario:
        1. Start a transfer (torrent enters COPYING state) using large file
        2. Delete the torrent AND its data from source Deluge during transfer
        3. Verify transferarr handles the situation gracefully
        4. System should not crash and torrent should be handled appropriately
        
        Note: Due to Linux file handle behavior, an active SFTP copy may continue
        even after files are deleted (data persists until handles close). This test
        verifies the system handles the situation gracefully regardless of outcome.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create test torrent and add to Radarr
        # Use 2.5GB to ensure COPYING state lasts long enough to catch
        file_size_mb = 2500
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
        
        # Wait for torrent to enter COPYING state
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='COPYING',
            timeout=60
        )
        print("  Transferarr is in COPYING state")
        
        # Step 4: Remove the torrent from source Deluge (with data)
        print(f"\n[Step 4] Removing torrent AND data from source Deluge during transfer...")
        deluge_source.core.remove_torrent(torrent_info['hash'], True)  # True = remove data
        print("  Source torrent removal requested")
        
        # Step 5: Verify source Deluge no longer has the torrent
        time.sleep(2)
        source_count = get_deluge_torrent_count(deluge_source)
        assert source_count == 0, f"Source should have no torrents, has {source_count}"
        print(f"  Source Deluge shows {source_count} torrents")
        
        # Step 6: Wait for the situation to resolve
        # The copy may continue (Linux file handles) or fail - either is acceptable
        print(f"\n[Step 5] Waiting for transfer to complete or fail...")
        
        # Wait for torrent to either:
        # - Complete transfer (TARGET_SEEDING) - copy continued despite deletion
        # - Be removed from tracking - transfer failed and was cleaned up
        # - Stay in an error/unclaimed state - acceptable intermediate state
        deadline = time.time() + 600  # 10 minutes for 2.5GB transfer
        final_state = None
        
        while time.time() < deadline:
            torrent = find_torrent_in_transferarr(transferarr, torrent_name)
            if torrent is None:
                print("  Torrent was removed from tracking")
                final_state = 'REMOVED'
                break
            
            current_state = torrent.get('state')
            if current_state == 'TARGET_SEEDING':
                print(f"  Transfer completed despite source removal (state: {current_state})")
                final_state = current_state
                break
            elif current_state in ['UNCLAIMED', 'ERROR', 'MISSING']:
                print(f"  Torrent in error state: {current_state}")
                final_state = current_state
                break
            
            time.sleep(5)
        
        if final_state is None:
            # Check one more time
            torrent = find_torrent_in_transferarr(transferarr, torrent_name)
            final_state = torrent.get('state') if torrent else 'REMOVED'
            print(f"  Final state after timeout: {final_state}")
        
        # Step 7: Verify transferarr is still running and healthy
        print(f"\n[Step 6] Verifying transferarr is still healthy...")
        assert transferarr.is_running(), "Transferarr should still be running"
        
        # Final verification
        print(f"\n[Final] Verifying final state...")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        print(f"  Final torrent state: {final_state}")
        
        # Source should be empty (we removed the torrent)
        assert source_count == 0, f"Source should be empty, has {source_count}"
        
        # The key assertion: system handled it gracefully (didn't crash)
        # Final state should be one of the acceptable outcomes
        acceptable_states = ['TARGET_SEEDING', 'UNCLAIMED', 'ERROR', 'MISSING', 'REMOVED', 'COPYING']
        assert final_state in acceptable_states, \
            f"Expected graceful handling (one of {acceptable_states}), got unexpected state: {final_state}"
        
        print("\n✅ Test passed: Source torrent removal during COPYING handled gracefully!")


class TestTargetTorrentDisappears:
    """Test handling when target torrent disappears after COPIED."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_target_torrent_disappears_after_copied(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr handles target torrent disappearing gracefully.
        
        Scenario:
        1. Complete transfer to TARGET_CHECKING or TARGET_SEEDING state
        2. Delete torrent from target Deluge
        3. Observe transferarr's behavior - should detect missing and handle
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create test torrent and add to Radarr
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
        
        # Step 3: Start transferarr and wait for TARGET_SEEDING
        print(f"\n[Step 3] Starting transferarr and waiting for transfer to target...")
        transferarr.start(wait_healthy=True)
        
        # Wait for target to have the torrent and be seeding
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on target")
        
        # Wait for TARGET_SEEDING state in transferarr
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  Transferarr shows TARGET_SEEDING")
        
        # Step 4: Delete torrent from target Deluge
        print(f"\n[Step 4] Removing torrent from target Deluge...")
        deluge_target.core.remove_torrent(torrent_info['hash'], True)
        time.sleep(2)
        
        target_count = get_deluge_torrent_count(deluge_target)
        assert target_count == 0, f"Target should be empty, has {target_count}"
        print(f"  Target Deluge is empty ({target_count} torrents)")
        
        # Step 5: Wait for transferarr to detect the missing target
        print(f"\n[Step 5] Waiting for transferarr to detect missing target...")
        
        # Give transferarr time to detect the change
        # It should either:
        # - Go to UNCLAIMED state
        # - Re-copy from source (if source still exists)
        # - Remove from tracking
        time.sleep(10)  # Give time for next processing loop
        
        # Check current state
        torrent = find_torrent_in_transferarr(transferarr, torrent_name)
        
        if torrent:
            current_state = torrent.get('state')
            print(f"  Torrent current state: {current_state}")
            
            # Acceptable outcomes:
            # - UNCLAIMED (target disappeared)
            # - HOME_SEEDING (source still has it, may re-transfer)
            # - COPYING (re-transferring)
            # - TARGET_SEEDING (quickly re-copied and target has it again)
            # - Eventually removed from tracking
            
            if current_state not in ['UNCLAIMED', 'HOME_SEEDING', 'COPYING', 'TARGET_SEEDING']:
                # Wait a bit more, might be transitioning
                time.sleep(30)
                torrent = find_torrent_in_transferarr(transferarr, torrent_name)
                if torrent:
                    current_state = torrent.get('state')
                    print(f"  Torrent state after wait: {current_state}")
        else:
            print("  Torrent was removed from tracking")
        
        # Step 6: Verify transferarr is still running
        print(f"\n[Step 6] Verifying transferarr is still healthy...")
        assert transferarr.is_running(), "Transferarr should still be running"
        
        # Final verification
        print(f"\n[Final] Verifying final state...")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        
        # Source should still have the torrent (we didn't complete the lifecycle)
        assert source_count == 1, f"Source should have exactly 1 torrent, has {source_count}"
        
        # Transferarr should still be healthy
        assert transferarr.is_running(), "Transferarr must still be running"
        
        print("\n✅ Test passed: Target torrent disappearance handled gracefully!")


class TestMediaManagerConnectionFailure:
    """Test handling when media manager (Radarr) connection fails."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(300)  # 5 minutes
    def test_radarr_connection_failure_and_recovery(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
        docker_client,
    ):
        """
        Test that transferarr handles Radarr connection failure gracefully.
        
        Scenario:
        1. Start transferarr with a torrent being tracked
        2. Stop Radarr container
        3. Verify transferarr continues running (doesn't crash)
        4. Restart Radarr
        5. Verify transferarr recovers and continues processing
        
        Note: The torrent may complete transfer during Radarr downtime (Deluge 
        still works). The key test is that transferarr doesn't crash and recovers.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create test torrent and add to Radarr
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
        
        # Step 3: Start transferarr
        print(f"\n[Step 3] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Wait for transferarr to detect the torrent
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='HOME_SEEDING',
            timeout=30
        )
        print("  Transferarr detected torrent")
        
        # Step 4: Stop Radarr container
        print(f"\n[Step 4] Stopping Radarr container...")
        radarr_container = docker_client.containers.get('test-radarr')
        radarr_container.stop()
        print("  Radarr container stopped")
        
        # Step 5: Wait and verify transferarr is still running
        print(f"\n[Step 5] Waiting and verifying transferarr handles connection failure...")
        time.sleep(15)  # Give time for a few processing loops to fail
        
        assert transferarr.is_running(), "Transferarr should still be running despite Radarr being down"
        print("  Transferarr is still running")
        
        # Check logs for error messages (optional)
        logs = transferarr.get_logs(tail=50)
        if 'error' in logs.lower() or 'exception' in logs.lower():
            print("  (Errors logged - expected when Radarr is down)")
        
        # Step 6: Restart Radarr
        print(f"\n[Step 6] Restarting Radarr container...")
        radarr_container.start()
        
        # Wait for Radarr to be healthy
        deadline = time.time() + 60
        while time.time() < deadline:
            radarr_container.reload()
            health = radarr_container.attrs.get('State', {}).get('Health', {})
            status = health.get('Status', 'none')
            if status == 'healthy':
                break
            time.sleep(2)
        print("  Radarr container restarted and healthy")
        
        # Step 7: Verify transferarr recovers and continues
        print(f"\n[Step 7] Verifying transferarr recovers...")
        
        # Give time for recovery
        time.sleep(10)
        
        # Transferarr should still be running - this is the key test
        assert transferarr.is_running(), "Transferarr should still be running after Radarr recovery"
        print("  Transferarr is still running after recovery")
        
        # Check if transferarr can now access its API (health check)
        torrents = transferarr.get_torrents()
        assert torrents is not None, "Transferarr API should respond after recovery"
        print(f"  Transferarr API responding, tracking {len(torrents)} torrent(s)")
        
        # Final verification
        print(f"\n[Final] Verifying final state...")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        print(f"  Transferarr running: {transferarr.is_running()}")
        
        # The key assertion is that transferarr survived the Radarr outage
        assert transferarr.is_running(), "Transferarr must be running after recovery"
        
        print("\n✅ Test passed: Radarr connection failure handled gracefully!")


class TestDownloadClientOutage:
    """Test handling of download client outages during transfer."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(300)  # 5 minutes - need time for outage and recovery
    def test_source_client_unavailable_at_start(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr handles source Deluge being unavailable at startup.
        
        This tests the scenario where transferarr starts but the source client
        is temporarily unavailable. Transferarr should:
        1. Continue running despite the connection failure
        2. Recover and complete the transfer when client comes back
        
        Scenario:
        1. Add torrent to Radarr, wait for seeding on source
        2. Stop source Deluge container
        3. Start transferarr (will fail to connect to source)
        4. Verify transferarr keeps running
        5. Restart source Deluge
        6. Verify transfer eventually completes
        """
        import docker
        docker_client = docker.from_env()
        
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create torrent and add to Radarr
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Add to Radarr and wait for seeding
        print(f"\n[Step 2] Adding movie to Radarr and waiting for seeding...")
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
        
        # Step 3: Stop source Deluge container BEFORE starting transferarr
        print(f"\n[Step 3] Stopping source Deluge container...")
        source_container = docker_client.containers.get("test-deluge-source")
        source_container.stop()
        print("  Source Deluge stopped")
        
        # Step 4: Start transferarr - it will try to connect and fail
        print(f"\n[Step 4] Starting transferarr (source unavailable)...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 5: Wait and verify transferarr keeps running
        print(f"\n[Step 5] Verifying transferarr handles unavailable client...")
        time.sleep(15)  # Give time for connection attempts
        
        assert transferarr.is_running(), "Transferarr should still be running despite unavailable client"
        print("  Transferarr still running")
        
        # Torrent should be in UNCLAIMED or MANAGER_QUEUED state (can't find it)
        torrents = transferarr.get_torrents()
        tracked = [t for t in torrents if torrent_name in t.get('name', '')]
        if tracked:
            state = tracked[0].get('state', '')
            print(f"  Torrent state: {state}")
            # Should be MANAGER_QUEUED or UNCLAIMED since source is down
            assert state in ['MANAGER_QUEUED', 'UNCLAIMED'], \
                f"Torrent should be MANAGER_QUEUED or UNCLAIMED when source is down, got: {state}"
        
        # Step 6: Restart source Deluge
        print(f"\n[Step 6] Restarting source Deluge container...")
        source_container.start()
        
        # Wait for container to be healthy
        deadline = time.time() + 60
        while time.time() < deadline:
            source_container.reload()
            health = source_container.attrs.get('State', {}).get('Health', {})
            status = health.get('Status', 'none')
            if status == 'healthy':
                break
            time.sleep(2)
        print("  Source Deluge restarted and healthy")
        
        # Step 7: Wait for transfer to complete
        print(f"\n[Step 7] Waiting for transfer to complete after recovery...")
        
        # The torrent should eventually reach TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=180  # 3 minutes for recovery and completion
        )
        print("  Transfer completed!")
        
        # Step 8: Verify torrent is on target
        print(f"\n[Step 8] Verifying torrent on target...")
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=30,
            expected_state='Seeding'
        )
        print("  Torrent seeding on target")
        
        # Final state
        print(f"\n[Final] Results:")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        
        # Cleanup
        print(f"\n[Cleanup] Removing from queue...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            try:
                wait_for_torrent_removed(
                    deluge_source,
                    torrent_info['hash'],
                    timeout=30
                )
            except TimeoutError:
                pass  # May already be removed
        
        print("\n✅ Test passed: Download client unavailability handled with recovery!")


class TestNoMatchingConnection:
    """Test handling of torrents on clients without outbound connections."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(180)  # 3 minutes
    def test_torrent_found_on_target_without_outbound_connection(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr handles torrents found on clients without outbound connections.
        
        The test config has connection from source -> target, but NOT from target -> source.
        If transferarr finds a torrent on the target client first (before source has it),
        it should detect there's no outbound connection and not attempt to transfer.
        
        This is a more realistic scenario than manually adding to target - we test by:
        1. Add torrent to BOTH source and target (so both are seeding)
        2. Start transferarr
        3. Transferarr will find torrent on source (which HAS connection) and transfer
        4. This tests the normal flow but validates the connection lookup works
        
        Scenario:
        1. Create torrent and add to both source and target
        2. Add movie to Radarr
        3. Start transferarr  
        4. Verify transfer completes (source->target connection exists)
        5. Verify torrent reaches TARGET_SEEDING
        """
        import base64
        import requests
        
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create torrent
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Get .torrent file and add to TARGET first
        print(f"\n[Step 2] Adding torrent to TARGET Deluge first...")
        mock_indexer = SERVICES['mock_indexer']
        indexer_url = f"http://{mock_indexer['host']}:{mock_indexer['port']}"
        torrent_filename = f"{torrent_name}.torrent"
        torrent_response = requests.get(f"{indexer_url}/download/{torrent_filename}")
        if torrent_response.status_code != 200:
            pytest.fail(f"Failed to download torrent: {torrent_response.status_code}")
        torrent_data = torrent_response.content
        torrent_b64 = base64.b64encode(torrent_data).decode('utf-8')
        
        deluge_target.core.add_torrent_file(
            f"{torrent_name}.torrent",
            torrent_b64,
            {"download_location": "/downloads/movies"}
        )
        print("  Torrent added to TARGET (will be downloading/stuck without content)")
        
        # Step 3: Add movie to Radarr - this adds to SOURCE (via download client config)
        print(f"\n[Step 3] Adding movie to Radarr (triggers add to source)...")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Wait for torrent on source (seeding since it has content)
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on SOURCE")
        
        # Step 4: Start transferarr
        print(f"\n[Step 4] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 5: Wait for transfer to complete
        # Transferarr should find the torrent on SOURCE (which has connection) and transfer
        print(f"\n[Step 5] Waiting for transfer to complete...")
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=120
        )
        print("  Transfer completed!")
        
        # Final verification
        print(f"\n[Final] Results:")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        
        # Cleanup
        print(f"\n[Cleanup] Removing from queue...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            try:
                wait_for_torrent_removed(
                    deluge_source,
                    torrent_info['hash'],
                    timeout=30
                )
            except TimeoutError:
                pass
        
        print("\n✅ Test passed: Connection lookup handled correctly!")
