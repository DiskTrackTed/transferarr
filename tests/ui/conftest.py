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
# Transfer History Setup Fixture (for delete tests)
# ==============================================================================

@pytest.fixture(scope="module")
def transfer_history_data(
    docker_client,
    docker_services,
    radarr_api_key,
    sonarr_api_key,
    radarr_client,
    sonarr_client,
    deluge_source,
    deluge_target,
    create_torrent
):
    """Run a transfer to create organic history data for UI tests.
    
    This module-scoped fixture runs ONE transfer before any test in the module
    that requests it, ensuring history data exists for testing delete functionality.
    
    Only used by tests that need history data (e.g., TestHistoryDeleteFeatures).
    """
    from tests.integration.helpers import LifecycleRunner
    from tests.utils import clear_radarr_state, clear_sonarr_state, clear_deluge_torrents, clear_mock_indexer_torrents
    import requests
    import time
    
    # Import TransferarrManager logic inline since we can't use the fixture
    class TransferarrManager:
        def __init__(self, docker_client, radarr_key, sonarr_key):
            self.docker = docker_client
            self.container_name = "test-transferarr"
            self.radarr_api_key = radarr_key
            self.sonarr_api_key = sonarr_key
        
        def is_running(self) -> bool:
            try:
                container = self.docker.containers.get(self.container_name)
                return container.status == "running"
            except:
                return False
        
        def start(self, wait_healthy=True):
            try:
                container = self.docker.containers.get(self.container_name)
                if container.status != "running":
                    container.start()
            except:
                pytest.fail("Transferarr container not found")
            if wait_healthy:
                self.wait_healthy()
        
        def stop(self):
            try:
                container = self.docker.containers.get(self.container_name)
                container.stop()
            except:
                pass
        
        def wait_healthy(self, timeout=60):
            import time
            deadline = time.time() + timeout
            url = f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/health"
            while time.time() < deadline:
                try:
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        return True
                except:
                    pass
                time.sleep(2)
            pytest.fail("Transferarr did not become healthy")
        
        def clear_state(self):
            try:
                container = self.docker.containers.get(self.container_name)
                container.exec_run("rm -f /state/state.json")
            except:
                pass
        
        def get_torrents(self) -> list:
            """Get tracked torrents from the API."""
            url = f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/torrents"
            resp = requests.get(url, timeout=TIMEOUTS['api_response'])
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', data) if isinstance(data, dict) else data
    
    # Create manager instance
    transferarr = TransferarrManager(docker_client, radarr_api_key, sonarr_api_key)
    
    # Clean up before running transfer
    clear_radarr_state(radarr_client)
    clear_sonarr_state(sonarr_client)
    clear_deluge_torrents(deluge_source)
    clear_deluge_torrents(deluge_target)
    clear_mock_indexer_torrents()
    transferarr.clear_state()
    
    # Stop transferarr if running
    if transferarr.is_running():
        transferarr.stop()
    
    # Run transfer to create history data
    runner = LifecycleRunner(
        create_torrent, deluge_source, deluge_target,
        transferarr, radarr_client, sonarr_client
    )
    torrent_info = runner.run_migration_test('radarr', item_type='movie')
    
    # Keep transferarr running for UI tests
    yield torrent_info
    
    # No cleanup needed - history data should persist for other tests


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


@pytest.fixture
def history_page(page: Page, base_url: str) -> "HistoryPage":
    """Create a HistoryPage instance.
    
    Uses pytest-playwright's page fixture which handles screenshots.
    """
    from tests.ui.pages.history_page import HistoryPage
    return HistoryPage(page, base_url)


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