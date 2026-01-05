"""
Show catalog validation tests.

These tests validate that all shows in the ShowCatalog work correctly with Sonarr.
They are not run as part of regular test suites - only when adding new shows to the catalog.

Run with: pytest tests/test_show_catalog.py -v
"""
import pytest
import time

from tests.utils import (
    wait_for_sonarr_queue_item_by_hash,
    clear_sonarr_state,
    clear_deluge_torrents,
    remove_from_sonarr_queue_by_name,
    show_catalog,
    make_episode_name,
)
from tests.conftest import TIMEOUTS


@pytest.mark.slow
class TestShowCatalogValidation:
    """Validate all shows in the catalog work with Sonarr."""
    
    @pytest.fixture(autouse=True)
    def setup(self, docker_services):
        """Ensure Docker services are running."""
        pass
    
    def test_all_shows_in_catalog(
        self,
        create_torrent,
        sonarr_client,
        deluge_source,
        deluge_target,
    ):
        """
        Test that each show in the catalog works with Sonarr.
        
        This test iterates through all shows, creates a torrent for each,
        adds it to Sonarr, and verifies that Sonarr can match and queue it.
        """
        # Get all shows from catalog
        total_shows = len(show_catalog.SHOWS)
        print(f"\n{'='*80}")
        print(f"Testing {total_shows} shows from catalog")
        print(f"{'='*80}\n")
        
        import os
        filter_show = os.environ.get('FILTER_SHOW')
        
        for idx, (show_key, show_data) in enumerate(show_catalog.SHOWS.items(), 1):
            show_title = show_data['title']
            tvdb_id = show_data['tvdb_id']
            
            if filter_show and filter_show.lower() not in show_title.lower():
                continue
            
            print(f"[{idx}/{total_shows}] Testing: {show_title}")
            print(f"            Key: {show_key}, TVDB ID: {tvdb_id}")
            
            # Clean state before testing this show
            clear_sonarr_state(sonarr_client)
            clear_deluge_torrents(deluge_source)
            clear_deluge_torrents(deluge_target)
            
            # Add show to Sonarr (without search yet)
            added_series = sonarr_client.add_series(
                title=show_title,
                tvdb_id=tvdb_id,
                search=False
            )
            
            # Get episodes to find a valid season/episode number
            episodes = []
            for _ in range(20): # Wait up to 20 seconds for episodes to populate
                episodes = sonarr_client.get_episodes(added_series['id'])
                if episodes:
                    break
                time.sleep(1)
                
            if not episodes:
                print(f"            ! Failed to get episodes for {show_title}")
                failed_shows.append(show_title)
                continue

            # Filter out specials (Season 0) if possible, otherwise take first
            regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
            target_ep = regular_episodes[0] if regular_episodes else episodes[0]
            
            season_num = target_ep['seasonNumber']
            episode_num = target_ep['episodeNumber']
            print(f"            Target Episode: S{season_num:02d}E{episode_num:02d}")
            
            # Create torrent name following release naming conventions
            # Format: Show.Title.S01E01.1080p.BluRay.x264
            # Use the title from Sonarr as it might be slightly different from our catalog
            torrent_name = make_episode_name(added_series['title'], season_num, episode_num)
            print(f"            Torrent Name: {torrent_name}")
            
            # Create the torrent
            torrent_info = create_torrent(torrent_name, size_mb=10)
            torrent_hash = torrent_info['hash']
            
            # Trigger search now that torrent exists
            sonarr_client.search_series(added_series['id'])
            
            # Wait for torrent to appear in queue
            wait_for_sonarr_queue_item_by_hash(
                sonarr_client,
                torrent_hash,
                timeout=TIMEOUTS['state_transition'],
                expected_status=None
            )
            
            # Clean up immediately
            remove_from_sonarr_queue_by_name(sonarr_client, torrent_name)
            sonarr_client.delete_series(added_series['id'], delete_files=True)
            
            print(f"            ✓ SUCCESS")
        
        print(f"\n{'='*80}")
        print(f"✓ All {total_shows} shows validated successfully!")
        print(f"{'='*80}")
