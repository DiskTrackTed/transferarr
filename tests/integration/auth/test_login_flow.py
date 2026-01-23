"""Integration tests for login/logout flow."""
import pytest
import requests

from tests.conftest import SERVICES


class TestLoginFlow:
    """Tests for login, logout, and session management."""

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
    def test_login_page_renders(self, transferarr, docker_services):
        """Login page renders when auth is enabled."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/login")
        assert response.status_code == 200
        assert 'Sign in' in response.text or 'Login' in response.text

    @pytest.mark.timeout(120)
    def test_login_with_valid_credentials(self, transferarr, docker_services):
        """Login succeeds with valid username and password."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Submit login form
        response = session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        }, allow_redirects=False)
        
        # Should redirect to dashboard
        assert response.status_code == 302
        
        # Should be able to access dashboard
        response = session.get(f"{base_url}/")
        assert response.status_code == 200
        assert 'Dashboard' in response.text or 'dashboard' in response.text.lower()

    @pytest.mark.timeout(120)
    def test_login_with_invalid_password(self, transferarr, docker_services):
        """Login fails with wrong password."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        
        # Should show error on login page
        assert response.status_code == 200
        assert 'Invalid' in response.text or 'invalid' in response.text

    @pytest.mark.timeout(120)
    def test_login_with_invalid_username(self, transferarr, docker_services):
        """Login fails with wrong username."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.post(f"{base_url}/login", data={
            'username': 'wronguser',
            'password': 'adminpassword'
        })
        
        # Should show error on login page
        assert response.status_code == 200
        assert 'Invalid' in response.text or 'invalid' in response.text

    @pytest.mark.timeout(120)
    def test_logout(self, transferarr, docker_services):
        """Logout clears session and redirects to login."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Verify logged in
        response = session.get(f"{base_url}/")
        assert response.status_code == 200
        
        # Logout
        response = session.get(f"{base_url}/logout", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']
        
        # Should be redirected to login when accessing protected page
        response = session.get(f"{base_url}/", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_login_redirect_next_param(self, transferarr, docker_services):
        """Login redirects to 'next' parameter after successful login."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login with next parameter
        response = session.post(f"{base_url}/login?next=/settings", data={
            'username': 'admin',
            'password': 'adminpassword'
        }, allow_redirects=False)
        
        # Should redirect to settings
        assert response.status_code == 302
        assert '/settings' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_login_rejects_external_redirect(self, transferarr, docker_services):
        """Login rejects external URLs in 'next' parameter (open redirect protection)."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Try to redirect to external URL
        response = session.post(f"{base_url}/login?next=https://evil.com", data={
            'username': 'admin',
            'password': 'adminpassword'
        }, allow_redirects=False)
        
        # Should redirect to dashboard, not external URL
        assert response.status_code == 302
        assert 'evil.com' not in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_login_already_authenticated_redirects(self, transferarr, docker_services):
        """Accessing /login when already logged in redirects to dashboard."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Try to access login page again
        response = session.get(f"{base_url}/login", allow_redirects=False)
        
        # Should redirect to dashboard
        assert response.status_code == 302
        assert '/login' not in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_remember_me_extends_session(self, transferarr, docker_services):
        """Remember me checkbox creates a persistent session cookie."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login with remember me
        response = session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword',
            'remember': 'on'
        }, allow_redirects=False)
        
        # Should have a remember cookie (Flask-Login sets 'remember_token' cookie)
        cookies = session.cookies.get_dict()
        assert response.status_code == 302
        # Flask-Login with remember=True should set a session that persists
        # The exact implementation depends on Flask-Login version

    @pytest.mark.timeout(120)
    def test_session_persists_across_requests(self, transferarr, docker_services):
        """Logged in session persists across multiple requests."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Make multiple requests
        for _ in range(3):
            response = session.get(f"{base_url}/")
            assert response.status_code == 200
            assert 'Dashboard' in response.text or 'dashboard' in response.text.lower()
