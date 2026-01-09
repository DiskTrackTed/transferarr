"""
Pytest configuration and fixtures for UI tests.

These tests use Playwright for browser automation and require
the test environment to be running (docker compose up).

This module uses pytest-playwright's built-in fixtures (browser, context, page)
which automatically handle:
- Screenshot capture on failure (--screenshot=on/only-on-failure)
- Video recording (--video=on/retain-on-failure)
- Trace capture (--tracing=on/retain-on-failure)
- Headed/headless mode (--headed)

Artifacts are saved to the --output directory (default: test-results/).
"""
import pytest
from playwright.sync_api import Page, Browser, BrowserContext

# Import from main conftest
from tests.conftest import SERVICES, TIMEOUTS
from tests.ui.helpers import TRANSFERARR_BASE_URL


# ==============================================================================
# URL Fixture (overrides pytest-playwright's base_url)
# ==============================================================================

@pytest.fixture(scope="session")
def base_url() -> str:
    """Return the base URL for transferarr.
    
    This overrides pytest-playwright's base_url fixture to point to
    our test environment's transferarr instance.
    
    Session-scoped to be compatible with pytest-playwright internals.
    """
    return TRANSFERARR_BASE_URL


# ==============================================================================
# Browser Configuration
# ==============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Configure browser context with consistent viewport.
    
    This extends pytest-playwright's browser_context_args fixture to ensure
    all tests run with the same viewport size for consistent screenshots.
    
    Args:
        browser_context_args: Base args from pytest-playwright
        
    Returns:
        Updated args dict with viewport configuration
    """
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
    }


# ==============================================================================
# Page Object Fixtures
# ==============================================================================

@pytest.fixture
def dashboard_page(page: Page, base_url: str) -> "DashboardPage":
    """Create a DashboardPage instance.
    
    Uses pytest-playwright's page fixture which handles screenshots.
    """
    from tests.ui.pages.dashboard_page import DashboardPage
    return DashboardPage(page, base_url)


@pytest.fixture
def torrents_page(page: Page, base_url: str) -> "TorrentsPage":
    """Create a TorrentsPage instance.
    
    Uses pytest-playwright's page fixture which handles screenshots.
    """
    from tests.ui.pages.torrents_page import TorrentsPage
    return TorrentsPage(page, base_url)


@pytest.fixture
def settings_page(page: Page, base_url: str) -> "SettingsPage":
    """Create a SettingsPage instance.
    
    Uses pytest-playwright's page fixture which handles screenshots.
    """
    from tests.ui.pages.settings_page import SettingsPage
    return SettingsPage(page, base_url)


# ==============================================================================
# Utility Fixtures
# ==============================================================================

@pytest.fixture
def crud_test_setup(clean_test_environment, transferarr):
    """Common setup for CRUD tests that need a running transferarr.
    
    This fixture:
    1. Uses clean_test_environment to reset state
    2. Starts transferarr and waits for it to be healthy
    
    Use this in CRUD test classes to reduce fixture duplication.
    
    Example:
        class TestSomeCRUD:
            @pytest.fixture(autouse=True)
            def setup(self, crud_test_setup):
                pass
    """
    transferarr.start(wait_healthy=True)
    yield transferarr
    # transferarr cleanup is handled by the fixture itself