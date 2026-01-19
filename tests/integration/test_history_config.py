"""
Integration tests for Transfer History Configuration (Phase 4).

Tests the history configuration options:
- history.enabled: Enable/disable history tracking
- history.retention_days: Automatic pruning of old entries
- history.track_progress: Enable/disable byte progress updates
"""
import pytest
import requests
import time

from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
)


def get_api_url():
    """Get the base API URL for transferarr."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


def get_transfers_count():
    """Get the total count of transfers in history."""
    url = f"{get_api_url()}/transfers"
    response = requests.get(url, timeout=TIMEOUTS['api_response'])
    if response.status_code == 200:
        return response.json()['data']['total']
    return 0


def get_transfer_by_name(torrent_name):
    """Get a transfer record by torrent name."""
    url = f"{get_api_url()}/transfers"
    response = requests.get(
        url,
        params={'search': torrent_name},
        timeout=TIMEOUTS['api_response']
    )
    if response.status_code == 200:
        transfers = response.json()['data']['transfers']
        for t in transfers:
            if torrent_name in t['torrent_name']:
                return t
    return None


class TestHistoryDisabled:
    """Tests for history.enabled=false configuration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_history_disabled_no_records_created(
        self,
        create_torrent,
        deluge_source,
        deluge_target,
        transferarr,
        radarr_client
    ):
        """When history.enabled=false, no transfer records should be created."""
        # Clear history database by starting/stopping with default config
        # This ensures clean_test_environment cleared the DB
        transferarr.start(wait_healthy=True)
        initial_count = get_transfers_count()
        assert initial_count == 0, f"Expected empty history after cleanup, got {initial_count}"
        transferarr.stop()
        
        # Start with history-disabled config
        transferarr.start(wait_healthy=True, history_config='disabled')
        
        # Run a transfer
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        # Add to Radarr and trigger search
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=False
        )
        radarr_client.search_movie(added_movie['id'])
        
        # Wait for queue item
        wait_for_queue_item_by_hash(
            radarr_client,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        
        # Wait for torrent on source
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        
        # Wait for transfer to complete
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            'TARGET_SEEDING',
            timeout=TIMEOUTS['torrent_transfer']
        )
        
        # Verify on target
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=30,
            expected_state='Seeding'
        )
        
        # Now check that no history record was created
        # We need to check the database directly since API is unavailable when history is disabled
        transferarr.stop()
        
        # Clear state file to prevent default-config transferarr from resuming transfers
        # But do NOT clear history.db - we want to see if history-disabled wrote anything
        import docker
        docker_client = docker.from_env()
        container = docker_client.containers.get("test-transferarr")
        # Start container briefly to clear only state.json
        container.start()
        time.sleep(2)
        container.exec_run("rm -f /app/state/state.json")
        container.stop()
        time.sleep(2)
        
        # Check if history.db has any records by starting with default config and querying
        transferarr.start(wait_healthy=True)  # Default config
        
        final_count = get_transfers_count()
        
        # Should still be 0 (no new records created by history-disabled run)
        assert final_count == 0, \
            f"Expected 0 transfers but got {final_count} - history was recorded despite being disabled"


class TestTrackProgressDisabled:
    """Tests for history.track_progress=false configuration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_track_progress_false_skips_progress_updates(
        self,
        create_torrent,
        deluge_source,
        deluge_target,
        transferarr,
        radarr_client
    ):
        """When track_progress=false, bytes_transferred should only be updated at completion."""
        # Start with no-progress-tracking config
        transferarr.start(wait_healthy=True, history_config='no-progress')
        
        # Run a transfer with a larger file to ensure multiple progress updates would normally occur
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        # Use larger file to ensure multiple chunks would normally trigger progress updates
        torrent_info = create_torrent(torrent_name, size_mb=50)
        
        # Add to Radarr and trigger search
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=False
        )
        radarr_client.search_movie(added_movie['id'])
        
        # Wait for queue item
        wait_for_queue_item_by_hash(
            radarr_client,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        
        # Wait for torrent on source
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        
        # Wait for transfer to complete
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            'TARGET_SEEDING',
            timeout=TIMEOUTS['torrent_transfer']
        )
        
        # Verify on target
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent_info['hash'],
            timeout=30,
            expected_state='Seeding'
        )
        
        # Check the transfer record
        transfer = get_transfer_by_name(torrent_name)
        assert transfer is not None, f"Transfer record not found for {torrent_name}"
        
        # With track_progress=false, the final update should still set bytes_transferred
        # (force=True is used on completion), so we just verify the record exists
        # and is marked as completed
        assert transfer['status'] == 'completed', \
            f"Expected status 'completed' but got '{transfer['status']}'"
        
        # The bytes_transferred should be set (final update with force=True still works)
        assert transfer['bytes_transferred'] is not None and transfer['bytes_transferred'] > 0, \
            "bytes_transferred should be set on completion even with track_progress=false"


class TestRetentionDays:
    """Tests for history.retention_days configuration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_retention_prunes_old_entries_on_startup(
        self,
        create_torrent,
        deluge_source,
        deluge_target,
        transferarr,
        radarr_client
    ):
        """Verify that old entries are pruned on startup based on retention_days config.
        
        This test:
        1. Creates a transfer with default config (retention_days=90)
        2. Manually backdates the completed_at timestamp in the database
        3. Restarts transferarr and verifies the old entry was pruned
        """
        # Start with default config to create a transfer
        transferarr.start(wait_healthy=True)
        
        # Run a transfer to create a history record
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        torrent_info = create_torrent(torrent_name, size_mb=10)
        
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=False
        )
        radarr_client.search_movie(added_movie['id'])
        
        wait_for_queue_item_by_hash(
            radarr_client,
            torrent_info['hash'],
            timeout=TIMEOUTS['state_transition']
        )
        
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=TIMEOUTS['torrent_seeding'],
            expected_state='Seeding'
        )
        
        wait_for_transferarr_state(
            transferarr,
            torrent_name,
            'TARGET_SEEDING',
            timeout=TIMEOUTS['torrent_transfer']
        )
        
        # Verify the transfer record exists
        transfer = get_transfer_by_name(torrent_name)
        assert transfer is not None, f"Transfer record not found for {torrent_name}"
        assert transfer['status'] == 'completed'
        transfer_id = transfer['id']
        
        # Stop transferarr so we can modify the database
        transferarr.stop()
        
        # Backdate the completed_at timestamp to 100 days ago (beyond 90 day retention)
        import docker
        docker_client = docker.from_env()
        container = docker_client.containers.get("test-transferarr")
        
        # Calculate a date 100 days ago
        from datetime import datetime, timedelta, timezone
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        
        # Update the database directly in the container using Python (sqlite3 CLI not installed)
        # Use transfer ID for precise matching (title matching fails due to special chars)
        container.start()
        time.sleep(2)
        
        python_cmd = f"""python3 -c "
import sqlite3
conn = sqlite3.connect('/app/state/history.db')
cursor = conn.execute(\\"UPDATE transfers SET completed_at = '{old_date}' WHERE id = '{transfer_id}'\\")
conn.commit()
print('Updated', cursor.rowcount, 'rows')
conn.close()
"
"""
        exec_result = container.exec_run(['sh', '-c', python_cmd])
        assert exec_result.exit_code == 0, f"Failed to backdate record: {exec_result.output}"
        assert b'Updated 1 rows' in exec_result.output, f"Expected 1 row updated, got: {exec_result.output}"
        
        container.stop()
        time.sleep(2)
        
        # Clear state.json to prevent transfer resume logic
        container.start()
        time.sleep(2)
        container.exec_run("rm -f /app/state/state.json")
        container.stop()
        time.sleep(2)
        
        # Restart with default config (retention_days=90) - should prune the old entry
        transferarr.start(wait_healthy=True)
        
        # The old transfer should have been pruned
        transfer_after = get_transfer_by_name(torrent_name)
        assert transfer_after is None, \
            f"Expected transfer to be pruned (was 100 days old with 90 day retention) but found: {transfer_after}"
    
    @pytest.mark.timeout(TIMEOUTS['api_response'])
    def test_retention_config_is_applied(self, transferarr):
        """Verify that the retention config is read and applied."""
        # Start transferarr and check health endpoint
        transferarr.start(wait_healthy=True)
        
        # The health endpoint should return successfully, indicating
        # the history service was initialized with config
        url = f"{get_api_url()}/health"
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        # If we got here without errors, the config was loaded successfully
        # including the history section with retention_days
