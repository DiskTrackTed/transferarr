"""Integration tests for API key authentication."""
import pytest
import requests

from tests.conftest import SERVICES, TIMEOUTS


class TestApiKeyAuthentication:
    """Tests for API key authentication on API routes."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    def _get_transferarr_url(self):
        """Get the transferarr base URL."""
        host = SERVICES['transferarr']['host']
        port = SERVICES['transferarr']['port']
        return f"http://{host}:{port}"

    # ============== API Key Required Tests ==============

    @pytest.mark.timeout(120)
    def test_api_blocked_without_key_when_required(self, transferarr, docker_services):
        """API returns 401 when API key is required but not provided."""
        # Configure API key as required
        transferarr.set_auth_config(enabled=False)  # Disable user auth
        transferarr.set_api_config(key="tr_testkey123456789012345678901234", key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Health should always be accessible
        response = requests.get(f"{base_url}/api/v1/health")
        assert response.status_code == 200
        
        # Other API routes should require API key
        response = requests.get(f"{base_url}/api/v1/torrents")
        assert response.status_code == 401
        data = response.json()
        assert data.get('error', {}).get('code') == 'UNAUTHORIZED'
        assert 'API key' in data.get('error', {}).get('message', '')

    @pytest.mark.timeout(120)
    def test_api_accessible_with_valid_header_key(self, transferarr, docker_services):
        """API is accessible with valid API key in X-API-Key header."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Request with valid API key header
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_api_accessible_with_valid_query_param_key(self, transferarr, docker_services):
        """API is accessible with valid API key as query parameter."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Request with valid API key as query param
        response = requests.get(f"{base_url}/api/v1/torrents?apikey={api_key}")
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_api_blocked_with_invalid_key(self, transferarr, docker_services):
        """API returns 401 with invalid API key."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Request with wrong API key
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": "tr_wrongkey12345678901234567890123"}
        )
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_header_takes_precedence_over_query_param(self, transferarr, docker_services):
        """X-API-Key header takes precedence over query parameter."""
        api_key = "tr_testkey123456789012345678901234"
        wrong_key = "tr_wrongkey12345678901234567890123"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Valid header, wrong query param - should succeed (header takes precedence)
        response = requests.get(
            f"{base_url}/api/v1/torrents?apikey={wrong_key}",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        
        # Wrong header, valid query param - should fail (header takes precedence)
        response = requests.get(
            f"{base_url}/api/v1/torrents?apikey={api_key}",
            headers={"X-API-Key": wrong_key}
        )
        assert response.status_code == 401

    # ============== API Key Not Required Tests ==============

    @pytest.mark.timeout(120)
    def test_api_accessible_without_key_when_not_required(self, transferarr, docker_services):
        """API is accessible without key when key_required is False."""
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key="tr_testkey123456789012345678901234", key_required=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # API should be accessible without key
        response = requests.get(f"{base_url}/api/v1/torrents")
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_api_key_still_works_when_not_required(self, transferarr, docker_services):
        """API key still works when key_required is False (for convenience)."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # API should be accessible with valid key even though not required
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200

    # ============== Integration with User Auth ==============

    @pytest.mark.timeout(120)
    def test_session_auth_bypasses_api_key(self, transferarr, docker_services):
        """Authenticated session bypasses API key requirement."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        session = requests.Session()
        
        # Login first
        response = session.post(
            f"{base_url}/login",
            data={'username': 'admin', 'password': 'adminpassword'},
            allow_redirects=False
        )
        assert response.status_code == 302  # Redirect on success
        
        # API should be accessible without API key due to session
        response = session.get(f"{base_url}/api/v1/torrents")
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_api_key_works_without_session_when_user_auth_enabled(self, transferarr, docker_services):
        """API key works when user auth is enabled but no session."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # No session, but API key should work
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_no_key_no_session_returns_401(self, transferarr, docker_services):
        """Request without key or session returns 401 when both are configured."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # No session, no API key - should fail
        response = requests.get(f"{base_url}/api/v1/torrents")
        assert response.status_code == 401

    # ============== Health Endpoint Tests ==============

    @pytest.mark.timeout(120)
    def test_health_always_accessible(self, transferarr, docker_services):
        """Health endpoint is always accessible regardless of auth config."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Health should be accessible without any auth
        response = requests.get(f"{base_url}/api/v1/health")
        assert response.status_code == 200


class TestApiKeyManagementEndpoints:
    """Tests for API key management endpoints."""

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
    def test_get_api_key_settings(self, transferarr, docker_services):
        """Can retrieve API key settings."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        response = requests.get(
            f"{base_url}/api/v1/auth/api-key",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['data']['key'] == api_key
        assert data['data']['key_required'] is True

    @pytest.mark.timeout(120)
    def test_update_api_key_settings(self, transferarr, docker_services):
        """Can update API key settings."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Disable key requirement
        response = requests.put(
            f"{base_url}/api/v1/auth/api-key",
            headers={"X-API-Key": api_key},
            json={'key_required': False}
        )
        assert response.status_code == 200
        
        # Verify change (no key needed now since key_required=False)
        response = requests.get(f"{base_url}/api/v1/auth/api-key")
        assert response.json()['data']['key_required'] is False

    @pytest.mark.timeout(120)
    def test_generate_api_key(self, transferarr, docker_services):
        """Can generate a new API key."""
        transferarr.set_auth_config(enabled=False)
        transferarr.clear_api_config()  # No API key initially
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Generate new key
        response = requests.post(f"{base_url}/api/v1/auth/api-key/generate")
        assert response.status_code == 200
        
        data = response.json()
        new_key = data['data']['key']
        assert new_key is not None
        assert new_key.startswith('tr_')
        
        # Key should now be usable
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": new_key}
        )
        # Note: key_required defaults to True, but without a key set initially
        # the default behavior allows access. After generating, we just verify the key works.
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_regenerate_api_key(self, transferarr, docker_services):
        """Regenerating key invalidates old key."""
        old_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=old_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Generate new key
        response = requests.post(
            f"{base_url}/api/v1/auth/api-key/generate",
            headers={"X-API-Key": old_key}  # Auth with old key
        )
        assert response.status_code == 200
        
        new_key = response.json()['data']['key']
        assert new_key != old_key
        
        # Old key should no longer work
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": old_key}
        )
        assert response.status_code == 401
        
        # New key should work
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": new_key}
        )
        assert response.status_code == 200

    @pytest.mark.timeout(120)
    def test_revoke_api_key(self, transferarr, docker_services):
        """Revoking key removes it and disables key_required."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Revoke the key
        response = requests.post(
            f"{base_url}/api/v1/auth/api-key/revoke",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        
        # Key should no longer exist and key_required should be False
        response = requests.get(f"{base_url}/api/v1/auth/api-key")
        assert response.json()['data']['key'] is None
        assert response.json()['data']['key_required'] is False

    @pytest.mark.timeout(120)
    def test_revoke_api_key_when_none_exists(self, transferarr, docker_services):
        """Revoking when no key exists returns 404."""
        transferarr.set_auth_config(enabled=False)
        transferarr.clear_api_config()  # No API key
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Revoke when no key exists - should return 404
        response = requests.post(f"{base_url}/api/v1/auth/api-key/revoke")
        assert response.status_code == 404
        data = response.json()
        assert 'no api key' in data.get('error', {}).get('message', '').lower()

    @pytest.mark.timeout(120)
    def test_api_key_case_sensitive(self, transferarr, docker_services):
        """API key comparison is case-sensitive."""
        api_key = "tr_TestKey123456789012345678901234"  # Mixed case
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Exact match should work
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
        
        # Lowercase version should fail
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key.lower()}
        )
        assert response.status_code == 401
        
        # Uppercase version should fail
        response = requests.get(
            f"{base_url}/api/v1/torrents",
            headers={"X-API-Key": api_key.upper()}
        )
        assert response.status_code == 401

    @pytest.mark.timeout(120)
    def test_api_key_endpoints_require_auth_when_enabled(self, transferarr, docker_services):
        """API key management endpoints require auth when user auth is enabled."""
        api_key = "tr_testkey123456789012345678901234"
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Without auth, should get 401
        response = requests.get(f"{base_url}/api/v1/auth/api-key")
        assert response.status_code == 401
        
        # With API key, should work
        response = requests.get(
            f"{base_url}/api/v1/auth/api-key",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200


class TestApiKeyConfigurationConstraints:
    """Tests for API key configuration constraints."""

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
    def test_cannot_enable_key_required_without_user_auth(self, transferarr, docker_services):
        """Cannot enable API key requirement when user auth is disabled."""
        api_key = "tr_testkey123456789012345678901234"
        # Start with user auth disabled and key_required=False
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key=api_key, key_required=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Try to enable key_required - should fail
        response = requests.put(
            f"{base_url}/api/v1/auth/api-key",
            json={"key_required": True}
        )
        assert response.status_code == 400
        data = response.json()
        assert 'user authentication' in data.get('error', {}).get('message', '').lower()

    @pytest.mark.timeout(120)
    def test_disabling_user_auth_disables_key_required(self, transferarr, docker_services):
        """Disabling user auth also disables API key requirement."""
        api_key = "tr_testkey123456789012345678901234"
        # Start with both enabled
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=True)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # First login to get a session
        session = requests.Session()
        response = session.post(
            f"{base_url}/login",
            data={"username": "admin", "password": "adminpassword"}
        )
        assert response.status_code == 200
        
        # Verify key_required is True
        response = session.get(f"{base_url}/api/v1/auth/api-key")
        assert response.status_code == 200
        assert response.json()['data']['key_required'] is True
        
        # Disable user auth
        response = session.put(
            f"{base_url}/api/v1/auth/settings",
            json={"enabled": False}
        )
        assert response.status_code == 200
        
        # key_required should now be False
        response = requests.get(f"{base_url}/api/v1/auth/api-key")
        assert response.status_code == 200
        assert response.json()['data']['key_required'] is False

    @pytest.mark.timeout(120)
    def test_can_enable_key_required_with_user_auth(self, transferarr, docker_services):
        """Can enable API key requirement when user auth is enabled."""
        api_key = "tr_testkey123456789012345678901234"
        # Start with user auth enabled and key_required=False
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.set_api_config(key=api_key, key_required=False)
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Login to get a session
        session = requests.Session()
        response = session.post(
            f"{base_url}/login",
            data={"username": "admin", "password": "adminpassword"}
        )
        assert response.status_code == 200
        
        # Enable key_required - should succeed
        response = session.put(
            f"{base_url}/api/v1/auth/api-key",
            json={"key_required": True}
        )
        assert response.status_code == 200
        
        # Verify it was saved
        response = session.get(f"{base_url}/api/v1/auth/api-key")
        assert response.status_code == 200
        assert response.json()['data']['key_required'] is True

    @pytest.mark.timeout(120)
    def test_cannot_enable_key_required_without_key(self, transferarr, docker_services):
        """Cannot enable API key requirement when no key has been generated."""
        # Start with user auth enabled but no API key
        transferarr.set_auth_config(enabled=True, username='admin', password='adminpassword')
        transferarr.clear_api_config()  # No key
        transferarr.start(wait_healthy=True)
        
        base_url = self._get_transferarr_url()
        
        # Login to get a session
        session = requests.Session()
        response = session.post(
            f"{base_url}/login",
            data={"username": "admin", "password": "adminpassword"}
        )
        assert response.status_code == 200
        
        # Try to enable key_required - should fail
        response = session.put(
            f"{base_url}/api/v1/auth/api-key",
            json={"key_required": True}
        )
        assert response.status_code == 400
        data = response.json()
        assert 'no key' in data.get('error', {}).get('message', '').lower()
