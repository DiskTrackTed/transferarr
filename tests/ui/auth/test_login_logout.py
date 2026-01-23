"""
UI tests for the complete login/logout workflow.

These tests verify end-to-end authentication flows including:
- Login persistence
- Logout functionality
- Session expiration
- Protected route access
"""
import pytest
from playwright.sync_api import expect


class TestLogoutFlow:
    """Test logout functionality via the UI."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_logout_link_in_sidebar(self, login_page):
        """Logout link appears in sidebar after login."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        logout_link = login_page.page.locator(".logout-link")
        expect(logout_link).to_be_visible()
    
    def test_click_logout_redirects_to_login(self, login_page):
        """Clicking logout redirects to login page."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Click logout
        login_page.page.click(".logout-link")
        
        # Wait for redirect to login page
        login_page.page.wait_for_url(lambda url: "/login" in url, timeout=5000)
        assert "/login" in login_page.page.url
    
    def test_after_logout_cannot_access_protected_pages(self, login_page, base_url):
        """After logout, protected pages redirect to login."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Logout
        login_page.page.click(".logout-link")
        login_page.page.wait_for_url(lambda url: "/login" in url, timeout=5000)
        
        # Try to access settings
        login_page.page.goto(f"{base_url}/settings")
        
        # Should redirect to login
        assert "/login" in login_page.page.url
    
    def test_logout_clears_session(self, login_page, base_url):
        """Logout clears the session completely."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Logout
        login_page.page.click(".logout-link")
        login_page.page.wait_for_url(lambda url: "/login" in url, timeout=5000)
        
        # Reload login page - should still be on login
        login_page.page.reload()
        assert "/login" in login_page.page.url


class TestLoginPersistence:
    """Test login session persistence."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_session_persists_across_page_reload(self, login_page, base_url):
        """Login session persists when page is reloaded."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Reload page
        login_page.page.reload()
        
        # Should still be logged in (not on login page)
        assert "/login" not in login_page.page.url
        
        # User info should still be visible
        user_info = login_page.page.locator(".user-info")
        expect(user_info).to_be_visible()
    
    def test_session_persists_across_navigation(self, login_page, base_url):
        """Login session persists when navigating between pages."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Navigate to torrents
        login_page.page.goto(f"{base_url}/torrents")
        assert "/login" not in login_page.page.url
        
        # Navigate to settings
        login_page.page.goto(f"{base_url}/settings")
        assert "/login" not in login_page.page.url
        
        # Navigate to history
        login_page.page.goto(f"{base_url}/history")
        assert "/login" not in login_page.page.url


class TestProtectedRouteRedirects:
    """Test protected route redirect behavior."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_dashboard_redirects_to_login(self, base_url, page):
        """Accessing dashboard without login redirects to login."""
        page.goto(f"{base_url}/")
        assert "/login" in page.url or "/setup" in page.url
    
    def test_torrents_redirects_to_login(self, base_url, page):
        """Accessing torrents without login redirects to login."""
        page.goto(f"{base_url}/torrents")
        assert "/login" in page.url
    
    def test_settings_redirects_to_login(self, base_url, page):
        """Accessing settings without login redirects to login."""
        page.goto(f"{base_url}/settings")
        assert "/login" in page.url
    
    def test_history_redirects_to_login(self, base_url, page):
        """Accessing history without login redirects to login."""
        page.goto(f"{base_url}/history")
        assert "/login" in page.url
    
    def test_redirect_preserves_original_url(self, base_url, page, login_page):
        """Redirect to login preserves original URL in 'next' parameter."""
        page.goto(f"{base_url}/settings")
        
        # Should be on login with next parameter
        assert "/login" in page.url
        assert "next=" in page.url or "settings" in page.url
    
    def test_after_login_returns_to_original_page(self, base_url, login_page):
        """After login, user returns to originally requested page."""
        # Try to access settings first
        login_page.page.goto(f"{base_url}/settings")
        
        # Should redirect to login
        assert "/login" in login_page.page.url
        
        # Login
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Should be on settings page now
        assert "/settings" in login_page.page.url


class TestSidebarUserInfo:
    """Test sidebar user info display."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_username_displayed_in_sidebar(self, login_page):
        """Logged-in username is displayed in sidebar."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        username = login_page.page.locator(".user-info .username")
        expect(username).to_have_text("testuser")
    
    def test_user_icon_visible(self, login_page):
        """User icon is visible in sidebar."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        user_icon = login_page.page.locator(".user-info .fa-user")
        expect(user_icon).to_be_visible()
    
    def test_logout_icon_visible(self, login_page):
        """Logout icon is visible in sidebar."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        logout_icon = login_page.page.locator(".logout-link .fa-sign-out-alt")
        expect(logout_icon).to_be_visible()


class TestAuthDisabledUI:
    """Test UI behavior when auth is disabled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr with auth disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        yield
    
    def test_no_user_info_when_auth_disabled(self, base_url, page):
        """User info is not shown when auth is disabled."""
        page.goto(f"{base_url}/")
        
        user_info = page.locator(".user-info")
        expect(user_info).not_to_be_visible()
    
    def test_no_logout_link_when_auth_disabled(self, base_url, page):
        """Logout link is not shown when auth is disabled."""
        page.goto(f"{base_url}/")
        
        logout_link = page.locator(".logout-link")
        expect(logout_link).not_to_be_visible()
    
    def test_can_access_all_pages_without_login(self, base_url, page):
        """All pages are accessible without login when auth is disabled."""
        # Dashboard
        page.goto(f"{base_url}/")
        assert "/login" not in page.url
        
        # Torrents
        page.goto(f"{base_url}/torrents")
        assert "/login" not in page.url
        
        # Settings
        page.goto(f"{base_url}/settings")
        assert "/login" not in page.url
        
        # History
        page.goto(f"{base_url}/history")
        assert "/login" not in page.url
    
    def test_login_page_redirects_when_auth_disabled(self, base_url, page):
        """Login page redirects to dashboard when auth is disabled."""
        page.goto(f"{base_url}/login")
        
        # Should redirect away from login
        assert "/login" not in page.url
