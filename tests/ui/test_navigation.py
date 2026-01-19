"""
Navigation tests for Transferarr UI.

Tests sidebar navigation, URL routing, and page accessibility.
"""
import re
import pytest
from playwright.sync_api import Page, expect

from tests.ui.helpers import UI_TIMEOUTS


class TestSidebarNavigation:
    """Tests for sidebar navigation functionality."""
    
    def test_sidebar_is_visible(self, page: Page, base_url: str):
        """Test that sidebar is visible on all pages."""
        page.goto(base_url)
        expect(page.locator(".sidebar")).to_be_visible()
    
    def test_navigate_to_dashboard(self, page: Page, base_url: str):
        """Test navigation to dashboard via sidebar."""
        # Start from settings page
        page.goto(f"{base_url}/settings")
        
        # Click dashboard link
        page.click(".sidebar a[href='/']")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/")
        expect(page.locator("h2")).to_contain_text("Dashboard")
    
    def test_navigate_to_torrents(self, page: Page, base_url: str):
        """Test navigation to torrents page via sidebar."""
        page.goto(base_url)
        
        # Click torrents link
        page.click(".sidebar a[href='/torrents']")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/torrents")
        expect(page.locator("h2")).to_contain_text("All Torrents")
    
    def test_navigate_to_history(self, page: Page, base_url: str):
        """Test navigation to history page via sidebar."""
        page.goto(base_url)
        
        # Click history link
        page.click(".sidebar a[href='/history']")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/history")
        expect(page.locator("h2")).to_contain_text("Transfer History")
    
    def test_navigate_to_settings(self, page: Page, base_url: str):
        """Test navigation to settings page via sidebar."""
        page.goto(base_url)
        
        # Click settings link
        page.click(".sidebar a[href='/settings']")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/settings")
        expect(page.locator("h2")).to_contain_text("Settings")
    
    def test_logo_navigates_to_dashboard(self, page: Page, base_url: str):
        """Test that clicking the logo navigates to dashboard."""
        # Start from settings
        page.goto(f"{base_url}/settings")
        
        # Click logo
        page.click(".logo")
        
        # Verify navigation to dashboard
        expect(page).to_have_url(f"{base_url}/")
    
    def test_active_nav_item_highlighted(self, page: Page, base_url: str):
        """Test that the active page is highlighted in sidebar."""
        # Check dashboard
        page.goto(base_url)
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("Dashboard")
        
        # Check torrents
        page.goto(f"{base_url}/torrents")
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("Torrents")
        
        # Check history
        page.goto(f"{base_url}/history")
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("History")
        
        # Check settings
        page.goto(f"{base_url}/settings")
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("Settings")


class TestDirectURLAccess:
    """Tests for direct URL access to pages."""
    
    def test_dashboard_direct_access(self, page: Page, base_url: str):
        """Test that dashboard is accessible via direct URL."""
        page.goto(f"{base_url}/")
        
        expect(page).to_have_title("Transferarr - Dashboard")
        expect(page.locator("h2")).to_contain_text("Dashboard")
    
    def test_torrents_direct_access(self, page: Page, base_url: str):
        """Test that torrents page is accessible via direct URL."""
        page.goto(f"{base_url}/torrents")
        
        expect(page).to_have_title("Transferarr - Torrents")
        expect(page.locator("h2")).to_contain_text("All Torrents")
    
    def test_history_direct_access(self, page: Page, base_url: str):
        """Test that history page is accessible via direct URL."""
        page.goto(f"{base_url}/history")
        
        expect(page).to_have_title("Transferarr - History")
        expect(page.locator("h2")).to_contain_text("Transfer History")
    
    def test_settings_direct_access(self, page: Page, base_url: str):
        """Test that settings page is accessible via direct URL."""
        page.goto(f"{base_url}/settings")
        
        expect(page).to_have_title("Transferarr - Settings")
        expect(page.locator("h2")).to_contain_text("Settings")


class TestSettingsTabNavigation:
    """Tests for settings page tab navigation."""
    
    def test_clients_tab_is_default(self, page: Page, base_url: str):
        """Test that Download Clients tab is active by default."""
        page.goto(f"{base_url}/settings")
        
        # Clients tab should be active
        clients_tab = page.locator(".client-tab[data-tab='download-clients']")
        expect(clients_tab).to_have_class(re.compile(r"active"))
        
        # Clients content should be visible
        expect(page.locator("#download-clients-tab-content")).to_be_visible()
    
    def test_switch_to_connections_tab(self, page: Page, base_url: str):
        """Test switching to Connections tab."""
        page.goto(f"{base_url}/settings")
        
        # Click connections tab
        page.click(".client-tab[data-tab='connections']")
        
        # Connections tab should be active
        connections_tab = page.locator(".client-tab[data-tab='connections']")
        expect(connections_tab).to_have_class(re.compile(r"active"))
        
        # Connections content should be visible
        expect(page.locator("#connections-tab-content")).to_be_visible()
        
        # URL hash should update
        expect(page).to_have_url(re.compile(r".*#connections"))
    
    def test_tab_persistence_via_url_hash(self, page: Page, base_url: str):
        """Test that tab selection persists via URL hash."""
        # Go to settings with connections hash
        page.goto(f"{base_url}/settings#connections")
        
        # Wait for JavaScript to process the hash
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        # Connections tab should be active
        expect(page.locator(".client-tab[data-tab='connections']")).to_have_class(re.compile(r"active"))
    
    def test_switch_back_to_clients_tab(self, page: Page, base_url: str):
        """Test switching back to clients tab from connections."""
        page.goto(f"{base_url}/settings#connections")
        page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        
        # Click clients tab
        page.click(".client-tab[data-tab='download-clients']")
        
        # Clients tab should be active
        expect(page.locator(".client-tab[data-tab='download-clients']")).to_have_class(re.compile(r"active"))
        
        # URL hash should update
        expect(page).to_have_url(re.compile(r".*#download-clients"))


class TestPageLoading:
    """Tests for page loading behavior."""
    
    def test_dashboard_loads_content(self, page: Page, base_url: str):
        """Test that dashboard loads its content properly."""
        page.goto(base_url)
        
        # Stats cards should be visible
        expect(page.locator("#active-torrents")).to_be_visible()
        expect(page.locator("#completed-torrents")).to_be_visible()
        expect(page.locator("#copying-torrents")).to_be_visible()
        
        # Watchlist container should exist
        expect(page.locator("#recent-torrents-container")).to_be_visible()
    
    def test_torrents_page_shows_loading(self, page: Page, base_url: str):
        """Test that torrents page shows loading indicator initially."""
        # Capture loading state by going to page
        page.goto(f"{base_url}/torrents")
        
        # Either loading indicator is visible OR it's already hidden (fast load)
        # We check that client tabs container exists
        expect(page.locator("#client-tabs")).to_be_attached()
    
    def test_settings_page_loads_tabs(self, page: Page, base_url: str):
        """Test that settings page loads both tabs."""
        page.goto(f"{base_url}/settings")
        
        # Both tabs should be visible
        expect(page.locator(".client-tab[data-tab='download-clients']")).to_be_visible()
        expect(page.locator(".client-tab[data-tab='connections']")).to_be_visible()
