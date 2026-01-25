"""Integration tests for auth settings API endpoints."""
import pytest
import requests

from tests.conftest import SERVICES


class TestGetAuthSettings:
    """Tests for GET /api/v1/auth/settings endpoint."""

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
    def test_get_settings_when_auth_disabled(self, transferarr, docker_services):
        """GET /api/v1/auth/settings works when auth is disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/auth/settings")
        assert response.status_code == 200
        
        data = response.json()
        assert 'data' in data
        assert 'enabled' in data['data']
        assert 'username' in data['data']
        assert 'session_timeout_minutes' in data['data']
        assert 'runtime_session_timeout_minutes' in data['data']
        # Should NOT include password_hash
        assert 'password_hash' not in data['data']

    @pytest.mark.timeout(120)
    def test_get_settings_when_auth_enabled_not_logged_in(self, transferarr, docker_services):
        """GET /api/v1/auth/settings returns 401 when not logged in."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(f"{base_url}/api/v1/auth/settings")
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_get_settings_when_logged_in(self, transferarr, docker_services):
        """GET /api/v1/auth/settings works when logged in."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        response = session.get(f"{base_url}/api/v1/auth/settings")
        assert response.status_code == 200
        
        data = response.json()
        assert 'data' in data
        assert data['data']['enabled'] is True
        assert data['data']['username'] == 'admin'


class TestUpdateAuthSettings:
    """Tests for PUT /api/v1/auth/settings endpoint."""

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
    def test_update_session_timeout(self, transferarr, docker_services):
        """PUT /api/v1/auth/settings can update session timeout."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Update session timeout
        response = session.put(
            f"{base_url}/api/v1/auth/settings",
            json={'session_timeout_minutes': 120}
        )
        assert response.status_code == 200
        
        # Verify the change
        response = session.get(f"{base_url}/api/v1/auth/settings")
        data = response.json()
        assert data['data']['session_timeout_minutes'] == 120

    @pytest.mark.timeout(120)
    def test_runtime_timeout_differs_after_update(self, transferarr, docker_services):
        """Runtime timeout stays at startup value after config update (needs restart)."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Get initial values - they should match
        response = session.get(f"{base_url}/api/v1/auth/settings")
        data = response.json()
        initial_timeout = data['data']['session_timeout_minutes']
        initial_runtime = data['data']['runtime_session_timeout_minutes']
        assert initial_timeout == initial_runtime
        
        # Update session timeout to a different value
        new_timeout = 480 if initial_timeout != 480 else 120
        response = session.put(
            f"{base_url}/api/v1/auth/settings",
            json={'session_timeout_minutes': new_timeout}
        )
        assert response.status_code == 200
        
        # Verify config changed but runtime stayed the same
        response = session.get(f"{base_url}/api/v1/auth/settings")
        data = response.json()
        assert data['data']['session_timeout_minutes'] == new_timeout
        assert data['data']['runtime_session_timeout_minutes'] == initial_runtime
        # They should now differ (indicating restart needed)
        assert data['data']['session_timeout_minutes'] != data['data']['runtime_session_timeout_minutes']

    @pytest.mark.timeout(120)
    def test_update_auth_enabled(self, transferarr, docker_services):
        """PUT /api/v1/auth/settings can disable auth."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Disable auth
        response = session.put(
            f"{base_url}/api/v1/auth/settings",
            json={'enabled': False}
        )
        assert response.status_code == 200
        
        # Verify the change (should work without login now)
        response = requests.get(f"{base_url}/api/v1/auth/settings")
        assert response.status_code == 200
        data = response.json()
        assert data['data']['enabled'] is False

    @pytest.mark.timeout(120)
    def test_update_settings_rejects_invalid_timeout(self, transferarr, docker_services):
        """PUT /api/v1/auth/settings rejects negative timeout."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Try invalid timeout
        response = session.put(
            f"{base_url}/api/v1/auth/settings",
            json={'session_timeout_minutes': -1}
        )
        assert response.status_code == 400

    @pytest.mark.timeout(120)
    def test_update_settings_when_not_logged_in(self, transferarr, docker_services):
        """PUT /api/v1/auth/settings returns 401 when not logged in."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.put(
            f"{base_url}/api/v1/auth/settings",
            json={'session_timeout_minutes': 120}
        )
        assert response.status_code == 401


class TestChangePassword:
    """Tests for PUT /api/v1/auth/password endpoint."""

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
    def test_change_password_success(self, transferarr, docker_services):
        """PUT /api/v1/auth/password changes password successfully."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Change password
        response = session.put(
            f"{base_url}/api/v1/auth/password",
            json={
                'current_password': 'adminpassword',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            }
        )
        assert response.status_code == 200
        
        # Logout
        session.get(f"{base_url}/logout")
        
        # Login with new password should work
        response = session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'newpassword123'
        }, allow_redirects=False)
        assert response.status_code == 302  # Redirect = success

    @pytest.mark.timeout(120)
    def test_change_password_wrong_current(self, transferarr, docker_services):
        """PUT /api/v1/auth/password fails with wrong current password."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Try to change with wrong current password
        response = session.put(
            f"{base_url}/api/v1/auth/password",
            json={
                'current_password': 'wrongpassword',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert 'INVALID_PASSWORD' in str(data) or 'incorrect' in str(data).lower()

    @pytest.mark.timeout(120)
    def test_change_password_mismatch(self, transferarr, docker_services):
        """PUT /api/v1/auth/password fails when passwords don't match."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Try to change with mismatched passwords
        response = session.put(
            f"{base_url}/api/v1/auth/password",
            json={
                'current_password': 'adminpassword',
                'new_password': 'newpassword123',
                'confirm_password': 'differentpassword'
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert 'mismatch' in str(data).lower() or 'match' in str(data).lower()

    @pytest.mark.timeout(120)
    def test_change_password_too_short(self, transferarr, docker_services):
        """PUT /api/v1/auth/password fails with password < 8 chars."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        session.post(f"{base_url}/login", data={
            'username': 'admin',
            'password': 'adminpassword'
        })
        
        # Try to change with short password
        response = session.put(
            f"{base_url}/api/v1/auth/password",
            json={
                'current_password': 'adminpassword',
                'new_password': 'short',
                'confirm_password': 'short'
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert '8' in str(data) or 'WEAK_PASSWORD' in str(data)

    @pytest.mark.timeout(120)
    def test_change_password_requires_login(self, transferarr, docker_services):
        """PUT /api/v1/auth/password returns 401 when not logged in."""
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.put(
            f"{base_url}/api/v1/auth/password",
            json={
                'current_password': 'adminpassword',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123'
            }
        )
        assert response.status_code == 401
