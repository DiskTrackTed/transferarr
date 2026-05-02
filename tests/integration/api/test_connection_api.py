"""
Integration tests for Connection API endpoints.

Tests /api/v1/connections endpoints for both file-transfer (SFTP/Local)
and torrent (P2P) config shapes.

These tests run against a live transferarr instance with Docker test services.
"""
import pytest
import requests
from tests.conftest import SERVICES, TIMEOUTS


def get_api_url():
    """Get the base API URL for transferarr."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


# =============================================================================
# File Transfer Connection Tests (backward compatibility)
# =============================================================================

class TestFileTransferConnectionApi:
    """Tests that file-transfer (SFTP/Local) connections still work via API."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Use shared test environment setup and ensure transferarr is running."""
        transferarr.start(wait_healthy=True)

    def test_create_file_connection_via_api(self):
        """POST connection with file config (backward compat) still works."""
        url = f"{get_api_url()}/connections"

        payload = {
            "name": "test-file-conn",
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "local"},
            },
            "source_dot_torrent_path": "/torrents",
            "source_torrent_download_path": "/downloads",
            "destination_dot_torrent_tmp_dir": "/tmp/torrents",
            "destination_torrent_download_path": "/downloads",
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

        data = response.json()
        assert data['data']['name'] == 'test-file-conn'
        assert data['data']['from'] == 'source-deluge'
        assert data['data']['to'] == 'target-deluge'
        assert data['warnings'] == []

        # Cleanup
        requests.delete(f"{url}/test-file-conn", timeout=TIMEOUTS['api_response'])

    def test_test_file_connection_backward_compat(self):
        """POST test with file config still works as before."""
        url = f"{get_api_url()}/connections/test"

        payload = {
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "local"},
            },
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert 'data' in data
        assert 'success' in data['data']


# =============================================================================
# Torrent Transfer Connection Tests
# =============================================================================

class TestTorrentConnectionApi:
    """Tests for torrent (P2P) connection CRUD via API."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with torrent-transfer config (includes tracker)."""
        transferarr.start(config_type='torrent-transfer', wait_healthy=True)

    def test_create_torrent_connection_via_api(self):
        """POST connection with torrent config succeeds, returns correct structure."""
        url = f"{get_api_url()}/connections"

        payload = {
            "name": "test-torrent-conn",
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
                "destination_path": "/downloads",
            },
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

        data = response.json()
        assert data['data']['name'] == 'test-torrent-conn'
        assert data['data']['from'] == 'source-deluge'
        assert data['data']['to'] == 'target-deluge'
        assert data['warnings'] == []

        # Cleanup
        requests.delete(f"{url}/test-torrent-conn", timeout=TIMEOUTS['api_response'])

    def test_list_connections_includes_transfer_type(self):
        """GET connections response includes transfer_type field."""
        url = f"{get_api_url()}/connections"

        # The torrent-transfer config already has a connection configured
        response = requests.get(url, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 200

        data = response.json()
        connections = data['data']
        assert len(connections) > 0

        # Find a connection (the pre-configured one from torrent-transfer config)
        conn = connections[0]
        assert 'transfer_type' in conn, f"Missing transfer_type field. Keys: {conn.keys()}"
        assert conn['transfer_type'] in ('file', 'torrent'), f"Unexpected transfer_type: {conn['transfer_type']}"

    def test_update_torrent_connection_via_api(self):
        """PUT to update torrent connection works."""
        base_url = f"{get_api_url()}/connections"

        # Create
        create_payload = {
            "name": "update-test-conn",
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
                "destination_path": "/downloads",
            },
        }
        create_resp = requests.post(base_url, json=create_payload, timeout=TIMEOUTS['api_response'])
        assert create_resp.status_code == 201

        # Update with new destination_path
        update_payload = {
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
                "destination_path": "/new-downloads",
            },
        }
        update_resp = requests.put(
            f"{base_url}/update-test-conn",
            json=update_payload,
            timeout=TIMEOUTS['api_response'],
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        assert update_resp.json()['warnings'] == []

        # Verify the update via list
        list_resp = requests.get(base_url, timeout=TIMEOUTS['api_response'])
        connections = list_resp.json()['data']
        updated = [c for c in connections if c['name'] == 'update-test-conn']
        assert len(updated) == 1
        assert updated[0]['transfer_config'].get('destination_path') == '/new-downloads'

        # Cleanup
        requests.delete(f"{base_url}/update-test-conn", timeout=TIMEOUTS['api_response'])

    def test_test_torrent_connection_checks_tracker(self):
        """POST test with torrent config verifies clients + tracker."""
        url = f"{get_api_url()}/connections/test"

        payload = {
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "torrent",
            },
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert 'data' in data
        assert data['data']['success'] is True
        # Should have details for each component
        details = data['data'].get('details', [])
        assert len(details) == 3, f"Expected 3 component details, got {len(details)}: {details}"
        for detail in details:
            assert detail['success'] is True, f"Component failed: {detail}"


class TestConnectionWarningApi:
    """Tests for non-blocking chain warnings on connection save."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with the multi-target config for 3-client topology."""
        transferarr.start(config_type='multi-target', wait_healthy=True)

    def test_create_connection_returns_warning_for_immediate_chain(self):
        url = f"{get_api_url()}/connections"
        payload = {
            "name": "chain-warning-create",
            "from": "target-deluge",
            "to": "target-deluge-2",
            "transfer_config": {
                "type": "torrent",
            },
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"

        data = response.json()
        assert data['data']['name'] == 'chain-warning-create'
        assert data['warnings'] == [
            "Connection target-deluge -> target-deluge-2 creates a chain (source-deluge -> target-deluge -> target-deluge-2). "
            "Transferarr does not support multi-hop transfers. Torrents on source-deluge will transfer to target-deluge "
            "but will NOT automatically continue to target-deluge-2."
        ]

        requests.delete(f"{url}/chain-warning-create", timeout=TIMEOUTS['api_response'])

    def test_update_connection_returns_warning_for_immediate_chain(self):
        base_url = f"{get_api_url()}/connections"

        create_payload = {
            "name": "chain-warning-update",
            "from": "source-deluge",
            "to": "target-deluge-2",
            "transfer_config": {
                "type": "torrent",
            },
        }
        create_resp = requests.post(base_url, json=create_payload, timeout=TIMEOUTS['api_response'])
        assert create_resp.status_code == 201, f"Expected 201, got {create_resp.status_code}: {create_resp.text}"
        assert create_resp.json()['warnings'] == []

        update_payload = {
            "from": "target-deluge",
            "to": "target-deluge-2",
            "transfer_config": {
                "type": "torrent",
            },
        }
        update_resp = requests.put(
            f"{base_url}/chain-warning-update",
            json=update_payload,
            timeout=TIMEOUTS['api_response'],
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        assert update_resp.json()['warnings'] == [
            "Connection target-deluge -> target-deluge-2 creates a chain (source-deluge -> target-deluge -> target-deluge-2). "
            "Transferarr does not support multi-hop transfers. Torrents on source-deluge will transfer to target-deluge "
            "but will NOT automatically continue to target-deluge-2."
        ]

        requests.delete(f"{base_url}/chain-warning-update", timeout=TIMEOUTS['api_response'])


# =============================================================================
# Validation Error Tests
# =============================================================================

class TestConnectionValidationApi:
    """Tests for connection API validation errors."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr."""
        transferarr.start(wait_healthy=True)

    def test_create_file_connection_missing_paths_returns_400(self):
        """POST file connection without path fields returns 400."""
        url = f"{get_api_url()}/connections"

        payload = {
            "name": "bad-file-conn",
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "from": {"type": "local"},
                "to": {"type": "local"},
            },
            # Missing path fields
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_create_connection_invalid_transfer_config_returns_400(self):
        """POST connection with invalid transfer_config returns 400."""
        url = f"{get_api_url()}/connections"

        payload = {
            "name": "bad-config-conn",
            "from": "source-deluge",
            "to": "target-deluge",
            "transfer_config": {
                "type": "invalid",
            },
        }

        response = requests.post(url, json=payload, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
