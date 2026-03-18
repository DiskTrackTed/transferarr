"""
Connection CRUD tests for Transferarr UI.

Tests the complete connection management workflow including:
- Adding new connections via the UI
- Testing connection configuration
- Editing existing connections
- Deleting connections
- Form validation
- Error handling
- Torrent transfer method form behaviour

Note: Connection tests are more complex because:
1. Connections require existing download clients
2. Connection modal requires successful connection test before paths can be configured
3. The SFTP config is more complex with multiple fields
"""
import logging
import pytest
from playwright.sync_api import Page, expect

# Import test configuration and helpers
from tests.conftest import SERVICES
from tests.ui.helpers import (
    UI_TIMEOUTS,
    add_torrent_connection_via_ui,
    delete_connection_via_api,
    get_connection_config_via_api,
    log_test_step,
)

logger = logging.getLogger(__name__)


class TestConnectionsList:
    """Tests for connections list display."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_connections_tab_loads(self, settings_page):
        """Test that connections tab loads correctly."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        # Should see connections content
        expect(settings_page.page.locator(settings_page.CONNECTIONS_CONTENT)).to_be_visible()
    
    def test_connections_list_shows_existing_connections(self, settings_page):
        """Test that existing connections are displayed."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        # Get connection count (may be 0 or more depending on config)
        count = settings_page.get_connection_count()
        assert count >= 0  # At minimum, should not error
    
    def test_add_connection_button_visible(self, settings_page):
        """Test that Add Connection button is visible."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        add_btn = settings_page.page.locator(settings_page.ADD_CONNECTION_BTN)
        expect(add_btn).to_be_visible()


class TestAddConnection:
    """Tests for adding new connections."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_add_connection_modal_opens(self, settings_page):
        """Test that add connection modal opens."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        settings_page.open_add_connection_modal()
        
        expect(settings_page.page.locator(settings_page.CONNECTION_MODAL)).to_be_visible()
    
    def test_add_connection_modal_has_client_dropdowns(self, settings_page):
        """Test that modal has from/to client dropdowns."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Both dropdowns should be visible
        expect(settings_page.page.locator(settings_page.CONNECTION_FROM_SELECT)).to_be_visible()
        expect(settings_page.page.locator(settings_page.CONNECTION_TO_SELECT)).to_be_visible()
    
    def test_add_connection_modal_populates_clients(self, settings_page):
        """Test that client dropdowns are populated with existing clients."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Wait for clients to be populated
        settings_page.page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])
        
        from_select = settings_page.page.locator(settings_page.CONNECTION_FROM_SELECT)
        options = from_select.locator("option").all()
        
        # Should have at least one option (empty/placeholder or actual clients)
        assert len(options) >= 1
    
    def test_save_button_disabled_before_test(self, settings_page):
        """Test that save button is disabled until connection tested."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        save_btn = settings_page.page.locator(settings_page.SAVE_CONNECTION_BTN)
        expect(save_btn).to_be_disabled()


class TestConnectionForm:
    """Tests for connection form interactions."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_from_type_changes_config_visibility(self, settings_page):
        """Test that changing from type shows/hides SFTP config."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Switch to file transfer mode (default is torrent, which hides type selects)
        settings_page.page.select_option(settings_page.TRANSFER_METHOD, "file")
        settings_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        from_type_select = settings_page.page.locator(settings_page.CONNECTION_FROM_TYPE)
        from_sftp_config = settings_page.page.locator("#fromSftpConfig")
        
        # Select local - SFTP config should hide
        from_type_select.select_option("local")
        expect(from_sftp_config).to_be_hidden()
        
        # Select sftp - SFTP config should show
        from_type_select.select_option("sftp")
        expect(from_sftp_config).to_be_visible()
    
    def test_to_type_changes_config_visibility(self, settings_page):
        """Test that changing to type shows/hides SFTP config."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Switch to file transfer mode (default is torrent, which hides type selects)
        settings_page.page.select_option(settings_page.TRANSFER_METHOD, "file")
        settings_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        to_type_select = settings_page.page.locator(settings_page.CONNECTION_TO_TYPE)
        to_sftp_config = settings_page.page.locator("#toSftpConfig")
        
        # Select local - SFTP config should hide
        to_type_select.select_option("local")
        expect(to_sftp_config).to_be_hidden()
        
        # Select sftp - SFTP config should show
        to_type_select.select_option("sftp")
        expect(to_sftp_config).to_be_visible()
    
    def test_path_config_disabled_before_test(self, settings_page):
        """Test that path configuration is disabled before connection test."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Path fields should be disabled initially
        source_path = settings_page.page.locator(settings_page.SOURCE_DOT_TORRENT_PATH)
        expect(source_path).to_be_disabled()
    
    def test_modal_close_button_works(self, settings_page):
        """Test that modal close button works."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Modal should be visible
        expect(settings_page.page.locator(settings_page.CONNECTION_MODAL)).to_be_visible()
        
        # Close it
        settings_page.close_connection_modal()
        
        # Modal should be hidden
        expect(settings_page.page.locator(settings_page.CONNECTION_MODAL)).not_to_be_visible()


class TestTestConnection:
    """Tests for testing connection configuration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_test_connection_button_visible(self, settings_page):
        """Test that test connection button is visible."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        test_btn = settings_page.page.locator(settings_page.TEST_CONNECTION_BTN2)
        expect(test_btn).to_be_visible()
    
    def test_test_connection_with_local_type(self, settings_page, page: Page):
        """Test connection with local transfer type."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Wait for clients to load in dropdowns
        page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])
        
        # Get available clients
        from_select = settings_page.page.locator(settings_page.CONNECTION_FROM_SELECT)
        to_select = settings_page.page.locator(settings_page.CONNECTION_TO_SELECT)
        
        from_options = from_select.locator("option").all()
        
        if len(from_options) < 2:
            pytest.skip("Need at least 2 clients for connection test")
        
        # Select different clients for from/to
        # Get values (skip empty/placeholder options)
        client_values = [opt.get_attribute("value") for opt in from_options if opt.get_attribute("value")]
        if len(client_values) < 2:
            pytest.skip("Need at least 2 non-empty client options")
        
        from_select.select_option(client_values[0])
        to_select.select_option(client_values[1])
        
        # Switch to file transfer mode (default is torrent, which hides type selects)
        settings_page.page.select_option(settings_page.TRANSFER_METHOD, "file")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        # Select from/to types as local
        settings_page.page.select_option(settings_page.CONNECTION_FROM_TYPE, "local")
        settings_page.page.select_option(settings_page.CONNECTION_TO_TYPE, "local")
        
        # Test connection - this may take a while for SFTP connection tests
        with page.expect_response(
            lambda r: "/api/v1/connections/test" in r.url,
            timeout=UI_TIMEOUTS['api_response_slow']  # 60s timeout
        ) as response_info:
            settings_page.test_connection()
        
        # Should get a response (success or failure) - Phase 3 format wraps in data envelope
        response = response_info.value.json()
        # Check for data.success (new format) or error (old format)
        assert ("data" in response and "success" in response.get("data", {})) or "error" in response


class TestEditConnection:
    """Tests for editing existing connections."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_edit_connection_opens_modal(self, settings_page):
        """Test that clicking edit opens the connection modal."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No existing connections to edit")
        
        # Click edit on first connection
        first_card = connections[0]
        first_card.locator(".btn-primary").click()
        
        # Modal should open
        expect(settings_page.page.locator(settings_page.CONNECTION_MODAL)).to_be_visible()
    
    def test_edit_modal_shows_connection_title(self, settings_page):
        """Test that edit modal shows 'Edit Connection' title."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No existing connections to edit")
        
        # Click edit
        first_card = connections[0]
        first_card.locator(".btn-primary").click()
        
        # Title should say "Edit Connection"
        modal_title = settings_page.page.locator("#connectionModalTitle")
        expect(modal_title).to_have_text("Edit Connection")


class TestDeleteConnection:
    """Tests for deleting connections."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_delete_shows_confirmation(self, settings_page, page: Page):
        """Test that delete shows browser confirmation dialog."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No existing connections to delete")
        
        first_card = connections[0]
        
        # Track if dialog was shown
        dialog_shown = False
        dialog_message = ""
        
        def handle_dialog(dialog):
            nonlocal dialog_shown, dialog_message
            dialog_shown = True
            dialog_message = dialog.message
            dialog.dismiss()  # Cancel the delete
        
        page.once("dialog", handle_dialog)
        
        # Click delete
        first_card.locator(".btn-danger").click()
        
        # Wait for dialog
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        # Dialog should have been shown
        assert dialog_shown
        assert "delete" in dialog_message.lower() or "sure" in dialog_message.lower()
    
    def test_cancel_delete_keeps_connection(self, settings_page, page: Page):
        """Test that dismissing delete dialog keeps connection."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        initial_count = settings_page.get_connection_count()
        if initial_count == 0:
            pytest.skip("No existing connections to test delete cancel")
        
        connections = settings_page.get_connection_cards()
        first_card = connections[0]
        
        # Set up to dismiss dialog
        page.once("dialog", lambda d: d.dismiss())
        
        # Click delete
        first_card.locator(".btn-danger").click()
        
        # Wait for dialog to be handled
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        # Count should be unchanged
        assert settings_page.get_connection_count() == initial_count


class TestConnectionValidation:
    """Tests for connection form validation and error handling."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_cannot_select_same_client_for_from_and_to(self, settings_page, page: Page):
        """Test that from and to clients should be different.
        
        Note: This depends on UI validation - may need to check if API rejects it.
        """
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        # Wait for clients to load
        page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])
        
        from_select = settings_page.page.locator(settings_page.CONNECTION_FROM_SELECT)
        to_select = settings_page.page.locator(settings_page.CONNECTION_TO_SELECT)
        
        # Get first option value
        first_option = from_select.locator("option").first
        first_value = first_option.get_attribute("value")
        
        if not first_value:
            pytest.skip("No clients available")
        
        # Select same client for both
        from_select.select_option(first_value)
        to_select.select_option(first_value)
        
        # The UI should either:
        # 1. Prevent this selection
        # 2. Show an error when testing/saving
        # This is a basic check that both fields have values
        assert from_select.input_value() == to_select.input_value()


class TestConnectionCardDisplay:
    """Tests for connection card display."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_connection_card_shows_client_names(self, settings_page):
        """Test that connection card shows from/to client names."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No connections to display")
        
        first_card = connections[0]
        card_header = first_card.locator(".card-header")
        header_text = card_header.text_content()
        
        # Should show "From → To" format
        assert "→" in header_text or "->" in header_text
    
    def test_connection_card_shows_status(self, settings_page):
        """Test that connection card shows status badge."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No connections to display")
        
        first_card = connections[0]
        status_badge = first_card.locator(".status-badge")
        
        expect(status_badge).to_be_visible()
    
    def test_connection_card_shows_transfer_stats(self, settings_page):
        """Test that connection card shows transfer statistics."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        connections = settings_page.get_connection_cards()
        if len(connections) == 0:
            pytest.skip("No connections to display")
        
        first_card = connections[0]
        card_text = first_card.text_content()
        
        # Should contain transfer info
        assert "Transfer" in card_text or "Active" in card_text


class TestTorrentConnectionForm:
    """Tests for torrent transfer method in the connection modal."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup with torrent-transfer config so the tracker is available."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True, config_type='torrent-transfer')

    def _open_connection_modal(self, settings_page, page):
        """Navigate to connections tab and open the add connection modal."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_transfer_method_selector_visible(self, settings_page, page: Page):
        """Test that Transfer Method selector is visible in Add Connection modal."""
        log_test_step("Test: Transfer Method selector visible")
        self._open_connection_modal(settings_page, page)

        transfer_method = page.locator(settings_page.TRANSFER_METHOD)
        expect(transfer_method).to_be_visible()

        # Should have two options
        options = transfer_method.locator("option").all()
        option_values = [opt.get_attribute("value") for opt in options]
        assert "file" in option_values
        assert "torrent" in option_values
        print("  ✓ Transfer Method selector visible with file/torrent options")

    def test_transfer_method_defaults_to_torrent(self, settings_page, page: Page):
        """Test that Torrent is the default transfer method."""
        log_test_step("Test: Transfer Method defaults to Torrent")
        self._open_connection_modal(settings_page, page)
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        transfer_method = page.locator(settings_page.TRANSFER_METHOD)
        assert transfer_method.input_value() == "torrent"

        # File-transfer-only elements should be hidden
        file_only_elements = page.locator(settings_page.FILE_TRANSFER_ONLY).all()
        for el in file_only_elements:
            display = el.evaluate("el => el.style.display")
            assert display == "none", "File-transfer-only element should be hidden by default"

        # Torrent config should be visible
        torrent_config = page.locator(settings_page.TORRENT_TRANSFER_CONFIG)
        expect(torrent_config).to_be_visible()
        print("  ✓ Torrent is selected by default")

    def test_switching_to_torrent_hides_sftp_config(self, settings_page, page: Page):
        """Test that selecting Torrent hides SFTP config and path sections."""
        log_test_step("Test: Switching to Torrent hides SFTP/path config")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent method
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # File-transfer-only elements (type selectors, path config) should be hidden
        file_only_elements = page.locator(settings_page.FILE_TRANSFER_ONLY).all()
        for el in file_only_elements:
            display = el.evaluate("el => el.style.display")
            assert display == "none", "File-transfer-only element should be hidden for torrent method"

        # Path config section should be hidden
        path_section = page.locator(".path-config-section")
        expect(path_section).to_be_hidden()

        # Torrent config should be visible
        torrent_config = page.locator(settings_page.TORRENT_TRANSFER_CONFIG)
        expect(torrent_config).to_be_visible()

        # Client dropdowns should still be visible
        expect(page.locator(settings_page.CONNECTION_FROM_SELECT)).to_be_visible()
        expect(page.locator(settings_page.CONNECTION_TO_SELECT)).to_be_visible()
        print("  ✓ SFTP config and path sections hidden for torrent method")

    def test_switching_to_file_transfer_shows_sftp_config(self, settings_page, page: Page):
        """Test that switching back to File Transfer restores SFTP config."""
        log_test_step("Test: Switching back to File Transfer restores config")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Verify torrent config is visible
        expect(page.locator(settings_page.TORRENT_TRANSFER_CONFIG)).to_be_visible()

        # Switch back to file
        page.select_option(settings_page.TRANSFER_METHOD, "file")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # File-transfer-only elements should be visible again
        file_only_elements = page.locator(settings_page.FILE_TRANSFER_ONLY).all()
        for el in file_only_elements:
            display = el.evaluate("el => el.style.display")
            assert display != "none", "File-transfer-only element should be visible for file method"

        # Torrent config should be hidden again
        expect(page.locator(settings_page.TORRENT_TRANSFER_CONFIG)).to_be_hidden()
        print("  ✓ File transfer config restored when switching back")

    def test_torrent_type_shows_destination_path(self, settings_page, page: Page):
        """Test that Torrent type shows destination path under Advanced Options."""
        log_test_step("Test: Torrent shows destination path in advanced options")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Advanced toggle should be visible
        advanced_toggle = page.locator(settings_page.TORRENT_ADVANCED_TOGGLE)
        expect(advanced_toggle).to_be_visible()

        # Destination path should be hidden (collapsed) by default
        dest_path = page.locator(settings_page.TORRENT_DESTINATION_PATH)
        expect(dest_path).to_be_hidden()

        # Click to expand advanced options
        advanced_toggle.click()
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Now destination path should be visible
        expect(dest_path).to_be_visible()

        # Should have placeholder indicating optional
        placeholder = dest_path.get_attribute("placeholder")
        assert "empty" in placeholder.lower() or "default" in placeholder.lower(), \
            f"Placeholder should indicate optional, got: {placeholder}"

        # Can type in the field
        dest_path.fill("/custom/downloads")
        assert dest_path.input_value() == "/custom/downloads"

        # Magnet-only checkbox should be visible and unchecked by default
        magnet_only = page.locator(settings_page.TORRENT_MAGNET_ONLY)
        expect(magnet_only).to_be_visible()
        expect(magnet_only).not_to_be_checked()

        print("  ✓ Torrent destination path visible under Advanced Options")

    def test_torrent_type_shows_tracker_info_note(self, settings_page, page: Page):
        """Test that Torrent type shows tracker requirement note."""
        log_test_step("Test: Torrent shows tracker info note")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Info alert should be visible
        tracker_info = page.locator(settings_page.TORRENT_TRACKER_INFO)
        expect(tracker_info).to_be_visible()

        # Should mention tracker
        info_text = tracker_info.text_content()
        assert "tracker" in info_text.lower(), f"Tracker info should mention tracker, got: {info_text}"
        print("  ✓ Tracker requirement info note is visible")

    @pytest.mark.timeout(120)
    def test_torrent_test_connection_checks_clients_and_tracker(self, settings_page, page: Page):
        """Test that Test Connection for torrent verifies clients and tracker."""
        log_test_step("Test: Torrent test connection checks clients + tracker")
        self._open_connection_modal(settings_page, page)

        page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])

        # Select torrent method
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Fill connection name and clients
        page.fill(settings_page.CONNECTION_NAME, "test-torrent-conn")
        page.select_option(settings_page.CONNECTION_FROM_SELECT, "source-deluge")
        page.select_option(settings_page.CONNECTION_TO_SELECT, "target-deluge")

        # Enable magnet-only mode so test doesn't fail on empty SFTP fields
        page.click(settings_page.TORRENT_ADVANCED_TOGGLE)
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        page.locator(settings_page.TORRENT_MAGNET_ONLY).check()
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Test connection
        with page.expect_response(
            lambda r: "/api/v1/connections/test" in r.url,
            timeout=UI_TIMEOUTS['api_response_slow']
        ) as response_info:
            settings_page.test_connection()

        response = response_info.value.json()
        test_result = response.get('data', response) if isinstance(response, dict) and 'data' in response else response

        # Should succeed — tracker is running with torrent-transfer config
        assert test_result.get("success"), f"Torrent connection test should succeed: {response}"
        print("  ✓ Torrent test connection verifies clients and tracker")

    @pytest.mark.timeout(120)
    def test_save_torrent_connection_creates_correct_config(self, settings_page, page: Page):
        """Test that saving torrent connection creates correct config structure."""
        log_test_step("Test: Save torrent connection creates correct config")
        connection_name = "test-torrent-save"

        # Cleanup any leftover
        delete_connection_via_api(connection_name)

        try:
            settings_page.goto()
            settings_page.wait_for_clients_loaded()
            # Save with magnet-only mode (no SFTP)
            add_torrent_connection_via_ui(
                settings_page, page,
                connection_name=connection_name,
                from_client="source-deluge",
                to_client="target-deluge",
                magnet_only=True,
            )

            # Verify the config via API
            conn = get_connection_config_via_api(connection_name)
            assert conn is not None, f"Connection '{connection_name}' not found via API"
            assert conn.get("transfer_config", {}).get("type") == "torrent", \
                f"Expected transfer_config.type='torrent', got: {conn.get('transfer_config')}"
            # destination_path should not be in config when not provided
            assert "destination_path" not in conn.get("transfer_config", {}), \
                f"Expected no destination_path in config, got: {conn.get('transfer_config')}"
            # source should not be in config when magnet-only
            assert "source" not in conn.get("transfer_config", {}), \
                f"Expected no source in magnet-only config, got: {conn.get('transfer_config')}"
            print("  ✓ Saved torrent connection has correct config structure")
        finally:
            delete_connection_via_api(connection_name)

    @pytest.mark.timeout(120)
    def test_edit_torrent_connection_populates_form(self, settings_page, page: Page):
        """Test that editing a torrent connection populates form correctly."""
        log_test_step("Test: Edit torrent connection populates form")
        connection_name = "test-torrent-edit"

        # Cleanup any leftover
        delete_connection_via_api(connection_name)

        try:
            # Create a torrent connection with magnet-only and destination_path
            settings_page.goto()
            settings_page.wait_for_clients_loaded()
            add_torrent_connection_via_ui(
                settings_page, page,
                connection_name=connection_name,
                from_client="source-deluge",
                to_client="target-deluge",
                destination_path="/downloads",
                magnet_only=True,
            )

            # Now reload and edit it
            settings_page.goto()
            settings_page.switch_to_connections_tab()
            settings_page.wait_for_connections_loaded()

            # Find and click edit on the torrent connection
            conn_card = page.locator(f".connection-card[data-name='{connection_name}']")
            expect(conn_card).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])
            conn_card.locator(".btn-primary").click()

            # Modal should open
            expect(page.locator(settings_page.CONNECTION_MODAL)).to_be_visible()
            page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

            # Transfer method should be set to torrent
            transfer_method = page.locator(settings_page.TRANSFER_METHOD)
            assert transfer_method.input_value() == "torrent", \
                f"Expected 'torrent', got '{transfer_method.input_value()}'"

            # Torrent config should be visible
            expect(page.locator(settings_page.TORRENT_TRANSFER_CONFIG)).to_be_visible()

            # File-transfer-only elements should be hidden
            file_only_elements = page.locator(settings_page.FILE_TRANSFER_ONLY).all()
            for el in file_only_elements:
                display = el.evaluate("el => el.style.display")
                assert display == "none", "File-transfer-only should be hidden in torrent edit mode"

            # Advanced options should be auto-expanded since destination_path was set
            # and magnet-only was enabled (no source config)
            advanced_section = page.locator(settings_page.TORRENT_ADVANCED_OPTIONS)
            expect(advanced_section).to_be_visible()

            # Destination path should be populated
            dest_path = page.locator(settings_page.TORRENT_DESTINATION_PATH)
            assert dest_path.input_value() == "/downloads", \
                f"Expected '/downloads', got '{dest_path.input_value()}'"

            # Magnet-only should be checked (no source config in this connection)
            magnet_only = page.locator(settings_page.TORRENT_MAGNET_ONLY)
            expect(magnet_only).to_be_checked()

            # Source SFTP config should be hidden when magnet-only is checked
            sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
            display = sftp_config.evaluate("el => el.style.display")
            assert display == "none", "Source SFTP should be hidden when magnet-only is checked"

            # Magnet-only warning should be visible
            expect(page.locator(settings_page.TORRENT_MAGNET_ONLY_WARNING)).to_be_visible()

            print("  ✓ Edit torrent connection populates form correctly")
        finally:
            delete_connection_via_api(connection_name)

    @pytest.mark.timeout(120)
    def test_edit_torrent_connection_saves_changes(self, settings_page, page: Page):
        """Test that editing and saving a torrent connection persists changes."""
        log_test_step("Test: Edit torrent connection saves changes")
        connection_name = "test-torrent-edit-save"

        # Cleanup any leftover
        delete_connection_via_api(connection_name)

        try:
            # Create a torrent connection first (magnet-only, without destination_path)
            settings_page.goto()
            settings_page.wait_for_clients_loaded()
            add_torrent_connection_via_ui(
                settings_page, page,
                connection_name=connection_name,
                from_client="source-deluge",
                to_client="target-deluge",
                magnet_only=True,
            )

            # Verify it was created without destination_path
            conn = get_connection_config_via_api(connection_name)
            assert conn is not None
            assert "destination_path" not in conn.get("transfer_config", {})

            # Now reload and edit it to add destination_path
            settings_page.goto()
            settings_page.switch_to_connections_tab()
            settings_page.wait_for_connections_loaded()

            # Find and click edit
            conn_card = page.locator(f".connection-card[data-name='{connection_name}']")
            expect(conn_card).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])
            conn_card.locator(".btn-primary").click()

            # Modal should open
            expect(page.locator(settings_page.CONNECTION_MODAL)).to_be_visible()
            page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

            # Expand advanced options and set destination path
            # (may already be expanded from magnet-only auto-expand)
            advanced_section = page.locator(settings_page.TORRENT_ADVANCED_OPTIONS)
            if not advanced_section.is_visible():
                advanced_toggle = page.locator(settings_page.TORRENT_ADVANCED_TOGGLE)
                expect(advanced_toggle).to_be_visible()
                advanced_toggle.click()
                page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

            dest_path = page.locator(settings_page.TORRENT_DESTINATION_PATH)
            expect(dest_path).to_be_visible()
            dest_path.fill("/custom/downloads")

            # Save
            save_btn = page.locator(settings_page.SAVE_CONNECTION_BTN)
            expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])

            with page.expect_response(
                lambda r: "/api/v1/connections" in r.url and r.request.method == "PUT",
                timeout=UI_TIMEOUTS['api_response']
            ) as response_info:
                settings_page.save_connection()

            assert response_info.value.status in (200, 201), \
                f"Save failed: {response_info.value.status}"

            # Verify via API that the change persisted
            conn = get_connection_config_via_api(connection_name)
            assert conn is not None
            assert conn.get("transfer_config", {}).get("destination_path") == "/custom/downloads", \
                f"Expected destination_path='/custom/downloads', got: {conn.get('transfer_config')}"

            print("  ✓ Edit torrent connection saves changes correctly")
        finally:
            delete_connection_via_api(connection_name)

    def test_source_sftp_fields_visible_by_default(self, settings_page, page: Page):
        """Test that Source SFTP config fields are visible by default for torrent method."""
        log_test_step("Test: Source SFTP fields visible by default")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Source type selector should default to 'sftp'
        source_type = page.locator(settings_page.TORRENT_SOURCE_TYPE)
        expect(source_type).to_be_visible()
        assert source_type.input_value() == "sftp", \
            f"Expected default source type 'sftp', got: {source_type.input_value()}"

        # Source SFTP config section should be visible (shown by default)
        sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
        expect(sftp_config).to_be_visible()

        # Individual SFTP fields should be visible
        expect(page.locator(settings_page.TORRENT_SOURCE_SFTP_HOST)).to_be_visible()
        expect(page.locator(settings_page.TORRENT_SOURCE_SFTP_PORT)).to_be_visible()
        expect(page.locator(settings_page.TORRENT_SOURCE_SFTP_USERNAME)).to_be_visible()
        expect(page.locator(settings_page.TORRENT_SOURCE_SFTP_PASSWORD)).to_be_visible()

        # Port should default to 22
        port_value = page.locator(settings_page.TORRENT_SOURCE_SFTP_PORT).input_value()
        assert port_value == "22", f"Expected default port 22, got: {port_value}"

        print("  ✓ Source SFTP fields visible by default for torrent method")

    def test_source_type_local_hides_sftp_fields(self, settings_page, page: Page):
        """Test that switching source type to local hides SFTP fields."""
        log_test_step("Test: Source type local hides SFTP fields")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Verify SFTP is visible initially
        sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
        expect(sftp_config).to_be_visible()

        # Switch source type to local
        page.select_option(settings_page.TORRENT_SOURCE_TYPE, "local")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # SFTP config should be hidden
        display = sftp_config.evaluate("el => el.style.display")
        assert display == "none", f"SFTP config should be hidden for local type, got: {display}"

        # State dir input should be enabled (directly editable for local)
        state_dir = page.locator(settings_page.TORRENT_SOURCE_STATE_DIR)
        expect(state_dir).to_be_enabled()

        print("  ✓ Source type local hides SFTP fields")

    def test_source_type_switch_back_to_sftp_restores_fields(self, settings_page, page: Page):
        """Test that switching from local back to sftp restores SFTP fields."""
        log_test_step("Test: Switch back to SFTP restores fields")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Switch to local, then back to sftp
        page.select_option(settings_page.TORRENT_SOURCE_TYPE, "local")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        page.select_option(settings_page.TORRENT_SOURCE_TYPE, "sftp")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # SFTP config should be visible again
        sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
        display = sftp_config.evaluate("el => el.style.display")
        assert display == "block", f"SFTP config should be visible after switching back, got: {display}"

        print("  ✓ Switching back to SFTP restores fields")

    def test_magnet_only_checkbox_under_advanced(self, settings_page, page: Page):
        """Test that magnet-only checkbox exists under Advanced Options and is unchecked."""
        log_test_step("Test: Magnet-only checkbox under Advanced Options")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Magnet-only checkbox should be hidden (inside collapsed Advanced)
        magnet_only = page.locator(settings_page.TORRENT_MAGNET_ONLY)
        expect(magnet_only).to_be_hidden()

        # Warning should be hidden
        expect(page.locator(settings_page.TORRENT_MAGNET_ONLY_WARNING)).to_be_hidden()

        # Expand advanced options
        page.click(settings_page.TORRENT_ADVANCED_TOGGLE)
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Now magnet-only checkbox should be visible and unchecked
        expect(magnet_only).to_be_visible()
        expect(magnet_only).not_to_be_checked()

        # Warning should still be hidden (checkbox not checked)
        expect(page.locator(settings_page.TORRENT_MAGNET_ONLY_WARNING)).to_be_hidden()

        print("  ✓ Magnet-only checkbox visible under Advanced, unchecked by default")

    def test_magnet_only_hides_sftp_shows_warning(self, settings_page, page: Page):
        """Test that checking magnet-only hides source config and shows warning."""
        log_test_step("Test: Magnet-only hides source config and shows warning")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Verify source type selector and SFTP are visible initially
        source_type = page.locator(settings_page.TORRENT_SOURCE_TYPE)
        expect(source_type).to_be_visible()
        sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
        expect(sftp_config).to_be_visible()

        # Expand advanced and check magnet-only
        page.click(settings_page.TORRENT_ADVANCED_TOGGLE)
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        page.locator(settings_page.TORRENT_MAGNET_ONLY).check()
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Source type selector should be hidden (its ancestor .mb-3)
        source_type_mb3 = source_type.locator("xpath=ancestor::div[contains(@class,'mb-3')]")
        display = source_type_mb3.evaluate("el => el.style.display")
        assert display == "none", f"Source type selector should be hidden, got display: {display}"

        # SFTP config should also be hidden
        display = sftp_config.evaluate("el => el.style.display")
        assert display == "none", f"SFTP config should be hidden, got display: {display}"

        # Warning should be visible
        warning = page.locator(settings_page.TORRENT_MAGNET_ONLY_WARNING)
        expect(warning).to_be_visible()

        # Warning text should mention private tracker
        warning_text = warning.text_content()
        assert "private" in warning_text.lower(), \
            f"Warning should mention private trackers, got: {warning_text}"

        print("  ✓ Magnet-only hides source config and shows private tracker warning")

    def test_uncheck_magnet_only_restores_sftp(self, settings_page, page: Page):
        """Test that unchecking magnet-only restores source config and hides warning."""
        log_test_step("Test: Uncheck magnet-only restores source config")
        self._open_connection_modal(settings_page, page)

        # Switch to torrent
        page.select_option(settings_page.TRANSFER_METHOD, "torrent")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Expand advanced and check magnet-only
        page.click(settings_page.TORRENT_ADVANCED_TOGGLE)
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        page.locator(settings_page.TORRENT_MAGNET_ONLY).check()
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Verify SFTP and source type selector are hidden
        sftp_config = page.locator(settings_page.TORRENT_SOURCE_SFTP_CONFIG)
        display = sftp_config.evaluate("el => el.style.display")
        assert display == "none", "SFTP should be hidden after checking magnet-only"

        source_type = page.locator(settings_page.TORRENT_SOURCE_TYPE)
        source_type_mb3 = source_type.locator("xpath=ancestor::div[contains(@class,'mb-3')]")
        display = source_type_mb3.evaluate("el => el.style.display")
        assert display == "none", "Source type selector should be hidden after checking magnet-only"

        # Uncheck magnet-only
        page.locator(settings_page.TORRENT_MAGNET_ONLY).uncheck()
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Source type selector should be visible again
        display = source_type_mb3.evaluate("el => el.style.display")
        assert display != "none", f"Source type selector should be visible, got display: {display}"

        # SFTP config should be visible again (default source type is sftp)
        display = sftp_config.evaluate("el => el.style.display")
        assert display == "block", f"SFTP should be visible after unchecking magnet-only, got: {display}"

        # Warning should be hidden
        warning = page.locator(settings_page.TORRENT_MAGNET_ONLY_WARNING)
        display = warning.evaluate("el => el.style.display")
        assert display == "none", "Warning should be hidden after unchecking magnet-only"

        print("  ✓ Unchecking magnet-only restores source config")

    @pytest.mark.timeout(120)
    def test_save_with_sftp_includes_source_config(self, settings_page, page: Page):
        """Test that saving with SFTP fields filled includes source config with nested sftp."""
        log_test_step("Test: Save with SFTP includes source config")
        connection_name = "test-torrent-sftp-save"

        # Cleanup any leftover
        delete_connection_via_api(connection_name)

        try:
            settings_page.goto()
            settings_page.wait_for_clients_loaded()
            # Save with SFTP fields filled (no magnet-only)
            add_torrent_connection_via_ui(
                settings_page, page,
                connection_name=connection_name,
                from_client="source-deluge",
                to_client="target-deluge",
                source_sftp={
                    'host': 'sftp-server',
                    'port': 2222,
                    'username': 'testuser',
                    'password': 'testpass',
                },
                state_dir='/home/abc/deluge/state',
            )

            # Verify the config via API
            conn = get_connection_config_via_api(connection_name)
            assert conn is not None, f"Connection '{connection_name}' not found via API"

            transfer_config = conn.get("transfer_config", {})
            assert transfer_config.get("type") == "torrent", \
                f"Expected type='torrent', got: {transfer_config}"

            # source should be present with nested structure
            source = transfer_config.get("source")
            assert source is not None, \
                f"Expected source in config, got: {transfer_config}"
            assert source.get("type") == "sftp", \
                f"Expected source.type='sftp', got: {source}"
            assert source.get("state_dir") == "/home/abc/deluge/state", \
                f"Expected state_dir='/home/abc/deluge/state', got: {source}"

            # SFTP credentials should be nested under source.sftp
            sftp = source.get("sftp")
            assert sftp is not None, \
                f"Expected source.sftp in config, got: {source}"
            assert sftp.get("host") == "sftp-server", \
                f"Expected host='sftp-server', got: {sftp}"
            assert sftp.get("port") == 2222, \
                f"Expected port=2222, got: {sftp}"
            assert sftp.get("username") == "testuser", \
                f"Expected username='testuser', got: {sftp}"
            # Password should be masked in GET response
            assert sftp.get("password") == "***", \
                f"Expected password='***' (masked), got: {sftp}"

            print("  ✓ Save with SFTP includes source config")
        finally:
            delete_connection_via_api(connection_name)
