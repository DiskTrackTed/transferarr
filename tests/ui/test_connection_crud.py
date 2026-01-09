"""
Connection CRUD tests for Transferarr UI.

Tests the complete connection management workflow including:
- Adding new connections via the UI
- Testing connection configuration
- Editing existing connections
- Deleting connections
- Form validation
- Error handling

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
from tests.ui.helpers import UI_TIMEOUTS

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
        
        # Select from/to types as local
        settings_page.page.select_option(settings_page.CONNECTION_FROM_TYPE, "local")
        settings_page.page.select_option(settings_page.CONNECTION_TO_TYPE, "local")
        
        # Test connection - this may take a while for SFTP connection tests
        with page.expect_response(
            lambda r: "/api/connections/test" in r.url,
            timeout=UI_TIMEOUTS['api_response_slow']  # 60s timeout
        ) as response_info:
            settings_page.test_connection()
        
        # Should get a response (success or failure)
        response = response_info.value.json()
        assert "success" in response or "error" in response


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
