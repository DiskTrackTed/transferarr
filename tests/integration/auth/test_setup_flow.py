"""Integration tests for first-run setup flow."""
import pytest
import requests

from tests.conftest import SERVICES


class TestSetupFlow:
    """Tests for the first-run setup page and configuration."""

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
    def test_unconfigured_redirects_to_setup(self, transferarr, docker_services):
        """Accessing any page without auth configured redirects to /setup."""
        # Clear auth config to simulate first run
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Try to access dashboard - should redirect to setup
        response = requests.get(f"{base_url}/", allow_redirects=False)
        assert response.status_code == 302
        assert '/setup' in response.headers['Location']

    @pytest.mark.timeout(120)
    def test_setup_page_renders(self, transferarr, docker_services):
        """Setup page renders with create and skip options."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/setup")
        assert response.status_code == 200
        assert 'Create Authentication' in response.text
        assert 'Skip Authentication' in response.text

    @pytest.mark.timeout(120)
    def test_setup_create_account(self, transferarr, docker_services):
        """Creating an account on setup page configures auth and logs in."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Submit create account form
        response = session.post(f"{base_url}/setup", data={
            'action': 'create',
            'username': 'testuser',
            'password': 'testpassword123',
            'confirm_password': 'testpassword123'
        }, allow_redirects=False)
        
        # Should redirect to dashboard
        assert response.status_code == 302
        assert '/' in response.headers['Location'] or 'dashboard' in response.headers['Location'].lower()
        
        # Should be logged in - can access dashboard
        response = session.get(f"{base_url}/")
        assert response.status_code == 200
        assert 'Dashboard' in response.text or 'dashboard' in response.text.lower()

    @pytest.mark.timeout(120)
    def test_setup_skip_auth(self, transferarr, docker_services):
        """Skipping auth on setup page disables authentication."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Submit skip form
        response = requests.post(f"{base_url}/setup", data={
            'action': 'skip'
        }, allow_redirects=False)
        
        # Should redirect to dashboard
        assert response.status_code == 302
        
        # Should be able to access dashboard without login
        response = requests.get(f"{base_url}/")
        assert response.status_code == 200
        assert 'Dashboard' in response.text or 'dashboard' in response.text.lower()

    @pytest.mark.timeout(120)
    def test_setup_password_validation_min_length(self, transferarr, docker_services):
        """Setup rejects passwords shorter than 8 characters."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Submit with short password
        response = requests.post(f"{base_url}/setup", data={
            'action': 'create',
            'username': 'testuser',
            'password': 'short',
            'confirm_password': 'short'
        })
        
        # Should show error and stay on setup page
        assert response.status_code == 200
        assert 'at least 8 characters' in response.text

    @pytest.mark.timeout(120)
    def test_setup_password_validation_mismatch(self, transferarr, docker_services):
        """Setup rejects mismatched passwords."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Submit with mismatched passwords
        response = requests.post(f"{base_url}/setup", data={
            'action': 'create',
            'username': 'testuser',
            'password': 'testpassword123',
            'confirm_password': 'differentpassword'
        })
        
        # Should show error and stay on setup page
        assert response.status_code == 200
        assert 'do not match' in response.text

    @pytest.mark.timeout(120)
    def test_setup_username_required(self, transferarr, docker_services):
        """Setup rejects empty username."""
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Submit with empty username
        response = requests.post(f"{base_url}/setup", data={
            'action': 'create',
            'username': '',
            'password': 'testpassword123',
            'confirm_password': 'testpassword123'
        })
        
        # Should show error and stay on setup page
        assert response.status_code == 200
        assert 'required' in response.text.lower()

    @pytest.mark.timeout(120)
    def test_setup_already_configured_redirects(self, transferarr, docker_services):
        """Accessing /setup when already configured redirects to dashboard."""
        # Configure auth first
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Try to access setup
        response = requests.get(f"{base_url}/setup", allow_redirects=False)
        
        # Should redirect away from setup
        assert response.status_code == 302
        assert '/setup' not in response.headers['Location']

    @pytest.mark.timeout(180)
    def test_auth_persists_after_restart(self, transferarr, docker_services):
        """Auth settings created via setup persist after container restart."""
        # Start with no auth configured
        transferarr.clear_auth_config()
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Create account via setup
        response = session.post(f"{base_url}/setup", data={
            'action': 'create',
            'username': 'testadmin',
            'password': 'testpass123',
            'confirm_password': 'testpass123'
        }, allow_redirects=False)
        assert response.status_code == 302
        
        # Restart the container
        transferarr.restart()
        
        # New session (simulates fresh browser)
        new_session = requests.Session()
        
        # Try to access dashboard - should redirect to login (auth is enabled)
        response = new_session.get(f"{base_url}/", allow_redirects=False)
        assert response.status_code == 302
        assert '/login' in response.headers['Location']
        
        # Login with the credentials we created
        response = new_session.post(f"{base_url}/login", data={
            'username': 'testadmin',
            'password': 'testpass123'
        }, allow_redirects=False)
        assert response.status_code == 302  # Successful login redirects
        
        # Now we should be able to access dashboard
        response = new_session.get(f"{base_url}/")
        assert response.status_code == 200
        assert 'Dashboard' in response.text or 'dashboard' in response.text.lower()
