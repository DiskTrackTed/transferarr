"""
UI tests for different transfer type combinations.

Tests that the UI correctly handles adding connections with all 4 transfer type
combinations:
- local -> local
- local -> sftp
- sftp -> local  
- sftp -> sftp

These tests verify the connection modal form works correctly for each combination,
including proper SFTP config field handling.
"""
import json
import pytest
from playwright.sync_api import Page, expect

from tests.conftest import TRANSFER_TYPE_CONFIGS
from tests.ui.helpers import (
    UI_TIMEOUTS,
    add_connection_via_ui,
    delete_connection_via_api,
    log_test_step,
)


def load_transfer_config(config_type: str) -> dict:
    """Load a transfer config from the fixtures directory.
    
    Args:
        config_type: One of 'local-to-local', 'local-to-sftp', 'sftp-to-local', 'sftp-to-sftp'
        
    Returns:
        Dict with from_config, to_config, and paths extracted from the fixture.
        The from_config and to_config are the raw transfer_config dicts that can
        be passed directly to add_connection_via_ui.
    """
    config_path = TRANSFER_TYPE_CONFIGS[config_type]
    with open(config_path) as f:
        raw_config = json.load(f)
    
    # Get the first (and typically only) connection config
    connection = list(raw_config['connections'].values())[0]
    
    return {
        'from_config': connection['transfer_config']['from'],
        'to_config': connection['transfer_config']['to'],
        'paths': {
            'source_dot_torrent_path': connection['source_dot_torrent_path'],
            'source_torrent_download_path': connection['source_torrent_download_path'],
            'destination_dot_torrent_tmp_dir': connection['destination_dot_torrent_tmp_dir'],
            'destination_torrent_download_path': connection['destination_torrent_download_path'],
        }
    }


class TestTransferTypeCombinations:
    """
    Test all 4 transfer type combinations via the UI.
    
    These tests verify that:
    1. The connection modal correctly shows/hides SFTP fields based on type selection
    2. Test connection works for each combination
    3. Connections can be saved successfully
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        # Use sftp-to-sftp config as base since it has all SFTP credentials
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True, config_type='sftp-to-sftp')
        self.transferarr = transferarr
    
    @pytest.mark.timeout(120)
    def test_local_to_local_connection(self, settings_page, page: Page):
        """Test adding a local -> local connection via UI."""
        log_test_step("Test: local -> local connection")
        config = load_transfer_config('local-to-local')
        connection_name = "test-local-to-local"
        
        # Clean up any existing connection with this name
        delete_connection_via_api(connection_name)
        
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        add_connection_via_ui(
            settings_page, page,
            connection_name=connection_name,
            from_client="source-deluge",
            to_client="target-deluge",
            from_config=config['from_config'],
            to_config=config['to_config'],
            paths=config['paths'],
        )
        
        print("  ✓ local -> local connection added successfully")
        
        # Clean up
        delete_connection_via_api(connection_name)
    
    @pytest.mark.timeout(120)
    def test_local_to_sftp_connection(self, settings_page, page: Page):
        """Test adding a local -> sftp connection via UI."""
        log_test_step("Test: local -> sftp connection")
        config = load_transfer_config('local-to-sftp')
        connection_name = "test-local-to-sftp"
        
        # Clean up any existing connection with this name
        delete_connection_via_api(connection_name)
        
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        add_connection_via_ui(
            settings_page, page,
            connection_name=connection_name,
            from_client="source-deluge",
            to_client="target-deluge",
            from_config=config['from_config'],
            to_config=config['to_config'],
            paths=config['paths'],
        )
        
        print("  ✓ local -> sftp connection added successfully")
        
        # Clean up
        delete_connection_via_api(connection_name)
    
    @pytest.mark.timeout(120)
    def test_sftp_to_local_connection(self, settings_page, page: Page):
        """Test adding a sftp -> local connection via UI."""
        log_test_step("Test: sftp -> local connection")
        config = load_transfer_config('sftp-to-local')
        connection_name = "test-sftp-to-local"
        
        # Clean up any existing connection with this name
        delete_connection_via_api(connection_name)
        
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        add_connection_via_ui(
            settings_page, page,
            connection_name=connection_name,
            from_client="source-deluge",
            to_client="target-deluge",
            from_config=config['from_config'],
            to_config=config['to_config'],
            paths=config['paths'],
        )
        
        print("  ✓ sftp -> local connection added successfully")
        
        # Clean up
        delete_connection_via_api(connection_name)
    
    @pytest.mark.timeout(120)
    def test_sftp_to_sftp_connection(self, settings_page, page: Page):
        """Test adding a sftp -> sftp connection via UI."""
        log_test_step("Test: sftp -> sftp connection")
        config = load_transfer_config('sftp-to-sftp')
        connection_name = "test-sftp-to-sftp"
        
        # Clean up any existing connection with this name
        delete_connection_via_api(connection_name)
        
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        add_connection_via_ui(
            settings_page, page,
            connection_name=connection_name,
            from_client="source-deluge",
            to_client="target-deluge",
            from_config=config['from_config'],
            to_config=config['to_config'],
            paths=config['paths'],
        )
        
        print("  ✓ sftp -> sftp connection added successfully")
        
        # Clean up
        delete_connection_via_api(connection_name)


class TestSftpFieldVisibility:
    """Test that SFTP config fields show/hide correctly based on type selection."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        self.transferarr = transferarr
    
    @pytest.mark.timeout(60)
    def test_sftp_fields_hidden_for_local_type(self, settings_page, page: Page):
        """Verify SFTP fields are hidden when type is 'local'."""
        log_test_step("Test: SFTP fields hidden for local type")
        
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        
        # Wait for modal to fully load
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        
        # Select local for both types
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'local')
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'local')
        page.wait_for_timeout(300)  # Wait for JS to process
        
        # Check that SFTP config containers are hidden
        from_sftp_container = page.locator("#fromSftpConfig")
        to_sftp_container = page.locator("#toSftpConfig")
        
        expect(from_sftp_container).to_be_hidden()
        expect(to_sftp_container).to_be_hidden()
        
        print("  ✓ SFTP fields correctly hidden for local type")
    
    @pytest.mark.timeout(60)
    def test_from_sftp_fields_visible_for_sftp_type(self, settings_page, page: Page):
        """Verify source SFTP fields are visible when from type is 'sftp'."""
        log_test_step("Test: Source SFTP fields visible for sftp type")
        
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        
        # Select sftp for source, local for target
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'sftp')
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'local')
        page.wait_for_timeout(300)
        
        # Check visibility
        from_sftp_container = page.locator("#fromSftpConfig")
        to_sftp_container = page.locator("#toSftpConfig")
        
        expect(from_sftp_container).to_be_visible()
        expect(to_sftp_container).to_be_hidden()
        
        # Verify individual fields are present
        expect(page.locator(settings_page.FROM_SFTP_HOST)).to_be_visible()
        expect(page.locator(settings_page.FROM_SFTP_PORT)).to_be_visible()
        expect(page.locator(settings_page.FROM_SFTP_USERNAME)).to_be_visible()
        expect(page.locator(settings_page.FROM_SFTP_PASSWORD)).to_be_visible()
        
        print("  ✓ Source SFTP fields correctly visible for sftp type")
    
    @pytest.mark.timeout(60)
    def test_to_sftp_fields_visible_for_sftp_type(self, settings_page, page: Page):
        """Verify target SFTP fields are visible when to type is 'sftp'."""
        log_test_step("Test: Target SFTP fields visible for sftp type")
        
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        
        # Select local for source, sftp for target
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'local')
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'sftp')
        page.wait_for_timeout(300)
        
        # Check visibility
        from_sftp_container = page.locator("#fromSftpConfig")
        to_sftp_container = page.locator("#toSftpConfig")
        
        expect(from_sftp_container).to_be_hidden()
        expect(to_sftp_container).to_be_visible()
        
        # Verify individual fields are present
        expect(page.locator(settings_page.TO_SFTP_HOST)).to_be_visible()
        expect(page.locator(settings_page.TO_SFTP_PORT)).to_be_visible()
        expect(page.locator(settings_page.TO_SFTP_USERNAME)).to_be_visible()
        expect(page.locator(settings_page.TO_SFTP_PASSWORD)).to_be_visible()
        
        print("  ✓ Target SFTP fields correctly visible for sftp type")
    
    @pytest.mark.timeout(60)
    def test_both_sftp_fields_visible_for_sftp_to_sftp(self, settings_page, page: Page):
        """Verify both SFTP field sets are visible for sftp -> sftp."""
        log_test_step("Test: Both SFTP fields visible for sftp -> sftp")
        
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        
        # Select sftp for both
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'sftp')
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'sftp')
        page.wait_for_timeout(300)
        
        # Check visibility
        from_sftp_container = page.locator("#fromSftpConfig")
        to_sftp_container = page.locator("#toSftpConfig")
        
        expect(from_sftp_container).to_be_visible()
        expect(to_sftp_container).to_be_visible()
        
        print("  ✓ Both SFTP field sets correctly visible for sftp -> sftp")
    
    @pytest.mark.timeout(60)
    def test_sftp_fields_toggle_on_type_change(self, settings_page, page: Page):
        """Verify SFTP fields toggle correctly when type is changed."""
        log_test_step("Test: SFTP fields toggle on type change")
        
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        settings_page.open_add_connection_modal()
        
        page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])
        
        from_sftp_container = page.locator("#fromSftpConfig")
        to_sftp_container = page.locator("#toSftpConfig")
        
        # Start with local -> local (both hidden)
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'local')
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'local')
        page.wait_for_timeout(300)
        
        expect(from_sftp_container).to_be_hidden()
        expect(to_sftp_container).to_be_hidden()
        print("  Step 1: local -> local - both hidden ✓")
        
        # Change from to sftp
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'sftp')
        page.wait_for_timeout(300)
        
        expect(from_sftp_container).to_be_visible()
        expect(to_sftp_container).to_be_hidden()
        print("  Step 2: sftp -> local - from visible, to hidden ✓")
        
        # Change to to sftp
        page.select_option(settings_page.CONNECTION_TO_TYPE, 'sftp')
        page.wait_for_timeout(300)
        
        expect(from_sftp_container).to_be_visible()
        expect(to_sftp_container).to_be_visible()
        print("  Step 3: sftp -> sftp - both visible ✓")
        
        # Change from back to local
        page.select_option(settings_page.CONNECTION_FROM_TYPE, 'local')
        page.wait_for_timeout(300)
        
        expect(from_sftp_container).to_be_hidden()
        expect(to_sftp_container).to_be_visible()
        print("  Step 4: local -> sftp - from hidden, to visible ✓")
        
        print("  ✓ SFTP fields toggle correctly on type change")
