"""Integration tests for route protection with authentication."""
import pytest
import requests

from tests.conftest import SERVICES


class TestProtectedRoutes:
    """Tests for protected UI and API routes."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    def _get_transferarr_url(self):
        """Get the transferarr base URL."""
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        return f"http://{host}:{port}"

    # ============== UI Routes ==============

    @pytest.mark.timeout(120)
    def test_dashboard_requires_auth(self, transferarr, docker_services):
        """Dashboard redirects to login when not authenticated."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_torrents_requires_auth(self, transferarr, docker_services):
        """Torrents page redirects to login when not authenticated."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/torrents", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_settings_requires_auth(self, transferarr, docker_services):
        """Settings page redirects to login when not authenticated."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/settings", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_history_requires_auth(self, transferarr, docker_services):
        """History page redirects to login when not authenticated."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/history", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_ui_routes_accessible_when_authenticated(self, transferarr, docker_services):
        """All UI routes are accessible when logged in."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Test each UI route
        routes = ['/', '/torrents', '/settings', '/history']
        for route in routes:
            response = session.get(f"{base_url}{route}")
            assert response.status_code == 200, f"Route {route} should be accessible"

    # ============== API Routes ==============

    @pytest.mark.timeout(120)
    def test_health_endpoint_always_accessible(self, transferarr, docker_services):
        """Health endpoint is always accessible, even without auth."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/health")
        assert response.status_code == 200
        assert 'status' in response.json().get('data', {})

    @pytest.mark.timeout(120)
    def test_api_config_requires_auth(self, transferarr, docker_services):
        """Config API endpoint requires authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/config")
        assert response.status_code == 401
        assert 'UNAUTHORIZED' in response.text or 'Authentication required' in response.text

    @pytest.mark.timeout(120)
    def test_api_torrents_requires_auth(self, transferarr, docker_services):
        """Torrents API endpoint requires authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/torrents")
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_api_download_clients_requires_auth(self, transferarr, docker_services):
        """Download clients API endpoint requires authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/download_clients")
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_api_connections_requires_auth(self, transferarr, docker_services):
        """Connections API endpoint requires authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/connections")
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_api_transfers_requires_auth(self, transferarr, docker_services):
        """Transfers API endpoint requires authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/transfers")
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_api_routes_accessible_when_authenticated(self, transferarr, docker_services):
        """API routes are accessible when logged in via session."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Test API routes
        api_routes = [
            '/api/v1/config',
            '/api/v1/torrents',
            '/api/v1/download_clients',
            '/api/v1/connections',
            '/api/v1/transfers'
        ]
        for route in api_routes:
            response = session.get(f"{base_url}{route}")
            assert response.status_code == 200, f"Route {route} should be accessible when authenticated"

    # ============== Login page public access ==============

    @pytest.mark.timeout(120)
    def test_login_page_accessible_without_auth(self, transferarr, docker_services):
        """Login page is accessible without authentication."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/login")
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_setup_page_accessible_without_auth(self, transferarr, docker_services):
        """Setup page is accessible without authentication (when unconfigured)."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/setup")
        assert response.status_code == 200
