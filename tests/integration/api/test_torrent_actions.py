"""Integration tests for torrent action endpoints (retry, remove)."""
import pytest
import requests
from tests.conftest import SERVICES, TIMEOUTS


def get_api_url():
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


class TestRetryTransfer:
    """Tests for POST /api/v1/torrents/<hash>/retry endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        transferarr.start(wait_healthy=True)

    def test_retry_not_found_returns_404(self):
        """Retrying nonexistent hash returns 404."""
        url = f"{get_api_url()}/torrents/nonexistent123/retry"
        response = requests.post(url, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 404
        data = response.json()
        assert data['error']['code'] == 'NOT_FOUND'
        assert 'not found' in data['error']['message'].lower()


class TestRemoveTransfer:
    """Tests for DELETE /api/v1/torrents/<hash> endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        transferarr.start(wait_healthy=True)

    def test_remove_not_found_returns_404(self):
        """Removing nonexistent hash returns 404."""
        url = f"{get_api_url()}/torrents/nonexistent123"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 404
        data = response.json()
        assert data['error']['code'] == 'NOT_FOUND'
        assert 'not found' in data['error']['message'].lower()
