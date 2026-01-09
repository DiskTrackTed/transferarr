"""
Torrents page tests for Transferarr UI.

Tests the torrents page functionality including:
- Client tabs display and switching
- Torrent list per client
- Loading states
- Automatic polling behavior
"""
import re
import pytest
from playwright.sync_api import Page, expect

from tests.ui.helpers import UI_TIMEOUTS


class TestTorrentsPageLoading:
    """Tests for torrents page loading and initial state."""
    
    def test_torrents_page_loads_with_correct_title(self, page: Page, base_url: str):
        """Test that torrents page loads with correct title."""
        page.goto(f"{base_url}/torrents")
        
        expect(page).to_have_title("Transferarr - Torrents")
    
    def test_torrents_page_shows_heading(self, torrents_page):
        """Test that torrents page shows the correct heading."""
        torrents_page.goto()
        
        expect(torrents_page.page.locator("h2")).to_contain_text("All Torrents")
    
    def test_client_tabs_container_exists(self, torrents_page):
        """Test that client tabs container is present."""
        torrents_page.goto()
        
        expect(torrents_page.page.locator(torrents_page.CLIENT_TABS)).to_be_attached()
    
    def test_loading_indicator_eventually_hides(self, torrents_page):
        """Test that loading indicator disappears after data loads."""
        torrents_page.goto()
        
        # Loading should complete within reasonable time
        torrents_page.wait_for_torrents_loaded(timeout=UI_TIMEOUTS['element_visible'])
        
        expect(torrents_page.page.locator(torrents_page.LOADING_INDICATOR)).to_be_hidden()


class TestClientTabs:
    """Tests for client tab functionality."""
    
    def test_client_tabs_appear_after_loading(self, torrents_page):
        """Test that client tabs appear once data loads."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # Should have at least one client tab
        tabs = torrents_page.get_client_tabs()
        assert len(tabs) >= 1
    
    def test_get_client_tab_count(self, torrents_page):
        """Test that get_client_tab_count returns correct count."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        count = torrents_page.get_client_tab_count()
        tabs = torrents_page.get_client_tabs()
        
        assert count == len(tabs)
    
    def test_get_client_tab_names(self, torrents_page):
        """Test that get_client_tab_names returns list of strings."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        names = torrents_page.get_client_tab_names()
        
        assert isinstance(names, list)
        if len(names) > 0:
            assert all(isinstance(name, str) for name in names)
            assert all(len(name) > 0 for name in names)
    
    def test_first_tab_is_active_by_default(self, torrents_page):
        """Test that first client tab is active by default."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        tabs = torrents_page.get_client_tabs()
        if len(tabs) > 0:
            first_tab = tabs[0]
            expect(first_tab).to_have_class(re.compile(r"active"))
    
    def test_get_active_client_tab(self, torrents_page):
        """Test that get_active_client_tab returns the active tab name."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        active_name = torrents_page.get_active_client_tab()
        
        # Should return a non-empty string if tabs exist
        tab_count = torrents_page.get_client_tab_count()
        if tab_count > 0:
            assert isinstance(active_name, str)
            assert len(active_name) > 0


class TestClientTabSwitching:
    """Tests for switching between client tabs."""
    
    def test_switch_to_second_tab(self, torrents_page):
        """Test switching to a different client tab."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        tabs = torrents_page.get_client_tabs()
        if len(tabs) >= 2:
            # Get second tab name
            second_tab = tabs[1]
            tab_name = second_tab.text_content().strip()
            
            # Switch to second tab
            torrents_page.switch_to_client_tab(tab_name)
            
            # Second tab should now be active
            expect(second_tab).to_have_class(re.compile(r"active"))
    
    def test_tab_content_changes_on_switch(self, torrents_page):
        """Test that tab content area updates when switching tabs."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        tabs = torrents_page.get_client_tabs()
        if len(tabs) >= 2:
            # Get tab names
            first_name = tabs[0].text_content().strip()
            second_name = tabs[1].text_content().strip()
            
            # Switch to second tab
            torrents_page.switch_to_client_tab(second_name)
            
            # Switch back to first
            torrents_page.switch_to_client_tab(first_name)
            
            # First should be active again
            expect(tabs[0]).to_have_class(re.compile(r"active"))


class TestTorrentList:
    """Tests for torrent list display within client tabs."""
    
    def test_torrent_cards_in_active_tab(self, torrents_page):
        """Test that torrent cards are found in active tab."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # Method should return list (possibly empty)
        cards = torrents_page.get_torrent_cards()
        assert isinstance(cards, list)
    
    def test_torrent_card_count(self, torrents_page):
        """Test that get_torrent_card_count returns correct count."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        count = torrents_page.get_torrent_card_count()
        cards = torrents_page.get_torrent_cards()
        
        assert count == len(cards)
    
    def test_empty_message_or_torrents(self, torrents_page):
        """Test that either torrents or empty message is shown."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        has_torrents = torrents_page.get_torrent_card_count() > 0
        has_empty = torrents_page.has_empty_message()
        
        # One should be true
        assert has_torrents or has_empty


class TestTorrentsPolling:
    """Tests for torrents page automatic polling behavior."""
    
    def test_torrents_page_polls_api(self, torrents_page, page: Page):
        """Test that torrents page polls the API for updates.
        
        Torrents.js polls /api/all_torrents every 3 seconds.
        """
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # Wait for API call (should happen within 5 seconds)
        with page.expect_response(
            lambda r: "/api/all_torrents" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            pass  # Wait for next poll cycle
        
        assert response_info.value.status == 200
    
    def test_wait_for_api_refresh(self, torrents_page):
        """Test the wait_for_api_refresh helper method."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # Should not raise timeout
        torrents_page.wait_for_api_refresh(timeout=UI_TIMEOUTS['api_response'])


class TestTorrentsNavigation:
    """Tests for navigation from torrents page."""
    
    def test_navigate_to_dashboard_from_torrents(self, torrents_page):
        """Test navigating to dashboard from torrents page."""
        torrents_page.goto()
        
        torrents_page.navigate_to_dashboard()
        
        expect(torrents_page.page).to_have_url(f"{torrents_page.base_url}/")
    
    def test_navigate_to_settings_from_torrents(self, torrents_page):
        """Test navigating to settings from torrents page."""
        torrents_page.goto()
        
        torrents_page.navigate_to_settings()
        
        expect(torrents_page.page).to_have_url(f"{torrents_page.base_url}/settings")
    
    def test_sidebar_visible_on_torrents(self, torrents_page):
        """Test that sidebar is visible on torrents page."""
        torrents_page.goto()
        
        assert torrents_page.is_sidebar_visible()
