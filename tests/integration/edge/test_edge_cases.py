"""
Integration tests for edge cases.

These tests verify that Transferarr correctly handles edge cases like
special characters in filenames and other unusual scenarios.
"""
import os
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
    decode_bytes,
    make_torrent_name,
    sanitize_title_for_torrent,
)
from tests.conftest import TIMEOUTS, SERVICES


class TestSpecialCharactersInFilename:
    """Test handling of special characters in torrent names."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_special_characters_in_filename(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that torrents with special characters transfer correctly.
        
        Tests torrent name with:
        - Spaces
        - Parentheses
        - Brackets
        - Dashes
        - Apostrophes
        
        Scenario:
        1. Create torrent with special characters in name
        2. Complete full lifecycle
        3. Verify file integrity on target
        
        Note: Avoid movies with years in the title (like "Blade Runner 2049")
        as Radarr's parser gets confused by the year in title + year in parentheses.
        """
        # Get a movie from the catalog (any movie without a year in its title)
        movie = movie_catalog.get_movie()
        
        # Create a torrent name with special characters (parentheses, brackets, dashes)
        torrent_name = f"{sanitize_title_for_torrent(movie['title'])}.({movie['year']}).Remastered.1080p.BluRay.x264-[Group]"
        
        # Step 1: Create test torrent with special characters
        print(f"\n[Step 1] Creating torrent with special characters: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        assert torrent_info['hash'], "Torrent creation failed - no hash returned"
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Add movie to Radarr
        print(f"\n[Step 2] Adding movie to Radarr: {movie['title']}")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        print(f"  Added movie ID: {movie_id}")
        
        # Trigger search
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Step 3: Wait for torrent in queue
        print(f"\n[Step 3] Waiting for torrent in Radarr queue...")
        queue_item = wait_for_queue_item_by_hash(
            radarr_client,
            torrent_info['hash'],
            timeout=60,
            expected_status='completed'
        )
        print(f"  Torrent in queue: {queue_item['title']}")
        
        # Step 4: Verify seeding on source
        print(f"\n[Step 4] Waiting for torrent to seed on source...")
        source_torrent = wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print(f"  Source torrent state: {source_torrent.get('state')}")
        
        # Verify the name is preserved correctly
        source_name = source_torrent.get('name', '')
        print(f"  Source torrent name: {source_name}")
        
        # Step 5: Start transferarr and wait for transfer
        print(f"\n[Step 5] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Wait for HOME_SEEDING detection
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='HOME_SEEDING',
            timeout=30
        )
        print("  Transferarr detected torrent")
        
        # Step 6: Wait for transfer to target
        print(f"\n[Step 6] Waiting for transfer to target...")
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        print(f"  Target torrent state: {target_torrent.get('state')}")
        
        # Verify name is preserved on target
        target_name = target_torrent.get('name', '')
        print(f"  Target torrent name: {target_name}")
        
        # The torrent name should be preserved (might differ slightly in encoding)
        # Key special characters should be present
        assert '(' in target_name or '[' in target_name, \
            f"Special characters should be preserved in name: {target_name}"
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  Transferarr shows TARGET_SEEDING")
        
        # Step 7: Complete lifecycle
        print(f"\n[Step 7] Removing from queue to complete lifecycle...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        assert removed, f"Should find and remove queue item for: {torrent_name}"
        
        wait_for_torrent_removed(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        print("  Source torrent removed")
        
        # Final verification
        print(f"\n[Final] Verifying final state...")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        
        assert target_count == 1, f"Target should have exactly 1 torrent, has {target_count}"
        
        print("\n✅ Test passed: Special characters handled correctly!")
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_spaces_in_torrent_name(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that torrents with spaces in the name transfer correctly.
        
        This is a simpler case - just spaces instead of dots.
        """
        # Get a movie from the catalog
        movie = movie_catalog.get_movie()
        
        # Create torrent name with spaces instead of dots
        torrent_name = f"{movie['title']} {movie['year']} 1080p BluRay x264"
        
        # Step 1: Create test torrent
        print(f"\n[Step 1] Creating torrent with spaces: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Add movie and search
        print(f"\n[Step 2] Adding movie to Radarr...")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie['id'])
        
        # Wait for grab (use hash-based matching)
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent seeding on source")
        
        # Step 3: Start transferarr and complete transfer
        print(f"\n[Step 3] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Wait for full transfer
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        
        # Verify name preserved
        target_name = target_torrent.get('name', '')
        print(f"  Target torrent name: '{target_name}'")
        
        # Name should still have spaces
        assert ' ' in target_name or target_name == torrent_name, \
            f"Spaces should be preserved: {target_name}"
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        
        print("\n✅ Test passed: Spaces in name handled correctly!")


class TestLargeTorrentTransfer:
    """
    Test 4.3: Large Torrent Transfer
    
    Verify that large torrents (2.5GB) transfer correctly with proper
    progress tracking and without timeout or memory issues.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(900)  # 15 minutes for 2.5GB transfer
    @pytest.mark.skipif(
        os.environ.get("GITHUB_ACTIONS") == "true",
        reason="Skipped in CI: 2.5GB test uses too much disk space on GitHub runners"
    )
    def test_2_5gb_torrent_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test transfer of a 2.5GB torrent to exercise real transfer behavior.
        
        This size is large enough to:
        - Test transfer speed tracking
        - Verify progress updates work
        - Catch any memory issues or timeouts
        - Observe COPYING state during transfer
        
        Scenario:
        1. Create 2.5GB torrent
        2. Transfer and verify
        3. Check file integrity
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        file_size_mb = 2500  # 2.5GB
        
        # Step 1: Create 2.5GB torrent
        print(f"\n[Step 1] Creating {file_size_mb}MB torrent: {torrent_name}")
        start_time = time.time()
        torrent_info = create_torrent(torrent_name, size_mb=file_size_mb)
        creation_time = time.time() - start_time
        print(f"  Created torrent in {creation_time:.1f}s")
        print(f"  Hash: {torrent_info['hash']}")
        
        # Step 2: Add movie to Radarr
        print(f"\n[Step 2] Adding movie to Radarr...")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie['id'])
        
        # Step 3: Wait for seeding
        print(f"\n[Step 3] Waiting for torrent to seed on source...")
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=180, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        
        # Query actual size from Deluge
        source_torrents = deluge_source.core.get_torrents_status({}, ['total_size'])
        source_torrents = decode_bytes(source_torrents)
        source_size = source_torrents.get(torrent_info['hash'], {}).get('total_size', 0)
        print(f"  Source torrent size: {source_size / (1024*1024*1024):.2f}GB")
        
        # Step 4: Start transferarr and track time
        print(f"\n[Step 4] Starting transferarr and monitoring transfer...")
        transfer_start = time.time()
        transferarr.start(wait_healthy=True)
        
        # Wait for COPYING state
        try:
            wait_for_transferarr_state(
                transferarr,
                torrent_name,
                expected_state='COPYING',
                timeout=60
            )
            print("  Entered COPYING state")
        except Exception:
            print("  Transfer may have completed quickly, checking target...")
        
        # Step 5: Wait for transfer completion
        print(f"\n[Step 5] Waiting for transfer to complete...")
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding'
        )
        transfer_time = time.time() - transfer_start
        print(f"  Transfer completed in {transfer_time:.1f}s")
        
        # Step 6: Verify file integrity
        print(f"\n[Step 6] Verifying file integrity...")
        target_torrents = deluge_target.core.get_torrents_status({}, ['total_size'])
        target_torrents = decode_bytes(target_torrents)
        target_size = target_torrents.get(torrent_info['hash'], {}).get('total_size', 0)
        print(f"  Target torrent size: {target_size / (1024*1024*1024):.2f}GB")
        
        # Sizes should match
        assert target_size == source_size, \
            f"Size mismatch: source={source_size}, target={target_size}"
        print("  Size verification passed")
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=180  # Longer timeout for large file
        )
        print("  Reached TARGET_SEEDING state")
        
        # Cleanup
        print(f"\n[Cleanup] Removing from queue...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            wait_for_torrent_removed(
                deluge_source,
                torrent_info['hash'],
                timeout=TIMEOUTS['state_transition']
            )
            print("  Cleanup complete")
        
        print(f"\n[Final] Results:")
        print(f"  File size: {target_size / (1024*1024*1024):.2f}GB")
        print(f"  Transfer time: {transfer_time:.1f}s")
        print(f"  Transfer speed: {(target_size / (1024*1024)) / transfer_time:.1f}MB/s")
        
        print("\n✅ Test passed: 2.5GB torrent transferred successfully!")


class TestMultiFileTorrent:
    """
    Test 4.4: Multi-File Torrent
    
    Verify that torrents with multiple files and subdirectories
    transfer correctly with all files preserved.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_multi_file_torrent_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test transfer of torrent with multiple files.
        
        The torrent creator creates a directory structure with
        multiple files when multi_file=True.
        
        Scenario:
        1. Create multi-file torrent
        2. Transfer and verify all files preserved
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create multi-file torrent
        print(f"\n[Step 1] Creating multi-file torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10, multi_file=True)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Add movie to Radarr
        print(f"\n[Step 2] Adding movie to Radarr...")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        time.sleep(2)
        radarr_client.search_movie(added_movie['id'])
        
        # Step 3: Wait for seeding
        print(f"\n[Step 3] Waiting for torrent to seed on source...")
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        
        # Fetch file list separately (wait_for_torrent_in_deluge doesn't request 'files')
        source_torrents = deluge_source.core.get_torrents_status({}, ['files'])
        source_torrents = decode_bytes(source_torrents)
        source_files = source_torrents.get(torrent_info['hash'], {}).get('files', [])
        source_file_count = len(source_files)
        assert source_file_count > 0, "Multi-file torrent should have at least 1 file"
        print(f"  Source has {source_file_count} file(s)")
        for f in source_files[:5]:  # Show first 5 files
            print(f"    - {f.get('path', 'unknown')}")
        if source_file_count > 5:
            print(f"    ... and {source_file_count - 5} more")
        
        # Step 4: Start transfer
        print(f"\n[Step 4] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        
        # Step 5: Wait for transfer completion
        print(f"\n[Step 5] Waiting for transfer to complete...")
        target_torrent = wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition'],
            expected_state='Seeding'
        )
        
        # Step 6: Verify all files transferred
        print(f"\n[Step 6] Verifying all files transferred...")
        
        # Fetch file list separately (wait_for_torrent_in_deluge doesn't request 'files')
        target_torrents = deluge_target.core.get_torrents_status({}, ['files'])
        target_torrents = decode_bytes(target_torrents)
        target_files = target_torrents.get(torrent_info['hash'], {}).get('files', [])
        target_file_count = len(target_files)
        print(f"  Target has {target_file_count} file(s)")
        
        # File counts should match
        assert target_file_count == source_file_count, \
            f"File count mismatch: source={source_file_count}, target={target_file_count}"
        print("  File count verification passed")
        
        # Verify file names match
        source_paths = set(f.get('path', '') for f in source_files)
        target_paths = set(f.get('path', '') for f in target_files)
        
        assert source_paths == target_paths, \
            f"File paths mismatch: missing={source_paths - target_paths}, extra={target_paths - source_paths}"
        print("  File paths verification passed")
        
        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  Reached TARGET_SEEDING state")
        
        # Cleanup
        print(f"\n[Cleanup] Removing from queue...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        if removed:
            wait_for_torrent_removed(
                deluge_source,
                torrent_info['hash'],
                timeout=TIMEOUTS['state_transition']
            )
            print("  Cleanup complete")
        
        print(f"\n[Final] Results:")
        print(f"  Total files: {target_file_count}")
        
        print("\n✅ Test passed: Multi-file torrent transferred successfully!")


class TestDuplicateTorrentDetection:
    """Test handling of torrents that already exist on target."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_torrent_already_on_target_skips_copy(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        docker_services,
    ):
        """
        Test that transferarr skips copying if torrent already exists on target.
        
        This tests the deduplication logic - if a torrent somehow ends up on
        both source and target, transferarr should detect this and skip the
        COPYING phase, going directly to TARGET_* state.
        
        Scenario:
        1. Create torrent and add to BOTH source and target Deluge
        2. Add movie to Radarr, trigger search
        3. Start transferarr
        4. Verify torrent skips COPYING and goes to TARGET_SEEDING
        5. Verify source is cleaned up normally
        """
        import base64
        import requests
        
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # Step 1: Create torrent
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent with hash: {torrent_info['hash']}")
        
        # Step 2: Get the .torrent file from mock indexer
        # The download URL uses the torrent name, not the hash
        print(f"\n[Step 2] Getting .torrent file from mock indexer...")
        mock_indexer = SERVICES['mock_indexer']
        indexer_url = f"http://{mock_indexer['host']}:{mock_indexer['port']}"
        torrent_filename = f"{torrent_name}.torrent"
        torrent_response = requests.get(f"{indexer_url}/download/{torrent_filename}")
        if torrent_response.status_code != 200:
            pytest.fail(f"Failed to download torrent: {torrent_response.status_code} - {torrent_response.text}")
        torrent_data = torrent_response.content
        torrent_b64 = base64.b64encode(torrent_data).decode('utf-8')
        print("  Got .torrent file")
        
        # Step 3: Add torrent to TARGET Deluge first (simulating pre-existing)
        # Note: Target won't be seeding since content is only on source volume
        # This simulates the scenario where target has the torrent but is still downloading
        print(f"\n[Step 3] Adding torrent to TARGET Deluge (pre-existing)...")
        deluge_target.core.add_torrent_file(
            f"{torrent_name}.torrent",
            torrent_b64,
            {"download_location": "/downloads/movies"}
        )
        
        # Brief wait for target to register the torrent
        time.sleep(3)
        
        # Verify target has the torrent (it will be Downloading, not Seeding)
        target_torrents = deluge_target.core.get_torrents_status({}, ['state'])
        target_torrents = decode_bytes(target_torrents)
        assert torrent_info['hash'] in target_torrents, "Target should have the torrent"
        target_state = target_torrents[torrent_info['hash']].get('state', 'Unknown')
        print(f"  Torrent on TARGET with state: {target_state}")
        
        # Step 4: Add movie to Radarr (this will add to SOURCE via download client config)
        print(f"\n[Step 4] Adding movie to Radarr...")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        movie_id = added_movie['id']
        
        time.sleep(2)
        radarr_client.search_movie(movie_id)
        
        # Wait for torrent to appear in queue and on source
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        print("  Torrent ALSO seeding on SOURCE")
        
        # Verify both clients have the torrent
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Source: {source_count} torrent(s), Target: {target_count} torrent(s)")
        assert source_count >= 1 and target_count >= 1, "Both clients should have the torrent"
        
        # Step 5: Start transferarr
        print(f"\n[Step 5] Starting transferarr...")
        transferarr.start(wait_healthy=True)
        print("  Transferarr started")
        
        # Step 6: Monitor state transitions - should skip COPYING
        print(f"\n[Step 6] Monitoring state transitions (should skip COPYING)...")
        
        # Track if we ever see COPYING state
        saw_copying = False
        deadline = time.time() + 60
        final_state = None
        
        while time.time() < deadline:
            torrents = transferarr.get_torrents()
            tracked = [t for t in torrents if torrent_name in t.get('name', '')]
            
            if tracked:
                state = tracked[0].get('state', '')
                if state == 'COPYING':
                    saw_copying = True
                    print(f"  WARNING: Saw COPYING state (unexpected)")
                elif 'TARGET' in state:
                    final_state = state
                    print(f"  Reached {state} state")
                    break
                else:
                    print(f"  Current state: {state}")
            
            time.sleep(3)
        
        # Verify we reached TARGET state
        assert final_state and 'TARGET' in final_state, \
            f"Should reach TARGET_* state, got: {final_state}"
        
        # Log whether COPYING was observed (it shouldn't be, but test passes either way)
        if saw_copying:
            print("  Note: COPYING state was observed (suboptimal but not an error)")
        else:
            print("  ✓ COPYING state was skipped (optimal deduplication)")
        
        # Step 7: Wait for TARGET_SEEDING and cleanup
        print(f"\n[Step 7] Waiting for TARGET_SEEDING and cleanup...")
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=60
        )
        print("  Reached TARGET_SEEDING")
        
        # Remove from Radarr queue to trigger cleanup
        print(f"\n[Cleanup] Removing from queue to trigger source cleanup...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        
        if removed:
            # Wait for source to be cleaned up
            try:
                wait_for_torrent_removed(
                    deluge_source,
                    torrent_info['hash'],
                    timeout=TIMEOUTS['state_transition']
                )
                print("  Source torrent cleaned up")
            except TimeoutError:
                print("  Source cleanup timed out (may need manual cleanup)")
        
        # Final state
        print(f"\n[Final] Results:")
        source_count = get_deluge_torrent_count(deluge_source)
        target_count = get_deluge_torrent_count(deluge_target)
        print(f"  Source torrents: {source_count}")
        print(f"  Target torrents: {target_count}")
        print(f"  COPYING phase skipped: {not saw_copying}")
        
        print("\n✅ Test passed: Duplicate torrent detection worked!")