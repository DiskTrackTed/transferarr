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