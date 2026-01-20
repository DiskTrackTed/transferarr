"""
Integration tests for concurrent torrent transfers.

These tests verify that Transferarr correctly handles multiple
torrents being transferred at the same time.
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
    make_torrent_name,
)
from tests.conftest import TIMEOUTS


class TestConcurrentTransfers:
    """Test concurrent torrent transfer handling."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)  # Longer timeout for multiple transfers
    def test_two_simultaneous_transfers(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that two torrents can be transferred simultaneously.
        
        Scenario:
        1. Create two test torrents
        2. Add both movies to Radarr
        3. Wait for both to be seeding on source
        4. Start transferarr
        5. Verify both transfer to target
        """
        # Get two movies from the catalog
        movie1, movie2 = movie_catalog.get_movies(2)
        
        torrent_name1 = make_torrent_name(movie1['title'], movie1['year'])
        torrent_name2 = make_torrent_name(movie2['title'], movie2['year'])
        
        # Step 1: Create both test torrents
        print(f"\n[Step 1] Creating two test torrents...")
        torrent_info1 = create_torrent(torrent_name1, size_mb=10)
        torrent_info2 = create_torrent(torrent_name2, size_mb=10)
        print(f"  Torrent 1: {torrent_name1} ({torrent_info1['hash'][:8]}...)")
        print(f"  Torrent 2: {torrent_name2} ({torrent_info2['hash'][:8]}...)")
        
        # Step 2: Add both movies to Radarr
        print(f"\n[Step 2] Adding movies to Radarr...")
        added_movie1 = radarr_client.add_movie(
            title=movie1['title'],
            tmdb_id=movie1['tmdb_id'],
            year=movie1['year'],
            search=True
        )
        added_movie2 = radarr_client.add_movie(
            title=movie2['title'],
            tmdb_id=movie2['tmdb_id'],
            year=movie2['year'],
            search=True
        )
        print(f"  Movie 1 ID: {added_movie1['id']}")
        print(f"  Movie 2 ID: {added_movie2['id']}")
        
        # Trigger searches
        time.sleep(2)
        radarr_client.search_movie(added_movie1['id'])
        radarr_client.search_movie(added_movie2['id'])
        
        # Step 3: Wait for both torrents to be seeding on source
        print(f"\n[Step 3] Waiting for both torrents to be seeding...")
        
        # Use hash-based matching for reliability
        wait_for_queue_item_by_hash(radarr_client, torrent_info1['hash'], timeout=60, expected_status='completed')
        wait_for_queue_item_by_hash(radarr_client, torrent_info2['hash'], timeout=60, expected_status='completed')
        
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info1['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info2['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Both torrents seeding on source")
        
        # Verify source has 2 torrents
        source_count = get_deluge_torrent_count(deluge_source)
        assert source_count == 2, f"Source should have 2 torrents, has {source_count}"
        
        # Step 4: Start transferarr
        print(f"\n[Step 4] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 5: Wait for both transfers to complete
        print(f"\n[Step 5] Waiting for both transfers to complete...")
        
        # Wait for both torrents to appear on target
        target_torrent1 = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info1['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        print(f"  Torrent 1 on target: {target_torrent1.get('state')}")
        
        target_torrent2 = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info2['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        print(f"  Torrent 2 on target: {target_torrent2.get('state')}")
        
        # Wait for both to reach TARGET_SEEDING in transferarr
        wait_for_transferarr_state(
            transferarr,
            torrent_name1,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        wait_for_transferarr_state(
            transferarr,
            torrent_name2,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  Both torrents at TARGET_SEEDING")
        
        # Step 6: Verify final state
        print(f"\n[Step 6] Verifying final state...")
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Target Deluge torrents: {target_count}")
        assert target_count == 2, f"Target should have 2 torrents, has {target_count}"
        
        # Step 7: Clean up both - remove from queue using helper
        print(f"\n[Step 7] Removing both from queue...")
        removed1 = remove_from_queue_by_name(radarr_client, torrent_name1)
        removed2 = remove_from_queue_by_name(radarr_client, torrent_name2)
        print(f"  Removed {int(removed1) + int(removed2)} queue items")
        
        # Wait for source cleanup
        wait_for_torrent_removed(
            deluge_source,
            torrent_info1['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        wait_for_torrent_removed(
            deluge_source,
            torrent_info2['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        print("  Both torrents removed from source")
        
        # Final verification
        final_source_count = get_deluge_torrent_count(deluge_source)
        final_target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"\n[Final] Results:")
        print(f"  Source torrents: {final_source_count}")
        print(f"  Target torrents: {final_target_count}")
        
        assert final_source_count == 0, f"Source should be empty, has {final_source_count}"
        assert final_target_count == 2, f"Target should have 2 torrents, has {final_target_count}"
        
        print("\n✅ Test passed: Two simultaneous transfers completed!")


class TestMaximumConcurrency:
    """
    Test 3.2: Maximum Concurrency (3 Transfers)
    
    Verify the system handles maximum concurrent load with 3 simultaneous transfers
    (matching ThreadPoolExecutor max_workers=3).
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(600)  # 10 minutes for 3 transfers
    def test_three_simultaneous_transfers(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test maximum concurrent transfers (3 = ThreadPoolExecutor max_workers).
        
        Scenario:
        1. Create 3 test torrents
        2. Add all 3 movies to Radarr
        3. Wait for all to be seeding on source
        4. Start transferarr
        5. Verify all 3 transfer to target simultaneously
        """
        # Get three movies
        movies = [movie_catalog.get_movie() for _ in range(3)]
        torrents_info = []
        
        # Step 1: Create all test torrents
        print(f"\n[Step 1] Creating 3 test torrents...")
        for i, movie in enumerate(movies):
            torrent_name = make_torrent_name(movie['title'], movie['year'])
            torrent_info = create_torrent(torrent_name, size_mb=10)
            
            torrents_info.append({
                'name': torrent_name,
                'hash': torrent_info['hash'],
                'movie': movie,
            })
            print(f"  Torrent {i+1}: {torrent_name} ({torrent_info['hash'][:8]}...)")
        
        # Step 2: Add all movies to Radarr
        print(f"\n[Step 2] Adding all movies to Radarr...")
        for info in torrents_info:
            added_movie = radarr_client.add_movie(
                title=info['movie']['title'],
                tmdb_id=info['movie']['tmdb_id'],
                year=info['movie']['year'],
                search=True
            )
            info['movie_id'] = added_movie['id']
            print(f"  Added: {info['movie']['title']} (ID: {added_movie['id']})")
        
        # Trigger searches
        time.sleep(2)
        for info in torrents_info:
            radarr_client.search_movie(info['movie_id'])
        
        # Step 3: Wait for all torrents to be seeding on source
        print(f"\n[Step 3] Waiting for all torrents to be seeding...")
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
        
        source_count = get_deluge_torrent_count(deluge_source)
        assert source_count == 3, f"Source should have 3 torrents, has {source_count}"
        print(f"  Verified {source_count} torrents on source")
        
        # Step 4: Start transferarr and measure time
        print(f"\n[Step 4] Starting transferarr...")
        start_time = time.time()
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 5: Wait for all transfers to complete
        print(f"\n[Step 5] Waiting for all 3 transfers to complete...")
        
        # Wait for all to reach TARGET_SEEDING
        for info in torrents_info:
            wait_for_transferarr_state(
                transferarr,
                info['name'],
                expected_state='TARGET_SEEDING',
                timeout=TIMEOUTS['state_transition']
            )
            print(f"  {info['name']}: TARGET_SEEDING")
        
        transfer_time = time.time() - start_time
        print(f"  Total transfer time: {transfer_time:.1f}s")
        
        # Step 6: Verify all torrents on target
        print(f"\n[Step 6] Verifying all torrents on target...")
        for info in torrents_info:
            target_torrent = wait_for_torrent_in_deluge(
                deluge_target,
                info['hash'],
                timeout=30,
                expected_state='Seeding'
            )
            print(f"  {info['name']}: {target_torrent.get('state')}")
        
        target_count = get_deluge_torrent_count(deluge_target)
        assert target_count == 3, f"Target should have 3 torrents, has {target_count}"
        
        # Step 7: Clean up
        print(f"\n[Step 7] Cleaning up...")
        for info in torrents_info:
            removed = remove_from_queue_by_name(radarr_client, info['name'])
            if removed:
                wait_for_torrent_removed(
                    deluge_source,
                    info['hash'],
                    timeout=TIMEOUTS['state_transition']
                )
                print(f"  {info['name']}: cleaned up")
        
        # Final verification
        final_source_count = get_deluge_torrent_count(deluge_source)
        final_target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"\n[Final] Results:")
        print(f"  Source torrents: {final_source_count}")
        print(f"  Target torrents: {final_target_count}")
        print(f"  Transfer time: {transfer_time:.1f}s (3 concurrent transfers)")
        
        assert final_source_count == 0, f"Source should be empty, has {final_source_count}"
        assert final_target_count == 3, f"Target should have 3 torrents, has {final_target_count}"
        
        print("\n✅ Test passed: 3 simultaneous transfers (max concurrency) completed!")


class TestQueueOverflow:
    """
    Test 7.2: Queue Overflow (5 Torrents with max_workers=3)
    
    Verify that when more torrents are ready than worker slots available,
    the system queues them properly and processes them as slots free up.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(900)  # 15 minutes for 5 transfers with queueing
    def test_queue_overflow_five_torrents(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test queue overflow with 5 torrents (max_workers=3).
        
        Scenario:
        1. Create 5 test torrents
        2. Add all 5 movies to Radarr
        3. Wait for all to be seeding on source
        4. Start transferarr
        5. Verify first 3 start transferring immediately
        6. Verify remaining 2 wait and start as slots open
        7. Verify all 5 eventually reach TARGET_SEEDING
        """
        NUM_TORRENTS = 5
        
        # Get five movies
        movies = [movie_catalog.get_movie() for _ in range(NUM_TORRENTS)]
        torrents_info = []
        
        # Step 1: Create all test torrents
        print(f"\n[Step 1] Creating {NUM_TORRENTS} test torrents...")
        for i, movie in enumerate(movies):
            torrent_name = make_torrent_name(movie['title'], movie['year'])
            torrent_info = create_torrent(torrent_name, size_mb=10)
            
            torrents_info.append({
                'name': torrent_name,
                'hash': torrent_info['hash'],
                'movie': movie,
            })
            print(f"  Torrent {i+1}: {torrent_name} ({torrent_info['hash'][:8]}...)")
        
        # Step 2: Add all movies to Radarr
        print(f"\n[Step 2] Adding all movies to Radarr...")
        for info in torrents_info:
            added_movie = radarr_client.add_movie(
                title=info['movie']['title'],
                tmdb_id=info['movie']['tmdb_id'],
                year=info['movie']['year'],
                search=True
            )
            info['movie_id'] = added_movie['id']
            print(f"  Added: {info['movie']['title']} (ID: {added_movie['id']})")
        
        # Trigger searches
        time.sleep(2)
        for info in torrents_info:
            radarr_client.search_movie(info['movie_id'])
        
        # Step 3: Wait for all torrents to be seeding on source
        print(f"\n[Step 3] Waiting for all torrents to be seeding...")
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
        
        source_count = get_deluge_torrent_count(deluge_source)
        assert source_count == NUM_TORRENTS, f"Source should have {NUM_TORRENTS} torrents, has {source_count}"
        print(f"  Verified {source_count} torrents on source")
        
        # Step 4: Start transferarr and track timing
        print(f"\n[Step 4] Starting transferarr...")
        start_time = time.time()
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 5: Wait for all transfers to complete
        print(f"\n[Step 5] Waiting for all {NUM_TORRENTS} transfers to complete...")
        print("  (max_workers=3, so 2 should be queued initially)")
        
        completed_times = {}
        for info in torrents_info:
            wait_for_transferarr_state(
                transferarr,
                info['name'],
                expected_state='TARGET_SEEDING',
                timeout=TIMEOUTS['torrent_transfer']
            )
            completed_times[info['name']] = time.time() - start_time
            print(f"  {info['name']}: TARGET_SEEDING at {completed_times[info['name']]:.1f}s")
        
        total_time = time.time() - start_time
        print(f"  Total transfer time: {total_time:.1f}s")
        
        # Step 6: Verify all torrents on target
        print(f"\n[Step 6] Verifying all torrents on target...")
        for info in torrents_info:
            target_torrent = wait_for_torrent_in_deluge(
                deluge_target,
                info['hash'],
                timeout=30,
                expected_state='Seeding'
            )
            print(f"  {info['name']}: {target_torrent.get('state')}")
        
        target_count = get_deluge_torrent_count(deluge_target)
        assert target_count == NUM_TORRENTS, f"Target should have {NUM_TORRENTS} torrents, has {target_count}"
        
        # Step 7: Clean up
        print(f"\n[Step 7] Cleaning up...")
        for info in torrents_info:
            removed = remove_from_queue_by_name(radarr_client, info['name'])
            if removed:
                wait_for_torrent_removed(
                    deluge_source,
                    info['hash'],
                    timeout=TIMEOUTS['state_transition']
                )
        
        # Final verification
        final_source_count = get_deluge_torrent_count(deluge_source)
        final_target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"\n[Final] Results:")
        print(f"  Source torrents: {final_source_count}")
        print(f"  Target torrents: {final_target_count}")
        print(f"  Total time for {NUM_TORRENTS} torrents: {total_time:.1f}s")
        
        assert final_source_count == 0, f"Source should be empty, has {final_source_count}"
        assert final_target_count == NUM_TORRENTS, f"Target should have {NUM_TORRENTS} torrents, has {final_target_count}"
        
        print(f"\n✅ Test passed: {NUM_TORRENTS} torrents transferred with queue overflow!")


class TestMixedStateConcurrency:
    """
    Test 7.3: Mixed State Concurrency
    
    Verify the system handles torrents in different states simultaneously.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(600)  # 10 minutes
    def test_mixed_state_torrents(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test handling of torrents added at different times (staggered states).
        
        Scenario:
        1. Add first torrent and start transfer
        2. While first is in COPYING/TARGET_SEEDING, add second torrent
        3. Verify both are tracked correctly and reach TARGET_SEEDING
        4. Add third torrent after first two complete
        5. Verify all three end up on target
        
        This tests the system's ability to handle:
        - New torrents joining mid-transfer
        - Different torrents in different states simultaneously
        """
        # Get three movies
        movie1 = movie_catalog.get_movie()
        movie2 = movie_catalog.get_movie()
        movie3 = movie_catalog.get_movie()
        
        torrent_name1 = make_torrent_name(movie1['title'], movie1['year'])
        torrent_name2 = make_torrent_name(movie2['title'], movie2['year'])
        torrent_name3 = make_torrent_name(movie3['title'], movie3['year'])
        
        # Step 1: Create and add first torrent
        print(f"\n[Step 1] Creating and adding first torrent...")
        torrent_info1 = create_torrent(torrent_name1, size_mb=10)
        print(f"  Torrent 1: {torrent_name1}")
        
        added_movie1 = radarr_client.add_movie(
            title=movie1['title'],
            tmdb_id=movie1['tmdb_id'],
            year=movie1['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie1['id'])
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info1['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info1['hash'], timeout=TIMEOUTS['torrent_seeding'], expected_state='Seeding')
        print("  Torrent 1 seeding on source")
        
        # Step 2: Start transferarr
        print(f"\n[Step 2] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Wait for first torrent to start processing
        wait_for_transferarr_state(transferarr, torrent_name1, 'HOME_SEEDING', timeout=30)
        print("  Torrent 1 detected by transferarr")
        
        # Step 3: While first is transferring, add second torrent
        print(f"\n[Step 3] Adding second torrent while first is transferring...")
        torrent_info2 = create_torrent(torrent_name2, size_mb=10)
        print(f"  Torrent 2: {torrent_name2}")
        
        added_movie2 = radarr_client.add_movie(
            title=movie2['title'],
            tmdb_id=movie2['tmdb_id'],
            year=movie2['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie2['id'])
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info2['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info2['hash'], timeout=TIMEOUTS['torrent_seeding'], expected_state='Seeding')
        print("  Torrent 2 seeding on source")
        
        # Step 4: Wait for both to reach TARGET_SEEDING
        print(f"\n[Step 4] Waiting for both torrents to reach TARGET_SEEDING...")
        wait_for_transferarr_state(transferarr, torrent_name1, 'TARGET_SEEDING', timeout=TIMEOUTS['torrent_transfer'])
        print("  Torrent 1: TARGET_SEEDING")
        
        wait_for_transferarr_state(transferarr, torrent_name2, 'TARGET_SEEDING', timeout=TIMEOUTS['torrent_transfer'])
        print("  Torrent 2: TARGET_SEEDING")
        
        # Step 5: Add third torrent after first two have completed transfer
        print(f"\n[Step 5] Adding third torrent after first two completed...")
        torrent_info3 = create_torrent(torrent_name3, size_mb=10)
        print(f"  Torrent 3: {torrent_name3}")
        
        added_movie3 = radarr_client.add_movie(
            title=movie3['title'],
            tmdb_id=movie3['tmdb_id'],
            year=movie3['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie3['id'])
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info3['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info3['hash'], timeout=TIMEOUTS['torrent_seeding'], expected_state='Seeding')
        print("  Torrent 3 seeding on source")
        
        # Wait for third to reach TARGET_SEEDING
        wait_for_transferarr_state(transferarr, torrent_name3, 'TARGET_SEEDING', timeout=TIMEOUTS['torrent_transfer'])
        print("  Torrent 3: TARGET_SEEDING")
        
        # Step 6: Verify all torrents on target
        print(f"\n[Step 6] Verifying all torrents on target...")
        for torrent_hash, name in [(torrent_info1['hash'], torrent_name1), 
                                    (torrent_info2['hash'], torrent_name2),
                                    (torrent_info3['hash'], torrent_name3)]:
            target_torrent = wait_for_torrent_in_deluge(
                deluge_target,
                torrent_hash,
                timeout=30,
                expected_state='Seeding'
            )
            print(f"  {name}: {target_torrent.get('state')}")
        
        target_count = get_deluge_torrent_count(deluge_target)
        assert target_count == 3, f"Target should have 3 torrents, has {target_count}"
        
        # Step 7: Clean up - remove from Radarr queue
        print(f"\n[Step 7] Cleaning up Radarr queue...")
        for torrent_hash, name in [(torrent_info1['hash'], torrent_name1), 
                                    (torrent_info2['hash'], torrent_name2),
                                    (torrent_info3['hash'], torrent_name3)]:
            removed = remove_from_queue_by_name(radarr_client, name)
            print(f"  {name}: {'removed from queue' if removed else 'not in queue'}")
            # Wait for source removal if torrent is still there
            try:
                wait_for_torrent_removed(deluge_source, torrent_hash, timeout=30)
            except TimeoutError:
                pass  # Already removed
        
        # Final verification
        final_source_count = get_deluge_torrent_count(deluge_source)
        final_target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"\n[Final] Results:")
        print(f"  Source torrents: {final_source_count}")
        print(f"  Target torrents: {final_target_count}")
        
        assert final_source_count == 0, f"Source should be empty, has {final_source_count}"
        assert final_target_count == 3, f"Target should have 3 torrents, has {final_target_count}"
        
        print("\n✅ Test passed: Mixed state concurrency handled correctly!")
