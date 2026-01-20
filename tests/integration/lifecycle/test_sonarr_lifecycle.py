"""
Integration tests for the complete Sonarr torrent transfer lifecycle.

These tests verify that Transferarr correctly handles TV shows from Sonarr,
including single episodes, multi-episode torrents, and season packs.
"""
import pytest
from tests.conftest import TIMEOUTS

class TestSonarrLifecycle:
    """Test the complete Sonarr torrent transfer lifecycle."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_sonarr_complete_lifecycle(self, lifecycle_runner):
        """Test the complete Sonarr lifecycle for a single episode."""
        lifecycle_runner.run_migration_test('sonarr', item_type='episode')

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_sonarr_multi_episode_torrent(self, lifecycle_runner):
        """Test a torrent containing multiple episodes (e.g., S01E01-E02)."""
        lifecycle_runner.run_migration_test('sonarr', item_type='multi-episode')

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_sonarr_season_pack(self, lifecycle_runner):
        """Test a season pack torrent (e.g., S01)."""
        lifecycle_runner.run_migration_test('sonarr', item_type='season-pack', show_key='the_flash', season_number=1)

