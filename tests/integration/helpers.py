import time
import pytest
from tests.utils import (
    wait_for_queue_item_by_hash,
    wait_for_sonarr_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    movie_catalog,
    show_catalog,
    make_torrent_name,
    make_episode_name,
    make_multi_episode_name,
    make_season_pack_name,
    QueueItemError,
)
from tests.conftest import TIMEOUTS

class MediaManagerAdapter:
    """Unifies Radarr and Sonarr API calls for testing."""
    def __init__(self, client, type):
        self.client = client
        self.type = type # 'radarr' or 'sonarr'

    def add_item(self, item):
        if self.type == 'radarr':
            return self.client.add_movie(
                title=item['title'],
                tmdb_id=item['tmdb_id'],
                year=item['year'],
                search=False
            )
        else:
            return self.client.add_series(
                title=item['title'],
                tvdb_id=item['tvdb_id'],
                search=False
            )

    def search_item(self, item_id, season_number=None):
        if self.type == 'radarr':
            return self.client.search_movie(item_id)
        else:
            if season_number is not None:
                return self.client.search_season(item_id, season_number)
            return self.client.search_series(item_id)

    def wait_for_queue_item(self, torrent_hash, timeout=120, max_retries=2, search_callback=None):
        """
        Wait for a torrent to appear in the queue with automatic retry on errors.
        
        Args:
            torrent_hash: Torrent info hash
            timeout: Max wait time per attempt
            max_retries: Max retry attempts on queue errors (default 2)
            search_callback: Function to trigger new search on retry (takes no args)
            
        Returns:
            The queue item dict
            
        Raises:
            QueueItemError: If queue item has error after all retries
            TimeoutError: If torrent not found after all retries
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if self.type == 'radarr':
                    return wait_for_queue_item_by_hash(
                        self.client, torrent_hash, timeout=timeout, 
                        expected_status='completed', check_for_errors=True
                    )
                else:
                    return wait_for_sonarr_queue_item_by_hash(
                        self.client, torrent_hash, timeout=timeout,
                        expected_status='completed', check_for_errors=True
                    )
            except QueueItemError as e:
                last_error = e
                if attempt < max_retries:
                    print(f"  ⚠️ Queue error detected (attempt {attempt + 1}/{max_retries + 1}): {e}")
                    
                    # Remove failed item from queue
                    try:
                        queue_id = e.queue_item.get('id')
                        if queue_id:
                            print(f"  Removing failed queue item (id={queue_id})...")
                            self.client.remove_from_queue(queue_id)
                            time.sleep(2)
                    except Exception as remove_err:
                        print(f"  Warning: Failed to remove queue item: {remove_err}")
                    
                    # Trigger new search if callback provided
                    if search_callback:
                        print(f"  Triggering new search...")
                        search_callback()
                        time.sleep(5)  # Wait for search to trigger grab
                    continue
                else:
                    print(f"  ❌ Queue error after {max_retries + 1} attempts: {e}")
                    raise
            except TimeoutError as e:
                last_error = e
                if attempt < max_retries and search_callback:
                    print(f"  ⚠️ Timeout waiting for queue (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                    search_callback()
                    time.sleep(5)
                    continue
                raise
        
        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state in wait_for_queue_item")

    def get_episodes(self, item_id):
        if self.type == 'sonarr':
            return self.client.get_episodes(item_id)
        return []

class LifecycleRunner:
    """Helper to run standardized migration tests."""
    def __init__(self, create_torrent, deluge_source, deluge_target, transferarr, radarr_client, sonarr_client):
        self.create_torrent = create_torrent
        self.deluge_source = deluge_source
        self.deluge_target = deluge_target
        self.transferarr = transferarr
        self.radarr = MediaManagerAdapter(radarr_client, 'radarr')
        self.sonarr = MediaManagerAdapter(sonarr_client, 'sonarr')

    def run_migration_test(self, manager_type, item_type='movie', **kwargs):
        """
        Runs a full 7-step migration test.
        item_type: 'movie', 'episode', 'multi-episode', 'season-pack'
        
        kwargs:
            movie_key: specific key from movie_catalog (for radarr)
            show_key: specific key from show_catalog (for sonarr)
            season_number: season number for season-pack tests
            verify_cleanup: whether to verify cleanup after transfer
            size_mb: override default torrent size
        """
        from tests.utils import find_queue_item_by_name, find_sonarr_queue_item_by_name, wait_for_torrent_removed, get_deluge_torrent_count
        adapter = self.radarr if manager_type == 'radarr' else self.sonarr
        
        # Step 1: Setup Item
        print(f"\n[Step 1] Setting up {item_type} for {manager_type}...")
        if manager_type == 'radarr':
            movie_key = kwargs.get('movie_key')
            item = movie_catalog.get_movie(movie_key)
            torrent_name = make_torrent_name(item['title'], item['year'])
            size_mb = kwargs.get('size_mb', 10)
        else:
            show_key = kwargs.get('show_key')
            item = show_catalog.get_show(show_key)
            added_item = adapter.add_item(item)
            item_id = added_item['id']
            
            # Wait for episodes
            episodes = []
            for _ in range(20):
                episodes = adapter.get_episodes(item_id)
                if episodes: break
                time.sleep(1)
            
            if item_type == 'episode':
                regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
                target_ep = regular_episodes[0] if regular_episodes else episodes[0]
                torrent_name = make_episode_name(added_item['title'], target_ep['seasonNumber'], target_ep['episodeNumber'])
                size_mb = 150
            elif item_type == 'multi-episode':
                regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
                torrent_name = make_multi_episode_name(added_item['title'], regular_episodes[0]['seasonNumber'], regular_episodes[0]['episodeNumber'], regular_episodes[1]['episodeNumber'])
                size_mb = 300
            elif item_type == 'season-pack':
                season_num = kwargs.get('season_number', 1)
                torrent_name = make_season_pack_name(added_item['title'], season_num)
                size_mb = 2500
            
            item['id'] = item_id # Store for search step
            item['title'] = added_item['title'] # Use Sonarr's title

        # Step 2: Create Torrent
        print(f"\n[Step 2] Creating torrent: {torrent_name}")
        torrent_info = self.create_torrent(torrent_name, size_mb=size_mb)
        
        # Delay to ensure mock indexer detects and can serve the new torrent
        # This is necessary because the mock indexer reads from the shared volume
        # and there may be slight delays in filesystem visibility
        time.sleep(5)
        
        # Step 3: Trigger Search
        print(f"\n[Step 3] Triggering search...")
        if manager_type == 'radarr':
            added_item = adapter.add_item(item)
            print(f"  Added movie: {added_item['title']} (ID: {added_item['id']})")
            adapter.search_item(added_item['id'])
            # Create search callback for retries
            search_callback = lambda: adapter.search_item(added_item['id'])
        else:
            season_num = kwargs.get('season_number') if item_type == 'season-pack' else None
            adapter.search_item(item['id'], season_number=season_num)
            # Create search callback for retries
            search_callback = lambda: adapter.search_item(item['id'], season_number=season_num)

        # Step 4: Wait for Queue (with automatic retry on errors)
        print(f"\n[Step 4] Waiting for queue...")
        adapter.wait_for_queue_item(torrent_info['hash'], search_callback=search_callback)

        # Step 5: Verify Source
        print(f"\n[Step 5] Verifying source Deluge...")
        wait_for_torrent_in_deluge(self.deluge_source, torrent_info['hash'], timeout=TIMEOUTS['torrent_seeding'], expected_state='Seeding')

        # Step 6: Transfer
        print(f"\n[Step 6] Starting transferarr...")
        self.transferarr.start(wait_healthy=True)
        wait_for_transferarr_state(self.transferarr, torrent_name, 'TARGET_SEEDING', timeout=TIMEOUTS['torrent_transfer'])

        # Step 7: Verify Target
        print(f"\n[Step 7] Verifying target Deluge...")
        wait_for_torrent_in_deluge(self.deluge_target, torrent_info['hash'], timeout=30, expected_state='Seeding')
        
        # Optional Step 8: Cleanup (if requested)
        if kwargs.get('verify_cleanup', False):
            print(f"\n[Step 8] Verifying cleanup...")
            if manager_type == 'radarr':
                queue_item = find_queue_item_by_name(adapter.client, torrent_name)
            else:
                queue_item = find_sonarr_queue_item_by_name(adapter.client, torrent_name)
            
            assert queue_item, f"Could not find queue item to remove for torrent: {torrent_name}"
            adapter.client.remove_from_queue(queue_item['id'])
            
            wait_for_torrent_removed(self.deluge_source, torrent_info['hash'], timeout=TIMEOUTS['state_transition'])
            print("  Torrent removed from source Deluge")

        print("  Success!")
        return torrent_info
