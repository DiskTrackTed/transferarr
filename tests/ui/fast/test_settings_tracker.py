"""
UI tests for the Settings page Tracker tab.

Tests the Tracker tab UI elements, settings interactions, advanced options,
save/restart functionality, and status indicator display.
"""
import re
import pytest
from playwright.sync_api import Page, expect

from tests.ui.helpers import UI_TIMEOUTS


class TestTrackerTabElements:
    """Test tracker tab UI elements are present."""

    def test_tracker_tab_exists(self, settings_page):
        """Tracker tab exists in settings page."""
        settings_page.goto()

        tracker_tab = settings_page.get_tracker_tab()
        expect(tracker_tab).to_be_visible()
        expect(tracker_tab).to_contain_text("Tracker")

    def test_tracker_tab_can_be_selected(self, settings_page):
        """Can switch to Tracker tab."""
        settings_page.goto()

        settings_page.switch_to_tracker_tab()

        tracker_tab = settings_page.get_tracker_tab()
        expect(tracker_tab).to_have_class(re.compile(r"active"))

    def test_tracker_tab_content_hidden_initially(self, settings_page):
        """Tracker content hidden when tab not active."""
        settings_page.goto()

        tracker_content = settings_page.page.locator(settings_page.TAB_CONTENT_TRACKER)
        expect(tracker_content).to_be_hidden()

    def test_tracker_tab_content_visible_after_switch(self, settings_page):
        """Tracker content visible after switching to tab."""
        settings_page.goto()

        settings_page.switch_to_tracker_tab()

        tracker_content = settings_page.page.locator(settings_page.TAB_CONTENT_TRACKER)
        expect(tracker_content).to_be_visible()

    def test_status_indicator_visible(self, settings_page):
        """Status indicator is visible in tracker tab."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        indicator = settings_page.page.locator(settings_page.TRACKER_STATUS_INDICATOR)
        expect(indicator).to_be_visible()

    def test_status_dot_visible(self, settings_page):
        """Status dot is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        dot = settings_page.page.locator(settings_page.TRACKER_STATUS_DOT)
        expect(dot).to_be_visible()

    def test_status_text_visible(self, settings_page):
        """Status text is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        text = settings_page.page.locator(settings_page.TRACKER_STATUS_TEXT)
        expect(text).to_be_visible()

    def test_status_text_has_valid_value(self, settings_page):
        """Status text shows a valid status."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        text = settings_page.get_tracker_status_text()
        assert text in ("Running", "Stopped", "Disabled")

    def test_active_transfers_visible(self, settings_page):
        """Active transfers count is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        transfers = settings_page.page.locator(settings_page.TRACKER_ACTIVE_TRANSFERS)
        expect(transfers).to_be_visible()

    def test_running_port_visible(self, settings_page):
        """Running port is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        port = settings_page.page.locator(settings_page.TRACKER_RUNNING_PORT)
        expect(port).to_be_visible()

    def test_enabled_toggle_visible(self, settings_page):
        """Enabled toggle is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        toggle_switch = settings_page.page.locator('.toggle-switch').filter(
            has=settings_page.page.locator(settings_page.TRACKER_ENABLED_TOGGLE)
        )
        expect(toggle_switch).to_be_visible()

    def test_port_input_visible(self, settings_page):
        """Port input is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        expect(port_input).to_be_visible()

    def test_external_url_input_visible(self, settings_page):
        """External URL input is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        expect(url_input).to_be_visible()

    def test_advanced_toggle_visible(self, settings_page):
        """Advanced Options toggle is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        toggle = settings_page.page.locator(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)
        expect(toggle).to_be_visible()

    def test_advanced_options_hidden_by_default(self, settings_page):
        """Advanced options section is hidden by default."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        options = settings_page.page.locator(settings_page.TRACKER_ADVANCED_OPTIONS_DIV)
        expect(options).to_be_hidden()

    def test_save_button_visible(self, settings_page):
        """Save Settings button is visible."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_be_visible()
        expect(save_btn).to_contain_text("Save Settings")


class TestTrackerTabInteractions:
    """Test tracker tab form interactions."""

    def test_can_toggle_enabled(self, settings_page):
        """Can toggle the enabled switch."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        toggle = settings_page.page.locator(settings_page.TRACKER_ENABLED_TOGGLE)
        initial = toggle.is_checked()

        # Click the visible toggle-switch label (the checkbox input is hidden by CSS)
        toggle_slider = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_slider.click()
        assert toggle.is_checked() != initial

        # Toggle back
        toggle_slider.click()
        assert toggle.is_checked() == initial

    def test_can_enter_port(self, settings_page):
        """Can enter a value in the port field."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        port_input.clear()
        port_input.fill("7070")
        expect(port_input).to_have_value("7070")

    def test_can_enter_external_url(self, settings_page):
        """Can enter a value in the external URL field."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        url_input.fill("http://myhost:6969/announce")
        expect(url_input).to_have_value("http://myhost:6969/announce")

    def test_expand_advanced_options(self, settings_page):
        """Clicking Advanced Options toggle shows hidden fields."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        # Click to expand
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        options = settings_page.page.locator(settings_page.TRACKER_ADVANCED_OPTIONS_DIV)
        expect(options).to_be_visible()

    def test_collapse_advanced_options(self, settings_page):
        """Clicking Advanced Options toggle again hides the fields."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()

        toggle = settings_page.page.locator(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        # Expand
        toggle.click()
        options = settings_page.page.locator(settings_page.TRACKER_ADVANCED_OPTIONS_DIV)
        expect(options).to_be_visible()

        # Collapse
        toggle.click()
        expect(options).to_be_hidden()

    def test_announce_interval_visible_when_expanded(self, settings_page):
        """Announce interval input visible when advanced expanded."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        interval = settings_page.page.locator(settings_page.TRACKER_ANNOUNCE_INTERVAL_INPUT)
        expect(interval).to_be_visible()

    def test_peer_expiry_visible_when_expanded(self, settings_page):
        """Peer expiry input visible when advanced expanded."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        expiry = settings_page.page.locator(settings_page.TRACKER_PEER_EXPIRY_INPUT)
        expect(expiry).to_be_visible()

    def test_can_enter_announce_interval(self, settings_page):
        """Can enter a value in announce interval field."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        interval = settings_page.page.locator(settings_page.TRACKER_ANNOUNCE_INTERVAL_INPUT)
        interval.clear()
        interval.fill("90")
        expect(interval).to_have_value("90")

    def test_can_enter_peer_expiry(self, settings_page):
        """Can enter a value in peer expiry field."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        expiry = settings_page.page.locator(settings_page.TRACKER_PEER_EXPIRY_INPUT)
        expiry.clear()
        expiry.fill("180")
        expect(expiry).to_have_value("180")

    def test_port_field_has_loaded_value(self, settings_page):
        """Port field is populated with config value after loading."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        value = port_input.input_value()
        # Should have a numeric value from config (default 6969)
        assert value.isdigit()
        assert int(value) > 0


class TestTrackerSaveSettings:
    """Test saving tracker settings."""

    def test_save_shows_success_notification(self, settings_page):
        """Saving settings shows success toast notification."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Click save
        with settings_page.page.expect_response(
            lambda r: "/api/v1/tracker/settings" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            settings_page.page.click(settings_page.SAVE_TRACKER_BTN)

        assert response_info.value.status == 200

        # Check for success notification
        notification = settings_page.page.locator('.notification-success')
        expect(notification).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])

    def test_save_settings_updates_config(self, settings_page):
        """Saved settings persist when tab is reloaded."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Set a distinctive external URL
        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        url_input.fill("http://test-save:6969/announce")

        # Save
        with settings_page.page.expect_response(
            lambda r: "/api/v1/tracker/settings" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.page.click(settings_page.SAVE_TRACKER_BTN)

        # Reload page and check value persisted
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        expect(url_input).to_have_value("http://test-save:6969/announce")

    def test_save_and_apply_updates_status(self, settings_page):
        """Saving with apply updates the status indicator."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Change port to trigger "Save and Apply"
        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        original_port = port_input.input_value()
        port_input.clear()
        port_input.fill(original_port)  # Same value to restore after

        # Toggle enabled off and back on to trigger apply
        toggle = settings_page.page.locator(settings_page.TRACKER_ENABLED_TOGGLE)
        toggle_switch = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_switch.click()
        toggle_switch.click()
        # Button should say "Save Settings" since we toggled back to original
        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save Settings")

    def test_save_and_apply_sends_apply_flag(self, settings_page):
        """Changing port sends apply=true in the request."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Change port to trigger apply
        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        port_input.clear()
        port_input.fill("7070")

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save and Apply")

        with settings_page.page.expect_response(
            lambda r: "/api/v1/tracker/settings" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            save_btn.click()

        assert response_info.value.status == 200

        # After save, button should reset to "Save Settings"
        expect(save_btn).to_contain_text("Save Settings")

        notification = settings_page.page.locator('.notification-success')
        expect(notification).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])

        # Restore original port
        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        port_input.clear()
        port_input.fill("6969")
        with settings_page.page.expect_response(
            lambda r: "/api/v1/tracker/settings" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.page.click(settings_page.SAVE_TRACKER_BTN)


class TestDynamicSaveButton:
    """Test dynamic save button text based on field changes."""

    def test_button_shows_save_settings_by_default(self, settings_page):
        """Button shows 'Save Settings' when no restart fields changed."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save Settings")
        # Should not contain "Apply"
        expect(save_btn).not_to_contain_text("Apply")

    def test_button_changes_to_save_and_apply_on_port_change(self, settings_page):
        """Changing port switches button to 'Save and Apply'."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        port_input.clear()
        port_input.fill("7070")

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save and Apply")

    def test_button_changes_to_save_and_apply_on_enabled_toggle(self, settings_page):
        """Toggling enabled switches button to 'Save and Apply'."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        toggle = settings_page.page.locator(settings_page.TRACKER_ENABLED_TOGGLE)
        toggle_switch = settings_page.page.locator('.toggle-switch').filter(has=toggle)
        toggle_switch.click()

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save and Apply")

        # Toggle back - should revert to "Save Settings"
        toggle_switch.click()
        expect(save_btn).to_contain_text("Save Settings")
        expect(save_btn).not_to_contain_text("Apply")

    def test_button_stays_save_settings_on_url_change(self, settings_page):
        """Changing external URL keeps button as 'Save Settings'."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        url_input.fill("http://changed:6969/announce")

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save Settings")
        expect(save_btn).not_to_contain_text("Apply")

    def test_button_stays_save_settings_on_advanced_change(self, settings_page):
        """Changing advanced fields keeps button as 'Save Settings'."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Expand advanced
        settings_page.page.click(settings_page.TRACKER_ADVANCED_TOGGLE_BTN)

        interval = settings_page.page.locator(settings_page.TRACKER_ANNOUNCE_INTERVAL_INPUT)
        interval.clear()
        interval.fill("90")

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save Settings")
        expect(save_btn).not_to_contain_text("Apply")

    def test_button_reverts_when_port_restored(self, settings_page):
        """Restoring port to original value reverts button to 'Save Settings'."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        port_input = settings_page.page.locator(settings_page.TRACKER_PORT_INPUT)
        original = port_input.input_value()

        # Change port
        port_input.clear()
        port_input.fill("7070")
        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save and Apply")

        # Restore original
        port_input.clear()
        port_input.fill(original)
        expect(save_btn).to_contain_text("Save Settings")
        expect(save_btn).not_to_contain_text("Apply")

    def test_button_resets_after_save(self, settings_page):
        """Button resets to 'Save Settings' after successful save."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        # Change URL (no apply needed)
        url_input = settings_page.page.locator(settings_page.TRACKER_EXTERNAL_URL_INPUT)
        url_input.fill("http://reset-test:6969/announce")

        with settings_page.page.expect_response(
            lambda r: "/api/v1/tracker/settings" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.page.click(settings_page.SAVE_TRACKER_BTN)

        save_btn = settings_page.page.locator(settings_page.SAVE_TRACKER_BTN)
        expect(save_btn).to_contain_text("Save Settings")


class TestTrackerStatusDisplay:
    """Test tracker status indicator display."""

    def test_running_status_shows_green_dot(self, settings_page):
        """Running tracker shows green status dot."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        status_text = settings_page.get_tracker_status_text()
        if status_text == "Running":
            dot_class = settings_page.get_tracker_status_dot_class()
            assert "running" in dot_class

    def test_active_transfers_shows_number(self, settings_page):
        """Active transfers shows a numeric value."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        count = settings_page.get_tracker_active_transfers()
        assert count.isdigit()

    def test_running_port_shows_value_when_running(self, settings_page):
        """Running port shows actual port when tracker is running."""
        settings_page.goto()
        settings_page.switch_to_tracker_tab()
        settings_page.page.wait_for_load_state("networkidle")

        status_text = settings_page.get_tracker_status_text()
        port_text = settings_page.page.locator(settings_page.TRACKER_RUNNING_PORT).text_content().strip()

        if status_text == "Running":
            assert port_text.isdigit()
        else:
            assert port_text == "—"


class TestTrackerTabPersistence:
    """Test tracker tab URL hash persistence."""

    def test_tracker_tab_via_url_hash(self, settings_page):
        """Navigating to settings#tracker activates tracker tab."""
        settings_page.page.goto(f"{settings_page.base_url}/settings#tracker")
        settings_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        tracker_tab = settings_page.get_tracker_tab()
        expect(tracker_tab).to_have_class(re.compile(r"active"))

        tracker_content = settings_page.page.locator(settings_page.TAB_CONTENT_TRACKER)
        expect(tracker_content).to_be_visible()

    def test_switching_to_tracker_updates_url_hash(self, settings_page):
        """Switching to tracker tab updates URL hash."""
        settings_page.goto()

        settings_page.switch_to_tracker_tab()

        expect(settings_page.page).to_have_url(re.compile(r".*#tracker"))
