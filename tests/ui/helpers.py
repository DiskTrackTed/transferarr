"""
UI Test helper functions and utilities.

This module provides common utilities for UI tests including:
- API interaction helpers
- Logging utilities
- Common test patterns
- Cleanup functions
"""
import logging
import requests

# Import test configuration
from tests.conftest import SERVICES

# Configure logging for UI tests
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create console handler if not already present
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# =============================================================================
# Constants
# =============================================================================

# Build transferarr URL from service config
TRANSFERARR_BASE_URL = f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}"

# Standard timeouts for UI operations (in milliseconds)
UI_TIMEOUTS = {
    'page_load': 10000,
    'api_response': 15000,
    'api_response_slow': 60000,  # For operations that may take longer (SFTP, etc.)
    'element_visible': 5000,
    'modal_animation': 500,
    'dropdown_load': 1000,  # Time for dropdown options to populate
    'js_processing': 500,   # Time for JS to process hash/state changes
}


# =============================================================================
# API Cleanup Functions
# =============================================================================

def delete_client_via_api(client_name: str) -> bool:
    """Delete a client directly via API for cleanup.
    
    Args:
        client_name: Name of the client to delete
        
    Returns:
        True if deleted successfully or client didn't exist, False on error
    """
    try:
        response = requests.delete(
            f"{TRANSFERARR_BASE_URL}/api/v1/download_clients/{client_name}",
            timeout=10
        )
        success = response.status_code in [200, 404]
        if success:
            logger.debug(f"Cleaned up client '{client_name}' (status: {response.status_code})")
        else:
            logger.warning(f"Failed to clean up client '{client_name}' (status: {response.status_code})")
        return success
    except Exception as e:
        logger.error(f"Exception cleaning up client '{client_name}': {e}")
        return False


# =============================================================================
# API Response Helpers  
# =============================================================================

def unwrap_api_response(response_json: dict) -> dict:
    """Unwrap data from the API response envelope.
    
    Phase 3 API responses use the format: {"data": {...}, "message": "..."}
    This helper extracts the data or returns the response as-is for compatibility.
    
    Args:
        response_json: The JSON response from the API
        
    Returns:
        The unwrapped data dict, or original response if no envelope
    """
    if "data" in response_json:
        return response_json["data"]
    return response_json


# Note: Playwright's expect_response() is used directly in tests as it provides
# better context manager syntax. These helpers were removed as unused.


# =============================================================================
# Connection Form Helpers
# =============================================================================

def _fill_transfer_type_config(page, settings_page, transfer_config: dict, prefix: str):
    """Fill transfer type-specific config fields in the connection modal.
    
    This is an internal helper that handles filling fields for different transfer
    types (local, sftp, and future types like rclone, s3, etc.).
    
    Args:
        page: Playwright Page
        settings_page: SettingsPage object with field selectors
        transfer_config: The transfer config dict, e.g. {"type": "sftp", "sftp": {...}}
        prefix: 'from' or 'to' to determine which fields to fill
    """
    transfer_type = transfer_config.get('type', 'local')
    
    if transfer_type == 'sftp':
        sftp_config = transfer_config.get('sftp', {})
        if prefix == 'from':
            page.fill(settings_page.FROM_SFTP_HOST, sftp_config.get('host', ''))
            page.fill(settings_page.FROM_SFTP_PORT, str(sftp_config.get('port', 22)))
            page.fill(settings_page.FROM_SFTP_USERNAME, sftp_config.get('username', ''))
            page.fill(settings_page.FROM_SFTP_PASSWORD, sftp_config.get('password', ''))
        else:  # 'to'
            page.fill(settings_page.TO_SFTP_HOST, sftp_config.get('host', ''))
            page.fill(settings_page.TO_SFTP_PORT, str(sftp_config.get('port', 22)))
            page.fill(settings_page.TO_SFTP_USERNAME, sftp_config.get('username', ''))
            page.fill(settings_page.TO_SFTP_PASSWORD, sftp_config.get('password', ''))
    
    # Future transfer types can be added here:
    # elif transfer_type == 'rclone':
    #     rclone_config = transfer_config.get('rclone', {})
    #     ...


def add_connection_via_ui(
    settings_page,
    page,
    connection_name: str,
    from_client: str,
    to_client: str,
    from_config: dict,
    to_config: dict,
    paths: dict,
):
    """Add a connection via the UI.
    
    This helper fills out the connection modal form, tests the connection,
    fills in paths, and saves the connection.
    
    Args:
        settings_page: SettingsPage object
        page: Playwright Page
        connection_name: Name for the connection
        from_client: Source client name
        to_client: Target client name
        from_config: Source transfer config dict, e.g. {"type": "sftp", "sftp": {...}}
        to_config: Target transfer config dict, e.g. {"type": "local"}
        paths: Dict with source_dot_torrent_path, source_torrent_download_path,
               destination_dot_torrent_tmp_dir, destination_torrent_download_path
        
    Raises:
        AssertionError: If connection test fails or save fails
    """
    from playwright.sync_api import expect
    
    settings_page.switch_to_connections_tab()
    settings_page.wait_for_connections_loaded()
    settings_page.open_add_connection_modal()
    
    # Wait for client dropdowns to populate
    page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])
    
    # Fill connection name
    page.fill(settings_page.CONNECTION_NAME, connection_name)
    
    # Select clients
    page.select_option(settings_page.CONNECTION_FROM_SELECT, from_client)
    page.select_option(settings_page.CONNECTION_TO_SELECT, to_client)
    
    # Select transfer types
    from_type = from_config.get('type', 'local')
    to_type = to_config.get('type', 'local')
    page.select_option(settings_page.CONNECTION_FROM_TYPE, from_type)
    page.select_option(settings_page.CONNECTION_TO_TYPE, to_type)
    
    # Wait for JS change events to process
    page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
    
    # Fill type-specific config fields
    _fill_transfer_type_config(page, settings_page, from_config, 'from')
    _fill_transfer_type_config(page, settings_page, to_config, 'to')
    
    # Test connection
    with page.expect_response(
        lambda r: "/api/v1/connections/test" in r.url,
        timeout=UI_TIMEOUTS['api_response_slow']
    ) as response_info:
        settings_page.test_connection()
    
    test_response = response_info.value.json()
    test_result = test_response.get('data', test_response) if isinstance(test_response, dict) and 'data' in test_response else test_response
    assert test_result.get("success"), f"Connection test failed: {test_response}"
    logger.debug("Connection test passed")
    
    # After successful test, path fields should be enabled
    # Use JS injection to fill paths (faster and more reliable)
    page.evaluate(f"""
        document.getElementById('sourceDotTorrentPath').value = '{paths['source_dot_torrent_path']}';
        document.getElementById('sourceTorrentDownloadPath').value = '{paths['source_torrent_download_path']}';
        document.getElementById('destinationDotTorrentTmpDir').value = '{paths['destination_dot_torrent_tmp_dir']}';
        document.getElementById('destinationTorrentDownloadPath').value = '{paths['destination_torrent_download_path']}';
        
        // Trigger input events so form validation picks up the values
        ['sourceDotTorrentPath', 'sourceTorrentDownloadPath', 'destinationDotTorrentTmpDir', 'destinationTorrentDownloadPath'].forEach(id => {{
            const el = document.getElementById(id);
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }});
    """)
    
    # Save button should be enabled
    save_btn = page.locator(settings_page.SAVE_CONNECTION_BTN)
    expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
    
    # Save connection and verify success
    with page.expect_response(
        lambda r: "/api/v1/connections" in r.url and r.request.method == "POST",
        timeout=UI_TIMEOUTS['api_response']
    ) as response_info:
        settings_page.save_connection()
    
    save_response = response_info.value
    assert save_response.status in (200, 201), f"Save connection failed: {save_response.status}"
    
    expect(page.locator(settings_page.CONNECTION_MODAL)).not_to_be_visible()
    settings_page.wait_for_connections_loaded()
    
    # Wait for connection card to appear
    page.wait_for_selector(settings_page.CONNECTION_CARD, timeout=UI_TIMEOUTS['api_response'])
    logger.debug(f"Added connection: {connection_name}")


def delete_connection_via_api(connection_name: str) -> bool:
    """Delete a connection directly via API for cleanup.
    
    Args:
        connection_name: Name of the connection to delete
        
    Returns:
        True if deleted successfully or connection didn't exist, False on error
    """
    from urllib.parse import quote
    
    try:
        encoded_name = quote(connection_name, safe='')
        response = requests.delete(
            f"{TRANSFERARR_BASE_URL}/api/v1/connections/{encoded_name}",
            timeout=10
        )
        success = response.status_code in [200, 404]
        if success:
            logger.debug(f"Cleaned up connection '{connection_name}' (status: {response.status_code})")
        else:
            logger.warning(f"Failed to clean up connection '{connection_name}' (status: {response.status_code})")
        return success
    except Exception as e:
        logger.error(f"Exception cleaning up connection '{connection_name}': {e}")
        return False


# =============================================================================
# Test Data Generation
# =============================================================================

def generate_unique_name(prefix: str) -> str:
    """Generate a unique name for test resources.
    
    Args:
        prefix: Prefix for the name (e.g., "ui-test-client")
        
    Returns:
        Unique name with timestamp suffix
    """
    import time
    return f"{prefix}-{int(time.time())}"


# =============================================================================
# Logging Helpers
# =============================================================================

def log_test_step(step: str) -> None:
    """Log a test step for debugging.
    
    Args:
        step: Description of the test step
    """
    logger.info(f"TEST STEP: {step}")