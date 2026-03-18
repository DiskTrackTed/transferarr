"""Integration tests for local source access in torrent transfers.

Tests the full torrent transfer lifecycle using local filesystem access to
.torrent files (instead of SFTP), verifying end-to-end correctness against
the real Docker test environment.

The Docker Compose test environment mounts the `source-state` volume into:
- `deluge-source` at `/config/state` (Deluge's state directory)
- `transferarr` at `/source-state` (read-only)

So a local-source config uses `state_dir: "/source-state"` to read .torrent
files directly from the filesystem.
"""

import pytest
import time

from tests.conftest import TIMEOUTS
from tests.utils import (
    movie_catalog,
    show_catalog,
    make_torrent_name,
    make_episode_name,
    wait_for_queue_item_by_hash,
    wait_for_sonarr_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    decode_bytes,
)


@pytest.fixture
def local_source_config():
    """Return the config type for torrent transfers with local source access."""
    return "torrent-transfer-local-source"


class TestTorrentTransferLocalSource:
    """Tests for torrent transfer lifecycle using local .torrent file access."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_local_source_radarr_lifecycle(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        local_source_config,
    ):
        """Test complete Radarr migration using local source access.

        Exercises _fetch_torrent_file_locally() in the real Docker environment:
        1. Radarr adds movie to queue
        2. Torrent seeds on source
        3. Transferarr reads .torrent file from local mount (/source-state)
        4. Transfer torrent created, target downloads via BitTorrent
        5. Original torrent added to target via .torrent file
        6. Torrent reaches TARGET_SEEDING on target
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # Create and add torrent
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        # Wait for Radarr to grab torrent
        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)

        # Wait for source to be seeding
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Start transferarr with local source config
        transferarr.start(config_type=local_source_config, wait_healthy=True)

        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # Verify original is seeding on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_local_source_sonarr_episode(
        self,
        create_torrent,
        sonarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        local_source_config,
    ):
        """Test Sonarr episode migration using local source access.

        Same as test_local_source_radarr_lifecycle but with a TV episode,
        verifying local source works with Sonarr's queue management too.
        """
        show = show_catalog.get_show()

        # Add series to Sonarr
        added_series = sonarr_client.add_series(
            title=show['title'],
            tvdb_id=show['tvdb_id'],
            search=False
        )
        series_id = added_series['id']

        # Wait for episodes to be populated
        episodes = []
        for _ in range(20):
            episodes = sonarr_client.get_episodes(series_id)
            if episodes:
                break
            time.sleep(1)

        assert episodes, "Episodes should be populated"

        # Find first regular episode (season > 0)
        regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
        target_ep = regular_episodes[0] if regular_episodes else episodes[0]

        # Create episode torrent
        torrent_name = make_episode_name(
            added_series['title'],
            target_ep['seasonNumber'],
            target_ep['episodeNumber']
        )

        torrent_info = create_torrent(torrent_name, size_mb=150)
        original_hash = torrent_info['hash']

        # Trigger search
        time.sleep(5)  # Wait for indexer to see torrent
        sonarr_client.search_series(series_id)

        # Wait for Sonarr to grab
        wait_for_sonarr_queue_item_by_hash(sonarr_client, original_hash, timeout=120)

        # Wait for source to seed
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Start transferarr with local source config
        transferarr.start(config_type=local_source_config, wait_healthy=True)

        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # Verify original on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )
