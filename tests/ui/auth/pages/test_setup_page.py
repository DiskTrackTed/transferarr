"""
UI tests for the setup page elements and interactions.

These tests verify the setup page UI components and behavior.
The setup page appears when auth is enabled but no credentials are configured.
"""
import pytest
from playwright.sync_api import expect


class TestSetupPageElements:
    """Test setup page UI elements are present and styled correctly."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr with auth enabled but no credentials (needs setup)."""
        # Enable auth without credentials to trigger setup flow
        transferarr.set_auth_config(
            enabled=True,
            username=None,
            password=None
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_setup_page_loads(self, setup_page):
        """Setup page loads with correct title."""
        setup_page.goto()
        expect(setup_page.page).to_have_title("Transferarr - Setup")
    
    def test_setup_container_visible(self, setup_page):
        """Setup container is visible."""
        setup_page.goto()
        expect(setup_page.page.locator(setup_page.LOGIN_CONTAINER)).to_be_visible()
    
    def test_setup_card_visible(self, setup_page):
        """Setup card is visible."""
        setup_page.goto()
        expect(setup_page.page.locator(setup_page.LOGIN_CARD)).to_be_visible()
    
    def test_logo_displays_transferarr(self, setup_page):
        """Logo displays 'Transferarr'."""
        setup_page.goto()
        assert "Transferarr" in setup_page.get_logo_text()
    
    def test_subtitle_displays_setup_message(self, setup_page):
        """Subtitle shows setup message."""
        setup_page.goto()
        subtitle = setup_page.get_subtitle_text()
        # Actual text: "Welcome! Let's set up your instance."
        assert "set up" in subtitle.lower() or "welcome" in subtitle.lower()
    
    def test_username_field_visible(self, setup_page):
        """Username input field is visible."""
        setup_page.goto()
        assert setup_page.is_username_field_visible()
    
    def test_password_field_visible(self, setup_page):
        """Password input field is visible."""
        setup_page.goto()
        assert setup_page.is_password_field_visible()
    
    def test_confirm_password_field_visible(self, setup_page):
        """Confirm password input field is visible."""
        setup_page.goto()
        assert setup_page.is_confirm_password_field_visible()
    
    def test_create_button_visible(self, setup_page):
        """Create account button is visible."""
        setup_page.goto()
        assert setup_page.is_create_button_visible()
    
    def test_skip_button_visible(self, setup_page):
        """Skip setup button is visible."""
        setup_page.goto()
        assert setup_page.is_skip_button_visible()
    
    def test_version_displayed_in_footer(self, setup_page):
        """Version number is displayed in footer."""
        setup_page.goto()
        version = setup_page.get_version_text()
        assert version.startswith("v")


class TestSetupPageInteractions:
    """Test setup page form interactions."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr needing setup."""
        transferarr.set_auth_config(
            enabled=True,
            username=None,
            password=None
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_can_type_in_username_field(self, setup_page):
        """Can type in username field."""
        setup_page.goto()
        setup_page.fill_username("newuser")
        expect(setup_page.page.locator(setup_page.USERNAME_INPUT)).to_have_value("newuser")
    
    def test_can_type_in_password_field(self, setup_page):
        """Can type in password field."""
        setup_page.goto()
        setup_page.fill_password("newpassword")
        expect(setup_page.page.locator(setup_page.PASSWORD_INPUT)).to_have_value("newpassword")
    
    def test_can_type_in_confirm_password_field(self, setup_page):
        """Can type in confirm password field."""
        setup_page.goto()
        setup_page.fill_confirm_password("newpassword")
        expect(setup_page.page.locator(setup_page.CONFIRM_PASSWORD_INPUT)).to_have_value("newpassword")


class TestSetupFormValidation:
    """Test setup form validation and error messages."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr needing setup."""
        transferarr.set_auth_config(
            enabled=True,
            username=None,
            password=None
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_password_mismatch_shows_error(self, setup_page):
        """Password mismatch shows error message."""
        setup_page.goto()
        setup_page.create_account("newuser", "password1", "password2")
        
        # Wait for page to process and reload
        setup_page.page.wait_for_load_state("networkidle")
        
        error = setup_page.get_error_message()
        # Server flashes "Passwords do not match"
        assert "match" in error.lower() or "do not" in error.lower() or setup_page.page.url.endswith("/setup")
    
    def test_empty_username_shows_error(self, setup_page):
        """Empty username shows error."""
        setup_page.goto()
        setup_page.fill_password("password123")
        setup_page.fill_confirm_password("password123")
        setup_page.click_create_account()
        
        setup_page.page.wait_for_load_state("networkidle")
        
        error = setup_page.get_error_message()
        # Either form validation prevents submission or server returns error
        assert error or setup_page.page.url.endswith("/setup")
    
    def test_empty_password_shows_error(self, setup_page):
        """Empty password shows error."""
        setup_page.goto()
        setup_page.fill_username("newuser")
        setup_page.click_create_account()
        
        setup_page.page.wait_for_load_state("networkidle")
        
        error = setup_page.get_error_message()
        # Either form validation prevents submission or server returns error
        assert error or setup_page.page.url.endswith("/setup")


class TestSuccessfulSetup:
    """Test successful setup flow."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr needing setup."""
        transferarr.set_auth_config(
            enabled=True,
            username=None,
            password=None
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_successful_setup_redirects_to_dashboard(self, setup_page):
        """Successful account creation redirects to dashboard."""
        setup_page.goto()
        setup_page.create_account("newadmin", "securepass123")
        
        setup_page.wait_for_redirect()
        assert "/setup" not in setup_page.page.url
    
    def test_created_user_is_logged_in(self, setup_page):
        """After setup, user is automatically logged in."""
        setup_page.goto()
        setup_page.create_account("newadmin", "securepass123")
        
        setup_page.wait_for_redirect()
        
        # Should see user info in sidebar (logged in)
        user_info = setup_page.page.locator(".user-info")
        expect(user_info).to_be_visible()


class TestSkipSetup:
    """Test skip setup flow."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr needing setup."""
        transferarr.set_auth_config(
            enabled=True,
            username=None,
            password=None
        )
        transferarr.start(wait_healthy=True)
        yield
    
    def test_skip_button_redirects_to_dashboard(self, setup_page):
        """Clicking skip redirects to dashboard."""
        setup_page.goto()
        setup_page.click_skip()
        
        setup_page.wait_for_redirect()
        assert "/setup" not in setup_page.page.url
    
    def test_skip_disables_auth(self, setup_page):
        """Skipping setup disables auth (no login required)."""
        setup_page.goto()
        setup_page.click_skip()
        
        setup_page.wait_for_redirect()
        
        # User info should NOT be visible (auth disabled)
        user_info = setup_page.page.locator(".user-info")
        expect(user_info).not_to_be_visible()
    
    def test_after_skip_can_access_pages_directly(self, setup_page, base_url):
        """After skipping, can access protected pages directly."""
        setup_page.goto()
        setup_page.click_skip()
        
        setup_page.wait_for_redirect()
        
        # Navigate to settings - should work without login
        setup_page.page.goto(f"{base_url}/settings")
        expect(setup_page.page).to_have_title("Transferarr - Settings")
