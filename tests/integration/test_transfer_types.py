"""
Integration tests for different transfer type combinations.

These tests verify that file transfers work correctly across all supported
transfer type combinations:
- sftp-to-local: SFTP source → Local destination
- local-to-sftp: Local source → SFTP destination  
- sftp-to-sftp: SFTP source → SFTP destination (default)
- local-to-local: Local source → Local destination

Each test uses the LifecycleRunner for standardized migration testing.
"""
import pytest

from tests.conftest import TIMEOUTS, TRANSFER_TYPE_CONFIGS


# Transfer types to test - parameterized
TRANSFER_TYPES = list(TRANSFER_TYPE_CONFIGS.keys())


class TestTransferTypes:
    """Test all transfer type combinations using parameterized tests."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    @pytest.mark.parametrize('transfer_type', TRANSFER_TYPES)
    def test_movie_migration(
        self,
        transfer_type,
        configure_transfer_type,
        lifecycle_runner,
    ):
        """
        Test complete movie migration lifecycle for each transfer type.
        
        Verifies:
        1. Torrent created and added to mock indexer
        2. Movie added to Radarr, grabs torrent
        3. Torrent appears in source Deluge
        4. Transferarr configured with transfer type
        5. Files transferred via configured method
        6. Torrent added to target Deluge
        7. Torrent removed from source after verification
        """
        # Configure transfer type before running lifecycle
        configure_transfer_type(transfer_type)
        print(f"\n=== Testing transfer type: {transfer_type} ===")
        
        # Run full migration test with cleanup verification
        lifecycle_runner.run_migration_test('radarr', verify_cleanup=True)
        
        print(f"=== Transfer type {transfer_type}: SUCCESS ===")
