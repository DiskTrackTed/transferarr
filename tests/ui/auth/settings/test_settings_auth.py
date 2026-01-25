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
        
        # Wait for toast notification
        notification = settings_page.page.locator('.notification-success')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('Settings Saved')


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
        
        # Should show error toast
        notification = settings_page.page.locator('.notification-error')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('incorrect')

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
        
        # Should show error toast (client-side validation)
        notification = settings_page.page.locator('.notification-error')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('match')

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
        
        # Should show success toast
        notification = settings_page.page.locator('.notification-success')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('Password Changed')


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


class TestApiKeySection:
    """Test API key section UI elements and interactions."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr without user auth but with API key config.
        
        Note: key_required=False so the browser can access API without key header.
        The browser doesn't know the API key yet, so it can't authenticate with it.
        """
        transferarr.set_auth_config(enabled=False)
        transferarr.set_api_config(key="tr_testkey123456789012345678901234", key_required=False)
        transferarr.start(wait_healthy=True)
        yield

    def test_api_key_section_visible(self, settings_page, base_url):
        """API key section is visible in auth tab."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        api_section = settings_page.page.locator('#api-key-section')
        expect(api_section).to_be_visible()

    def test_api_key_auth_warning_visible_when_auth_disabled(self, settings_page, base_url):
        """Warning shows when API key exists but auth is disabled."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Warning should be visible (auth disabled + key exists)
        warning = settings_page.page.locator('#api-key-auth-warning')
        expect(warning).to_be_visible()
        expect(warning).to_contain_text('authentication is disabled')

    def test_api_key_required_toggle_visible(self, settings_page, base_url):
        """API key required toggle is visible."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        toggle = settings_page.page.locator('#api-key-required')
        # Toggle is inside a label, check label wrapper
        toggle_switch = settings_page.page.locator('.toggle-switch').filter(
            has=settings_page.page.locator('#api-key-required')
        )
        expect(toggle_switch).to_be_visible()

    def test_api_key_input_visible(self, settings_page, base_url):
        """API key input field is visible."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for API settings to load
        settings_page.page.wait_for_timeout(1000)
        
        key_input = settings_page.page.locator('#api-key-value')
        expect(key_input).to_be_visible()

    def test_api_key_masked_by_default(self, settings_page, base_url):
        """API key is masked by default."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for API settings to load by waiting for the input to have a value
        key_input = settings_page.page.locator('#api-key-value')
        # Wait for the input to have some value (not empty)
        settings_page.page.wait_for_function(
            "document.getElementById('api-key-value').value.length > 0",
            timeout=10000
        )
        
        # Value should be masked (contain bullets)
        value = key_input.input_value()
        # Should show prefix and then bullets
        assert value.startswith('tr_test'), f"Expected value to start with 'tr_test', got: '{value}'"
        assert '•' in value, f"Expected bullets in masked value, got: '{value}'"

    def test_toggle_visibility_button_shows_key(self, settings_page, base_url):
        """Clicking visibility toggle shows full key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        # Wait for API settings to load
        settings_page.page.wait_for_function(
            "document.getElementById('api-key-value').value.length > 0",
            timeout=10000
        )
        
        # Click visibility toggle
        settings_page.page.click('#toggle-api-key-visibility')
        settings_page.page.wait_for_timeout(500)
        
        key_input = settings_page.page.locator('#api-key-value')
        value = key_input.input_value()
        # Should show full key now
        assert value == 'tr_testkey123456789012345678901234'

    def test_copy_button_visible(self, settings_page, base_url):
        """Copy button is visible."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        copy_btn = settings_page.page.locator('#copy-api-key')
        expect(copy_btn).to_be_visible()

    def test_generate_button_visible(self, settings_page, base_url):
        """Generate/Regenerate button is visible."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        
        generate_btn = settings_page.page.locator('#generate-api-key')
        expect(generate_btn).to_be_visible()
        # Should say "Regenerate" since key exists
        expect(generate_btn).to_contain_text('Regenerate')

    def test_revoke_button_visible_when_key_exists(self, settings_page, base_url):
        """Revoke button is visible when API key exists."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        revoke_btn = settings_page.page.locator('#revoke-api-key')
        expect(revoke_btn).to_be_visible()

    def test_key_required_toggle_state(self, settings_page, base_url):
        """Key required toggle reflects config state."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        toggle = settings_page.page.locator('#api-key-required')
        expect(toggle).not_to_be_checked()  # Set to False in fixture

    def test_revoke_key_removes_key(self, settings_page, base_url):
        """Clicking revoke button removes the API key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Verify key exists first
        key_input = settings_page.page.locator('#api-key-value')
        initial_value = key_input.input_value()
        assert initial_value != '', "Expected key to exist initially"
        
        # Set up dialog handler to accept the confirm prompt
        settings_page.page.on('dialog', lambda dialog: dialog.accept())
        
        # Click revoke button and wait for the API response
        with settings_page.page.expect_response(
            lambda r: "/api/v1/auth/api-key/revoke" in r.url,
            timeout=10000
        ):
            settings_page.page.click('#revoke-api-key')
        
        # Wait for the UI to update
        settings_page.page.wait_for_timeout(500)
        
        # Verify key was removed
        value = key_input.input_value()
        assert value == '', f"Expected key to be empty, got: '{value}'"
        
        # Button should now say "Generate API Key"
        generate_btn = settings_page.page.locator('#generate-api-key')
        expect(generate_btn).to_contain_text('Generate API Key')
        
        # Revoke button should be hidden
        revoke_btn = settings_page.page.locator('#revoke-api-key')
        expect(revoke_btn).to_be_hidden()

    def test_regenerate_key_changes_key(self, settings_page, base_url):
        """Clicking regenerate creates a different API key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Get the initial key (masked, so just check it's not empty)
        key_input = settings_page.page.locator('#api-key-value')
        initial_key = key_input.input_value()
        assert initial_key != '', "Expected initial key to exist"
        
        # Set up dialog handler to accept the confirm prompt
        settings_page.page.on('dialog', lambda dialog: dialog.accept())
        
        # Click regenerate button and wait for the API response
        with settings_page.page.expect_response(
            lambda r: "/api/v1/auth/api-key/generate" in r.url,
            timeout=10000
        ):
            settings_page.page.click('#generate-api-key')
        
        # Wait for the UI to update
        settings_page.page.wait_for_timeout(500)
        
        # Verify key changed (new key should be visible by default after generation)
        new_key = key_input.input_value()
        assert new_key.startswith('tr_'), f"Expected key to start with 'tr_', got: '{new_key}'"

    def test_enable_key_required_with_auth_disabled_shows_error(self, settings_page, base_url):
        """Enabling key_required with auth disabled shows error notification."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Toggle key_required ON using the visible slider
        toggle = settings_page.page.locator('#api-key-required')
        toggle_slider = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_slider.click()
        
        # Save button should appear
        save_btn = settings_page.page.locator('#save-api-key-settings')
        expect(save_btn).to_be_visible()
        
        # Click save and wait for API response
        with settings_page.page.expect_response(
            lambda r: "/api/v1/auth/api-key" in r.url and r.request.method == "PUT",
            timeout=10000
        ):
            save_btn.click()
        
        # Should show error toast (cannot enable key_required with auth disabled)
        notification = settings_page.page.locator('.notification-error')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('auth')


class TestApiKeySectionNoKey:
    """Test API key section when no key is configured."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr without API key."""
        transferarr.set_auth_config(enabled=False)
        transferarr.clear_api_config()
        transferarr.start(wait_healthy=True)
        yield

    def test_generate_button_shows_generate(self, settings_page, base_url):
        """Generate button shows 'Generate API Key' when no key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        generate_btn = settings_page.page.locator('#generate-api-key')
        expect(generate_btn).to_contain_text('Generate API Key')

    def test_api_key_auth_warning_hidden_when_no_key(self, settings_page, base_url):
        """Warning is hidden when no API key exists (even with auth disabled)."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        warning = settings_page.page.locator('#api-key-auth-warning')
        expect(warning).to_be_hidden()

    def test_revoke_button_hidden_when_no_key(self, settings_page, base_url):
        """Revoke button is hidden when no API key exists."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        revoke_btn = settings_page.page.locator('#revoke-api-key')
        expect(revoke_btn).to_be_hidden()

    def test_key_input_shows_placeholder(self, settings_page, base_url):
        """Key input shows placeholder when no key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        key_input = settings_page.page.locator('#api-key-value')
        placeholder = key_input.get_attribute('placeholder')
        assert placeholder == 'No API key generated'

    def test_key_required_toggle_off_by_default(self, settings_page, base_url):
        """Key required toggle is OFF when no API config exists."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        toggle = settings_page.page.locator('#api-key-required')
        expect(toggle).not_to_be_checked()

    def test_generate_key_creates_new_key(self, settings_page, base_url):
        """Clicking generate button creates a new API key."""
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Click generate button and wait for the API response
        with settings_page.page.expect_response(
            lambda r: "/api/v1/auth/api-key" in r.url and "generate" in r.url,
            timeout=15000
        ):
            settings_page.page.click('#generate-api-key')
        
        # Wait for the UI to update (new key is automatically visible)
        settings_page.page.wait_for_timeout(1000)
        
        # Verify key was generated (key is visible by default after generation)
        key_input = settings_page.page.locator('#api-key-value')
        value = key_input.input_value()
        assert value.startswith('tr_'), f"Expected key to start with 'tr_', got: '{value}'"
        
        # Revoke button should now be visible
        revoke_btn = settings_page.page.locator('#revoke-api-key')
        expect(revoke_btn).to_be_visible()


class TestApiKeyWithAuthEnabled:
    """Test API key settings when user auth is enabled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Set up transferarr with user auth enabled and API key configured."""
        transferarr.set_auth_config(
            enabled=True,
            username="testuser",
            password="testpass123"
        )
        transferarr.set_api_config(key="tr_testkey123456789012345678901234", key_required=False)
        transferarr.start(wait_healthy=True)
        yield

    def test_enable_key_required_saves_successfully(self, settings_page, login_page):
        """Enabling key_required with auth enabled saves successfully."""
        # Login first
        login_page.goto()
        login_page.login("testuser", "testpass123")
        login_page.wait_for_redirect()
        
        settings_page.goto()
        settings_page.page.click('[data-tab="auth"]')
        settings_page.page.wait_for_load_state("networkidle")
        settings_page.page.wait_for_timeout(1000)
        
        # Toggle key_required ON using the visible slider
        toggle = settings_page.page.locator('#api-key-required')
        toggle_slider = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_slider.click()
        
        # Save button should appear
        save_btn = settings_page.page.locator('#save-api-key-settings')
        expect(save_btn).to_be_visible()
        
        # Click save and wait for API response
        with settings_page.page.expect_response(
            lambda r: "/api/v1/auth/api-key" in r.url and r.request.method == "PUT",
            timeout=10000
        ):
            save_btn.click()
        
        # Should show success toast
        notification = settings_page.page.locator('.notification-success')
        expect(notification).to_be_visible(timeout=5000)
        expect(notification).to_contain_text('Settings Saved')
        
        # Save button should be hidden again
        expect(save_btn).to_be_hidden()
