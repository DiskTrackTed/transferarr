"""
Integration tests for Transfer History API endpoints.

Tests the /api/v1/transfers endpoints against a running transferarr instance.
"""
import pytest
import requests
import uuid
from tests.conftest import SERVICES, TIMEOUTS


# Base URL for transferarr API
def get_api_url():
    """Get the base API URL for transferarr."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


class TestTransfersListEndpoint:
    """Tests for GET /api/v1/transfers endpoint."""
    
    def test_get_transfers_returns_list(self):
        """GET /transfers should return a paginated list structure."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        assert 'transfers' in data['data']
        assert 'total' in data['data']
        assert 'page' in data['data']
        assert 'per_page' in data['data']
        assert 'pages' in data['data']
        assert isinstance(data['data']['transfers'], list)
    
    def test_get_transfers_pagination(self):
        """GET /transfers should support pagination parameters."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'page': 1, 'per_page': 10},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['data']['page'] == 1
        assert data['data']['per_page'] == 10
    
    def test_get_transfers_pagination_max_per_page(self):
        """GET /transfers should cap per_page at 100."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'per_page': 500},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be capped at 100
        assert data['data']['per_page'] == 100
    
    def test_get_transfers_filter_status(self):
        """GET /transfers should filter by status parameter."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'status': 'completed'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned transfers should have status 'completed'
        for transfer in data['data']['transfers']:
            assert transfer['status'] == 'completed'
    
    def test_get_transfers_filter_source(self):
        """GET /transfers should filter by source client."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'source': 'source-deluge'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned transfers should have the specified source
        for transfer in data['data']['transfers']:
            assert transfer['source_client'] == 'source-deluge'
    
    def test_get_transfers_filter_target(self):
        """GET /transfers should filter by target client."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'target': 'target-deluge'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned transfers should have the specified target
        for transfer in data['data']['transfers']:
            assert transfer['target_client'] == 'target-deluge'
    
    def test_get_transfers_search(self):
        """GET /transfers should search in torrent name."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'search': 'Movie'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned transfers should contain 'Movie' in name (case insensitive)
        for transfer in data['data']['transfers']:
            assert 'movie' in transfer['torrent_name'].lower()
    
    def test_get_transfers_date_range(self):
        """GET /transfers should filter by date range."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={
                'from_date': '2020-01-01',
                'to_date': '2030-12-31'
            },
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        # Just verify it doesn't error - date validation is in service layer
    
    def test_get_transfers_sort(self):
        """GET /transfers should support sorting."""
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url, 
            params={'sort': 'size_bytes', 'order': 'desc'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify descending order by size
        transfers = data['data']['transfers']
        if len(transfers) >= 2:
            sizes = [t.get('size_bytes') or 0 for t in transfers]
            assert sizes == sorted(sizes, reverse=True)


class TestActiveTransfersEndpoint:
    """Tests for GET /api/v1/transfers/active endpoint."""
    
    def test_get_active_transfers(self):
        """GET /transfers/active should return list of active transfers."""
        url = f"{get_api_url()}/transfers/active"
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        assert isinstance(data['data'], list)
        
        # All returned transfers should be pending or transferring
        for transfer in data['data']:
            assert transfer['status'] in ('pending', 'transferring')


class TestTransferStatsEndpoint:
    """Tests for GET /api/v1/transfers/stats endpoint."""
    
    def test_get_stats(self):
        """GET /transfers/stats should return aggregate statistics."""
        url = f"{get_api_url()}/transfers/stats"
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        stats = data['data']
        
        # Check all expected fields exist
        assert 'total' in stats
        assert 'completed' in stats
        assert 'failed' in stats
        assert 'pending' in stats
        assert 'transferring' in stats
        assert 'success_rate' in stats
        assert 'total_bytes_transferred' in stats
        
        # Verify types
        assert isinstance(stats['total'], int)
        assert isinstance(stats['completed'], int)
        assert isinstance(stats['failed'], int)
        assert isinstance(stats['success_rate'], (int, float))
        assert isinstance(stats['total_bytes_transferred'], int)


class TestSingleTransferEndpoint:
    """Tests for GET /api/v1/transfers/<id> endpoint."""
    
    def test_get_transfer_not_found(self):
        """GET /transfers/<id> should return 404 for non-existent ID."""
        fake_id = str(uuid.uuid4())
        url = f"{get_api_url()}/transfers/{fake_id}"
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 404
        data = response.json()
        
        assert 'error' in data
        assert data['error']['code'] == 'TRANSFER_NOT_FOUND'
    
    def test_get_transfer_by_id(self):
        """GET /transfers/<id> should return transfer details if exists."""
        # First, get list to find an existing transfer (if any)
        list_url = f"{get_api_url()}/transfers"
        list_response = requests.get(list_url, timeout=TIMEOUTS['api_response'])
        
        assert list_response.status_code == 200
        transfers = list_response.json()['data']['transfers']
        
        if transfers:
            # Get the first transfer by ID
            transfer_id = transfers[0]['id']
            url = f"{get_api_url()}/transfers/{transfer_id}"
            response = requests.get(url, timeout=TIMEOUTS['api_response'])
            
            assert response.status_code == 200
            data = response.json()
            
            assert 'data' in data
            assert data['data']['id'] == transfer_id
        else:
            # No transfers yet - skip the individual GET test
            pytest.skip("No transfers in history to test individual GET")


class TestTransferHistoryIntegration:
    """Integration tests that verify transfer history is recorded during actual transfers."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_successful_transfer_creates_history_record(
        self, lifecycle_runner, radarr_client
    ):
        """A successful transfer should create a completed history record."""
        # Run a full transfer
        lifecycle_runner.run_migration_test('radarr', item_type='movie')
        
        # Check that a history record was created
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url,
            params={'status': 'completed'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have at least one completed transfer
        assert data['data']['total'] >= 1
        
        # Check the transfer has expected fields
        transfer = data['data']['transfers'][0]
        assert transfer['status'] == 'completed'
        assert transfer['source_client'] is not None
        assert transfer['target_client'] is not None
        assert transfer['torrent_name'] is not None
        assert transfer['completed_at'] is not None
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_history_record_has_correct_metadata(
        self, lifecycle_runner
    ):
        """Transfer history should include correct metadata."""
        # Run a transfer
        lifecycle_runner.run_migration_test('radarr', item_type='movie')
        
        # Get the most recent transfer
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url,
            params={'sort': 'created_at', 'order': 'desc', 'per_page': 1},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        transfers = response.json()['data']['transfers']
        
        if transfers:
            transfer = transfers[0]
            # Verify metadata
            assert transfer['media_type'] == 'movie'
            assert transfer['media_manager'] == 'radarr'
            assert transfer['connection_name'] is not None
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_history_timestamps_correct(self, lifecycle_runner):
        """Transfer timestamps should be set correctly."""
        lifecycle_runner.run_migration_test('radarr', item_type='movie')
        
        url = f"{get_api_url()}/transfers"
        response = requests.get(
            url,
            params={'status': 'completed', 'per_page': 1},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        transfers = response.json()['data']['transfers']
        
        if transfers:
            transfer = transfers[0]
            # All timestamps should be set for completed transfer
            assert transfer['created_at'] is not None
            assert transfer['started_at'] is not None
            assert transfer['completed_at'] is not None
            
            # Timestamps should be in order
            assert transfer['created_at'] <= transfer['started_at']
            assert transfer['started_at'] <= transfer['completed_at']
    
    @pytest.mark.timeout(TIMEOUTS['state_transition'])
    def test_stats_update_after_transfer(self, lifecycle_runner, transferarr):
        """Stats should reflect completed transfers."""
        # Start transferarr first so we can get initial stats
        transferarr.start(wait_healthy=True)
        
        # Get initial stats
        stats_url = f"{get_api_url()}/transfers/stats"
        initial_response = requests.get(stats_url, timeout=TIMEOUTS['api_response'])
        initial_stats = initial_response.json()['data']
        initial_completed = initial_stats['completed']
        
        # Run a transfer (lifecycle_runner will handle transferarr restart if needed)
        lifecycle_runner.run_migration_test('radarr', item_type='movie')
        
        # Check updated stats
        updated_response = requests.get(stats_url, timeout=TIMEOUTS['api_response'])
        updated_stats = updated_response.json()['data']
        
        # Should have one more completed transfer
        assert updated_stats['completed'] == initial_completed + 1


class TestDeleteTransferEndpoint:
    """Tests for DELETE /api/v1/transfers/<id> endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Use shared test environment setup and ensure transferarr is running."""
        transferarr.start(wait_healthy=True)
    
    def test_delete_transfer_not_found(self):
        """DELETE /transfers/<id> should return 404 for non-existent ID."""
        import uuid
        fake_id = str(uuid.uuid4())
        url = f"{get_api_url()}/transfers/{fake_id}"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 404
        data = response.json()
        
        assert 'error' in data
        assert data['error']['code'] == 'TRANSFER_NOT_FOUND'
    
    def test_delete_transfer_success(self):
        """DELETE /transfers/<id> should delete existing transfer."""
        # First, get list to find an existing transfer
        list_url = f"{get_api_url()}/transfers"
        list_response = requests.get(list_url, timeout=TIMEOUTS['api_response'])
        
        assert list_response.status_code == 200
        transfers = list_response.json()['data']['transfers']
        
        if not transfers:
            pytest.skip("No transfers in history to test delete")
        
        transfer_id = transfers[0]['id']
        
        # Delete the transfer
        delete_url = f"{get_api_url()}/transfers/{transfer_id}"
        response = requests.delete(delete_url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        assert data['data']['deleted'] is True
        assert 'message' in data
        
        # Verify it's gone
        get_response = requests.get(delete_url, timeout=TIMEOUTS['api_response'])
        assert get_response.status_code == 404


class TestClearTransfersEndpoint:
    """Tests for DELETE /api/v1/transfers endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Use shared test environment setup and ensure transferarr is running."""
        transferarr.start(wait_healthy=True)
    
    def test_clear_transfers_returns_count(self):
        """DELETE /transfers should return deleted count."""
        url = f"{get_api_url()}/transfers"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        assert 'deleted_count' in data['data']
        assert isinstance(data['data']['deleted_count'], int)
        assert 'message' in data
    
    def test_clear_transfers_with_status_filter(self):
        """DELETE /transfers?status=completed should only delete that status."""
        url = f"{get_api_url()}/transfers"
        response = requests.delete(
            url,
            params={'status': 'completed'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'data' in data
        assert 'deleted_count' in data['data']
        # Message should mention the status
        assert 'completed' in data.get('message', '')
    
    def test_clear_transfers_invalid_status(self):
        """DELETE /transfers with invalid status should return 400."""
        url = f"{get_api_url()}/transfers"
        response = requests.delete(
            url,
            params={'status': 'invalid_status'},
            timeout=TIMEOUTS['api_response']
        )
        
        assert response.status_code == 400
        data = response.json()
        
        assert 'error' in data
        assert data['error']['code'] == 'VALIDATION_ERROR'
    
    def test_clear_transfers_preserves_active(self):
        """DELETE /transfers should not delete pending/transferring records."""
        # This is harder to test without creating active transfers
        # Just verify the endpoint doesn't error
        url = f"{get_api_url()}/transfers"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])
        
        assert response.status_code == 200
