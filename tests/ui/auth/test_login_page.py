"""
UI tests for the login page elements and interactions.

These tests verify the login page UI components and behavior.
"""
import pytest
from playwright.sync_api import expect


class TestLoginPageElements:
    """Test login page UI elements are present and styled correctly."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr for login page tests."""
        # Enable auth with test credentials
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_login_page_loads(self, login_page):
        """Login page loads with correct title."""
        login_page.goto()
        expect(login_page.page).to_have_title("Transferarr - Login")
    
    def test_login_container_visible(self, login_page):
        """Login container is visible."""
        login_page.goto()
        expect(login_page.page.locator(login_page.LOGIN_CONTAINER)).to_be_visible()
    
    def test_login_card_visible(self, login_page):
        """Login card is visible."""
        login_page.goto()
        expect(login_page.page.locator(login_page.LOGIN_CARD)).to_be_visible()
    
    def test_logo_displays_transferarr(self, login_page):
        """Logo displays 'Transferarr'."""
        login_page.goto()
        assert "Transferarr" in login_page.get_logo_text()
    
    def test_subtitle_displays_sign_in(self, login_page):
        """Subtitle shows sign in message."""
        login_page.goto()
        subtitle = login_page.get_subtitle_text()
        assert "sign in" in subtitle.lower() or "Sign in" in subtitle
    
    def test_username_field_visible(self, login_page):
        """Username input field is visible."""
        login_page.goto()
        assert login_page.is_username_field_visible()
    
    def test_password_field_visible(self, login_page):
        """Password input field is visible."""
        login_page.goto()
        assert login_page.is_password_field_visible()
    
    def test_remember_checkbox_visible(self, login_page):
        """Remember me checkbox is visible."""
        login_page.goto()
        assert login_page.is_remember_checkbox_visible()
    
    def test_submit_button_visible(self, login_page):
        """Sign in button is visible."""
        login_page.goto()
        assert login_page.is_submit_button_visible()
    
    def test_version_displayed_in_footer(self, login_page):
        """Version number is displayed in footer."""
        login_page.goto()
        version = login_page.get_version_text()
        assert version.startswith("v")


class TestLoginPageInteractions:
    """Test login page form interactions."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr for login tests."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_can_type_in_username_field(self, login_page):
        """Can type in username field."""
        login_page.goto()
        login_page.fill_username("myuser")
        expect(login_page.page.locator(login_page.USERNAME_INPUT)).to_have_value("myuser")
    
    def test_can_type_in_password_field(self, login_page):
        """Can type in password field."""
        login_page.goto()
        login_page.fill_password("mypassword")
        expect(login_page.page.locator(login_page.PASSWORD_INPUT)).to_have_value("mypassword")
    
    def test_can_check_remember_me(self, login_page):
        """Can check remember me checkbox."""
        login_page.goto()
        login_page.check_remember_me()
        expect(login_page.page.locator(login_page.REMEMBER_CHECKBOX)).to_be_checked()
    
    def test_can_uncheck_remember_me(self, login_page):
        """Can uncheck remember me checkbox."""
        login_page.goto()
        login_page.check_remember_me()
        login_page.uncheck_remember_me()
        expect(login_page.page.locator(login_page.REMEMBER_CHECKBOX)).not_to_be_checked()


class TestLoginFormValidation:
    """Test login form validation and error messages."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr for validation tests."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_invalid_credentials_shows_error(self, login_page):
        """Invalid credentials show error message."""
        login_page.goto()
        login_page.login("wronguser", "wrongpass")
        
        # Wait for page to reload with error
        login_page.page.wait_for_load_state("networkidle")
        
        error = login_page.get_error_message()
        assert "invalid" in error.lower() or "incorrect" in error.lower()
    
    def test_empty_username_shows_error(self, login_page):
        """Empty username shows error."""
        login_page.goto()
        login_page.fill_password("somepass")
        login_page.click_submit()
        
        # Wait for page to reload with error
        login_page.page.wait_for_load_state("networkidle")
        
        error = login_page.get_error_message()
        # Either form validation prevents submission or server returns error
        assert error or login_page.page.url.endswith("/login")
    
    def test_empty_password_shows_error(self, login_page):
        """Empty password shows error."""
        login_page.goto()
        login_page.fill_username("someuser")
        login_page.click_submit()
        
        # Wait for page to reload with error
        login_page.page.wait_for_load_state("networkidle")
        
        error = login_page.get_error_message()
        # Either form validation prevents submission or server returns error
        assert error or login_page.page.url.endswith("/login")


class TestSuccessfulLogin:
    """Test successful login flow."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up auth-enabled transferarr for login tests."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_successful_login_redirects_to_dashboard(self, login_page):
        """Successful login redirects to dashboard."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        
        login_page.wait_for_redirect()
        # Should not be on login page anymore
        assert "/login" not in login_page.page.url
    
    def test_login_preserves_next_parameter(self, login_page, base_url):
        """Login redirects to 'next' URL after success."""
        login_page.page.goto(f"{base_url}/login?next=/settings")
        login_page.login("testuser", "testpass123")
        
        login_page.wait_for_redirect()
        assert "/settings" in login_page.page.url
    
    def test_logged_in_user_sees_sidebar(self, login_page):
        """After login, sidebar shows user info."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        
        login_page.wait_for_redirect()
        
        # Should see username in sidebar
        user_info = login_page.page.locator(".user-info")
        expect(user_info).to_be_visible()
    
    def test_logged_in_user_sees_logout_link(self, login_page):
        """After login, logout link is visible."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        
        login_page.wait_for_redirect()
        
        logout_link = login_page.page.locator(".logout-link")
        expect(logout_link).to_be_visible()
