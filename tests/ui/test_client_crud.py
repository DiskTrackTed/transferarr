"""
Client CRUD tests for Transferarr UI.

Tests the complete client management workflow including:
- Adding new clients via the UI
- Testing client connections
- Editing existing clients
- Deleting clients
- Form validation
- Error handling

Note: Tests that add clients will clean them up afterwards via the API
to avoid polluting the config for other tests.
"""
import logging
import pytest
from playwright.sync_api import Page, expect

# Import test configuration and helpers
from tests.conftest import SERVICES, DELUGE_PASSWORD, DELUGE_RPC_USERNAME
from tests.ui.helpers import (
    delete_client_via_api,
    generate_unique_name,
    UI_TIMEOUTS,
)

logger = logging.getLogger(__name__)


class TestAddClient:
    """Tests for adding new download clients."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        self._created_clients = []
        yield
        # Cleanup: delete any clients created during test
        for client_name in self._created_clients:
            delete_client_via_api(client_name)
    
    def test_add_client_form_validation_required_fields(self, settings_page):
        """Test that form requires all mandatory fields."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Save button should be disabled initially (need to test connection first)
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_disabled()
    
    def test_add_client_successfully(self, settings_page, page: Page):
        """Test adding a new download client via UI."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        initial_count = settings_page.get_client_count()
        
        # Use a unique name to avoid conflicts
        unique_name = generate_unique_name("ui-test-client")
        self._created_clients.append(unique_name)  # Track for cleanup
        logger.info(f"Creating test client: {unique_name}")
        
        # Open modal and fill form
        settings_page.open_add_client_modal()
        settings_page.fill_client_form(
            name=unique_name,
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection first (required to enable save)
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            settings_page.test_client_connection()
        
        # Wait for test to complete and check response
        test_response = response_info.value.json()
        assert test_response.get("success") is True, f"Connection test failed: {test_response}"
        
        # Save button should be enabled after successful test
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        # Save the client
        with page.expect_response(
            lambda r: "/api/download_clients" in r.url and r.request.method == "POST",
            timeout=UI_TIMEOUTS['element_visible']
        ) as save_response_info:
            settings_page.save_client()
        
        # Verify API response
        save_response = save_response_info.value
        if save_response.status != 200:
            error_body = save_response.json()
            pytest.fail(f"API returned {save_response.status}: {error_body}")
        
        # Modal should close
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
        
        # Wait for clients list to reload
        settings_page.wait_for_clients_loaded()
        
        # New client should appear
        new_count = settings_page.get_client_count()
        assert new_count == initial_count + 1
        
        # Verify the client card is visible
        expect(
            settings_page.page.locator(f"{settings_page.CLIENT_CARD}:has-text('{unique_name}')")
        ).to_be_visible()
    
    def test_add_duplicate_client_shows_error(self, settings_page, page: Page):
        """Test that adding a client with existing name shows error."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        # First, create a client that we'll try to duplicate
        unique_name = generate_unique_name("duplicate-test")
        self._created_clients.append(unique_name)  # Track for cleanup
        
        settings_page.open_add_client_modal()
        settings_page.fill_client_form(
            name=unique_name,
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test and save the first client
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.test_client_connection()
        
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        with page.expect_response(
            lambda r: "/api/download_clients" in r.url and r.request.method == "POST",
            timeout=UI_TIMEOUTS['element_visible']
        ):
            settings_page.save_client()
        
        # Wait for modal to close and list to reload
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
        settings_page.wait_for_clients_loaded()
        
        # Now try to add another client with the same name
        settings_page.open_add_client_modal()
        settings_page.fill_client_form(
            name=unique_name,  # Same name - should fail
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.test_client_connection()
        
        # Wait for save button to be enabled
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        # Try to save - should return 409 Conflict
        with page.expect_response(
            lambda r: "/api/download_clients" in r.url and r.request.method == "POST",
            timeout=UI_TIMEOUTS['element_visible']
        ) as response_info:
            settings_page.save_client()
        
        response = response_info.value
        assert response.status == 409, f"Expected 409 Conflict, got {response.status}"


class TestTestConnection:
    """Tests for the Test Connection functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_connection_success_with_valid_credentials(self, settings_page, page: Page):
        """Test that valid credentials show success."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Fill with valid credentials for source Deluge
        settings_page.fill_client_form(
            name="test-valid-connection",
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            settings_page.test_client_connection()
        
        response = response_info.value.json()
        assert response.get("success") is True
    
    def test_connection_failure_with_wrong_port(self, settings_page, page: Page):
        """Test that wrong port shows connection failure."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Fill with valid host but wrong port - connection refused is fast
        settings_page.fill_client_form(
            name="test-invalid-connection",
            host=SERVICES['deluge_source']['host'],
            port=59999,  # Wrong port - connection refused
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection - connection refused should be fast
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            settings_page.test_client_connection()
        
        response = response_info.value.json()
        assert response.get("success") is False
    
    def test_connection_failure_with_wrong_password(self, settings_page, page: Page):
        """Test that wrong password shows failure."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Fill with wrong password
        settings_page.fill_client_form(
            name="test-wrong-password",
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password="wrong-password",
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection
        with page.expect_response(
            lambda r: "/api/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            settings_page.test_client_connection()
        
        response = response_info.value.json()
        assert response.get("success") is False


class TestEditClient:
    """Tests for editing existing download clients."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_edit_client_modal_populates_existing_values(self, settings_page):
        """Test that edit modal shows existing client values."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        # Get first client
        clients = settings_page.get_client_cards()
        if len(clients) == 0:
            pytest.skip("No existing clients to edit")
        
        # Get client name from card
        first_card = clients[0]
        client_name_elem = first_card.locator(".card-header")
        client_name = client_name_elem.text_content().strip()
        
        # Click edit button
        settings_page.edit_client(client_name)
        
        # Modal should open
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).to_be_visible()
        
        # Name field should have the client name
        name_input = settings_page.page.locator(settings_page.CLIENT_NAME_INPUT)
        expect(name_input).to_have_value(client_name)
        
        # Host field should be populated
        host_input = settings_page.page.locator(settings_page.CLIENT_HOST_INPUT)
        expect(host_input).not_to_have_value("")
    
    def test_edit_client_changes_saved(self, settings_page, page: Page):
        """Test that editing a client saves changes."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        # Get first client
        clients = settings_page.get_client_cards()
        if len(clients) == 0:
            pytest.skip("No existing clients to edit")
        
        first_card = clients[0]
        client_name = first_card.locator(".card-header").text_content().strip()
        
        # Edit the client
        settings_page.edit_client(client_name)
        
        # Change the port slightly
        port_input = settings_page.page.locator(settings_page.CLIENT_PORT_INPUT)
        current_port = port_input.input_value()
        new_port = int(current_port) if current_port else 58846
        
        # Clear and re-fill port (triggers change detection)
        port_input.clear()
        port_input.fill(str(new_port))
        
        # Close modal without saving to reset state
        settings_page.close_client_modal()


class TestDeleteClient:
    """Tests for deleting download clients."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_delete_confirmation_modal_shows(self, settings_page):
        """Test that delete shows confirmation modal."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        clients = settings_page.get_client_cards()
        if len(clients) == 0:
            pytest.skip("No existing clients to delete")
        
        # Get client name
        first_card = clients[0]
        client_name = first_card.locator(".card-header").text_content().strip()
        
        # Click delete button
        first_card.locator(".btn-danger").click()
        
        # Confirmation modal should appear
        expect(settings_page.page.locator(settings_page.DELETE_MODAL)).to_be_visible()
        
        # Client name should be shown in confirmation
        expect(
            settings_page.page.locator(settings_page.DELETE_CLIENT_NAME)
        ).to_have_text(client_name)
        
        # Cancel to avoid deleting - use the page object method
        settings_page.close_delete_modal()
    
    def test_cancel_delete_keeps_client(self, settings_page):
        """Test that canceling delete keeps the client."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        initial_count = settings_page.get_client_count()
        if initial_count == 0:
            pytest.skip("No existing clients to test delete cancel")
        
        clients = settings_page.get_client_cards()
        first_card = clients[0]
        
        # Click delete
        first_card.locator(".btn-danger").click()
        
        # Cancel using page object method
        settings_page.close_delete_modal()
        
        # Count should be unchanged
        assert settings_page.get_client_count() == initial_count


class TestClientFormInteractions:
    """Tests for client form interactions and UX."""
    
    @pytest.fixture(autouse=True)
    def setup(self, crud_test_setup):
        """Setup clean environment with running transferarr."""
        pass
    
    def test_connection_type_toggles_username_field(self, settings_page):
        """Test that Web connection type hides username field."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        username_field = settings_page.page.locator("#usernameField")
        connection_type_select = settings_page.page.locator(settings_page.CLIENT_CONNECTION_TYPE_SELECT)
        
        # Select Web - username should be hidden
        connection_type_select.select_option("web")
        expect(username_field).to_be_hidden()
        
        # Select RPC - username should be visible
        connection_type_select.select_option("rpc")
        expect(username_field).to_be_visible()
    
    def test_modal_close_button_works(self, settings_page):
        """Test that modal close button works."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Modal should be visible
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).to_be_visible()
        
        # Close it
        settings_page.close_client_modal()
        
        # Modal should be hidden
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
    
    def test_form_changes_disable_save_button(self, settings_page, page: Page):
        """Test that changing form fields requires re-testing connection."""
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        settings_page.open_add_client_modal()
        
        # Fill form
        settings_page.fill_client_form(
            name="test-form-changes",
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection
        with page.expect_response(lambda r: "/api/download_clients/test" in r.url):
            settings_page.test_client_connection()
        
        # Save button should be enabled after successful test
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        # Change a form field
        host_input = settings_page.page.locator(settings_page.CLIENT_HOST_INPUT)
        host_input.fill("different-host")
        
        # Save button should be disabled after change
        expect(save_btn).to_be_disabled()
