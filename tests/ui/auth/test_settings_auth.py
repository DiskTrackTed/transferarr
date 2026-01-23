"""
UI tests for the Settings page Authentication tab.

Tests the Auth tab UI elements, settings changes, and password change form.
"""
import pytest
from playwright.sync_api import expect


class TestAuthTabElements:
    """Test auth tab UI elements are present."""

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

    def test_auth_tab_exists(self, settings_page, login_page):
        """Auth tab exists in settings page."""
        # Login first
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        # Navigate to settings
        settings_page.goto()
        
        # Check for auth tab
        auth_tab = settings_page.page.locator('[data-tab="auth"]')
        expect(auth_tab).to_be_visible()
        expect(auth_tab).to_contain_text("Authentication")

    def test_auth_tab_content_loads(self, settings_page, login_page):
        """Auth tab content loads when clicked."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        
        # Click auth tab
        settings_page.page.click('[data-tab="auth"]')
        
        # Wait for content
        auth_content = settings_page.page.locator('#auth-tab-content')
        expect(auth_content).to_be_visible()

    def test_auth_enabled_toggle_visible(self, settings_page, login_page):
        """Auth enabled toggle is visible."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        
        # The toggle-switch label is visible, the input inside is hidden by CSS
        toggle_switch = settings_page.page.locator('.toggle-switch').filter(has=settings_page.page.locator('#auth-enabled'))
        expect(toggle_switch).to_be_visible()

    def test_session_timeout_select_visible(self, settings_page, login_page):
        """Session timeout select is visible."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        
        select = settings_page.page.locator('#session-timeout')
        expect(select).to_be_visible()

    def test_save_settings_button_visible(self, settings_page, login_page):
        """Save settings button is visible."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        
        button = settings_page.page.locator('#save-auth-settings')
        expect(button).to_be_visible()

    def test_change_password_form_visible(self, settings_page, login_page):
        """Change password form is visible when auth enabled."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        
        # Wait for auth settings to load
        settings_page.page.wait_for_load_state("networkidle")
        
        form = settings_page.page.locator('#change-password-form')
        expect(form).to_be_visible()

    def test_password_fields_visible(self, settings_page, login_page):
        """All password fields are visible."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        expect(settings_page.page.locator('#current-password')).to_be_visible()
        expect(settings_page.page.locator('#new-password')).to_be_visible()
        expect(settings_page.page.locator('#confirm-new-password')).to_be_visible()


class TestAuthTabInteractions:
    """Test auth tab form interactions."""

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

    def test_can_toggle_auth_enabled(self, settings_page, login_page):
        """Can toggle auth enabled checkbox."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        toggle = settings_page.page.locator('#auth-enabled')
        
        # Wait for auth settings API to load and populate the checkbox
        # The checkbox should be checked because auth is enabled
        settings_page.page.wait_for_timeout(500)  # Small delay for JS to populate
        expect(toggle).to_be_checked(timeout=5000)
        
        # Uncheck it using the visible slider
        toggle_slider = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_slider.click()
        expect(toggle).not_to_be_checked()
        
        # Check again
        toggle_slider.click()
        expect(toggle).to_be_checked()

    def test_can_change_session_timeout(self, settings_page, login_page):
        """Can change session timeout dropdown."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        select = settings_page.page.locator('#session-timeout')
        
        # Change to 8 hours
        select.select_option('480')
        expect(select).to_have_value('480')

    def test_restart_warning_hidden_by_default(self, settings_page, login_page):
        """Restart warning is hidden when timeout matches runtime value."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for settings to load
        settings_page.page.wait_for_timeout(500)
        
        # Restart warning should be hidden
        restart_warning = settings_page.page.locator('#restart-warning')
        expect(restart_warning).to_be_hidden()

    def test_restart_warning_shows_on_timeout_change(self, settings_page, login_page):
        """Restart warning appears when session timeout is changed."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for settings to load
        settings_page.page.wait_for_timeout(500)
        
        # Get current value and change to a different one
        select = settings_page.page.locator('#session-timeout')
        current_value = select.input_value()
        new_value = '480' if current_value != '480' else '120'
        
        # Change timeout
        select.select_option(new_value)
        
        # Restart warning should now be visible
        restart_warning = settings_page.page.locator('#restart-warning')
        expect(restart_warning).to_be_visible()
        expect(restart_warning).to_contain_text('restart')

    def test_restart_warning_hides_when_reset(self, settings_page, login_page):
        """Restart warning hides when timeout is reset to original value."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for settings to load
        settings_page.page.wait_for_timeout(500)
        
        select = settings_page.page.locator('#session-timeout')
        original_value = select.input_value()
        new_value = '480' if original_value != '480' else '120'
        
        # Change timeout - warning appears
        select.select_option(new_value)
        restart_warning = settings_page.page.locator('#restart-warning')
        expect(restart_warning).to_be_visible()
        
        # Change back to original - warning disappears
        select.select_option(original_value)
        expect(restart_warning).to_be_hidden()

    def test_can_type_in_password_fields(self, settings_page, login_page):
        """Can type in all password fields."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        settings_page.page.fill('#current-password', 'currentpass')
        settings_page.page.fill('#new-password', 'newpassword')
        settings_page.page.fill('#confirm-new-password', 'newpassword')
        
        expect(settings_page.page.locator('#current-password')).to_have_value('currentpass')
        expect(settings_page.page.locator('#new-password')).to_have_value('newpassword')
        expect(settings_page.page.locator('#confirm-new-password')).to_have_value('newpassword')


class TestSaveAuthSettings:
    """Test saving auth settings."""

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

    def test_save_settings_shows_success(self, settings_page, login_page):
        """Saving settings shows success message."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Click save
        settings_page.page.click('#save-auth-settings')
        
        # Wait for status message
        status = settings_page.page.locator('#auth-settings-status')
        expect(status).to_contain_text('saved', timeout=5000)


class TestChangePassword:
    """Test password change functionality."""

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

    def test_change_password_with_wrong_current(self, settings_page, login_page):
        """Wrong current password shows error."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Fill form with wrong current password
        settings_page.page.fill('#current-password', 'wrongpassword')
        settings_page.page.fill('#new-password', 'newpassword123')
        settings_page.page.fill('#confirm-new-password', 'newpassword123')
        
        # Submit
        settings_page.page.click('#change-password-form button[type="submit"]')
        
        # Should show error
        status = settings_page.page.locator('#password-change-status')
        expect(status).to_contain_text('incorrect', timeout=5000)

    def test_change_password_mismatch(self, settings_page, login_page):
        """Mismatched passwords show error."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Fill form with mismatched passwords
        settings_page.page.fill('#current-password', 'testpass123')
        settings_page.page.fill('#new-password', 'newpassword123')
        settings_page.page.fill('#confirm-new-password', 'differentpassword')
        
        # Submit
        settings_page.page.click('#change-password-form button[type="submit"]')
        
        # Should show error (client-side validation)
        status = settings_page.page.locator('#password-change-status')
        expect(status).to_contain_text('match', timeout=5000)

    def test_change_password_success(self, settings_page, login_page):
        """Successful password change shows success message."""
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Fill form correctly
        settings_page.page.fill('#current-password', 'testpass123')
        settings_page.page.fill('#new-password', 'newpassword123')
        settings_page.page.fill('#confirm-new-password', 'newpassword123')
        
        # Submit
        settings_page.page.click('#change-password-form button[type="submit"]')
        
        # Should show success
        status = settings_page.page.locator('#password-change-status')
        expect(status).to_contain_text('success', timeout=5000)


class TestAuthTabWhenDisabled:
    """Test auth tab behavior when auth is disabled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr with auth disabled."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        yield

    def test_auth_tab_accessible_when_disabled(self, settings_page, base_url):
        """Auth tab is accessible when auth is disabled."""
        settings_page.goto()
        
        # Click auth tab
        settings_page.page.click('[data-tab="auth"]')
        
        # Should show the tab content
        auth_content = settings_page.page.locator('#auth-tab-content')
        expect(auth_content).to_be_visible()

    def test_auth_toggle_shows_disabled_state(self, settings_page, base_url):
        """Auth toggle shows disabled state."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        toggle = settings_page.page.locator('#auth-enabled')
        expect(toggle).not_to_be_checked()

    def test_password_form_hidden_when_disabled(self, settings_page, base_url):
        """Password form is hidden when auth is disabled."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for JS to load settings and update UI
        settings_page.page.wait_for_timeout(1000)
        
        # Password section should be hidden (display: none set by JS)
        password_section = settings_page.page.locator('#change-password-section')
        expect(password_section).to_be_hidden()

    def test_info_message_shown_when_disabled(self, settings_page, base_url):
        """Info message is shown when auth is disabled."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for JS to load settings and update UI
        settings_page.page.wait_for_timeout(1000)
        
        # Info message should be visible (display: block set by JS)
        info = settings_page.page.locator('#auth-disabled-info')
        expect(info).to_be_visible()
