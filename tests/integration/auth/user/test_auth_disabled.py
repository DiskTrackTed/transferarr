"""Integration tests for auth disabled behavior."""
import pytest
import requests

from tests.conftest import SERVICES


class TestAuthDisabled:
    """Tests for behavior when authentication is explicitly disabled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    def _get_transferarr_url(self):
        """Get the transferarr base URL."""
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        return f"http://{host}:{port}"

    @pytest.mark.timeout(120)
    def test_ui_routes_accessible_when_auth_disabled(self, transferarr, docker_services):
        """All UI routes are accessible when auth is disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Test each UI route without any authentication
        routes = ['/', '/torrents', '/settings', '/history']
        for route in routes:
            response = requests.get(f"{base_url}{route}")
            assert response.status_code == 200, f"Route {route} should be accessible when auth disabled"

    @pytest.mark.timeout(120)
    def test_api_routes_accessible_when_auth_disabled(self, transferarr, docker_services):
        """All API routes are accessible when auth is disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Test API routes without authentication
        api_routes = [
            '/api/v1/health',
            '/api/v1/config',
            '/api/v1/torrents',
            '/api/v1/download_clients',
            '/api/v1/connections',
            '/api/v1/transfers'
        ]
        for route in api_routes:
            response = requests.get(f"{base_url}{route}")
            assert response.status_code == 200, f"Route {route} should be accessible when auth disabled"

    @pytest.mark.timeout(120)
    def test_login_page_redirects_when_auth_disabled(self, transferarr, docker_services):
        """Login page redirects to dashboard when auth is disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/login", allow_redirects=False)
        assert response.status_code == 302
        # Should redirect to dashboard (root or explicit dashboard path)
        location = response.headers['Location']
        assert '/login' not in location

    @pytest.mark.timeout(120)
    def test_setup_page_redirects_when_auth_configured_disabled(self, transferarr, docker_services):
        """Setup page redirects to dashboard when auth is configured (even if disabled)."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/setup", allow_redirects=False)
        assert response.status_code == 302
        # Should redirect away from setup
        assert '/setup' not in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_no_login_required_message_when_auth_disabled(self, transferarr, docker_services):
        """Dashboard loads directly without login message when auth disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/")
        assert response.status_code == 200
        # Should not show login message
        assert 'Please log in' not in response.text
        assert 'Sign in' not in response.text

    @pytest.mark.timeout(120)
    def test_write_operations_allowed_when_auth_disabled(self, transferarr, docker_services):
        """Write operations (POST/PUT/DELETE) are allowed when auth disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Test that we can make POST requests (not that we're creating real data)
        # We test by trying to add a client - if it returns 4xx it's a validation error
        # not an auth error
        response = requests.post(f"{base_url}/api/v1/download_clients", json={
            'name': 'test-client',
            'type': 'deluge',
            'connection_type': 'rpc',
            'host': 'nonexistent-host',
            'port': 58846,
            'password': 'test'
        })
        
        # Should not be 401 Unauthorized
        assert response.status_code != 401

    @pytest.mark.timeout(120)
    def test_swagger_docs_accessible_when_auth_disabled(self, transferarr, docker_services):
        """Swagger/OpenAPI docs are accessible when auth disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/apidocs/")
        assert response.status_code == 200
