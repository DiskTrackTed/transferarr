"""
Dashboard page tests for Transferarr UI.

Tests the dashboard page functionality including:
- Stats cards display and updates
- Torrent list rendering
- Automatic polling behavior
"""
import pytest
from playwright.sync_api import Page, expect

from tests.ui.helpers import UI_TIMEOUTS


class TestDashboardLoading:
    """Tests for dashboard page loading and initial state."""
    
    def test_dashboard_loads_with_correct_title(self, page: Page, base_url: str):
        """Test that dashboard page loads with correct title."""
        page.goto(base_url)
        
        expect(page).to_have_title("Transferarr - Dashboard")
    
    def test_dashboard_shows_page_heading(self, dashboard_page):
        """Test that dashboard shows the correct heading."""
        dashboard_page.goto()
        
        expect(dashboard_page.page.locator("h2")).to_contain_text("Dashboard")
    
    def test_stats_cards_are_visible(self, dashboard_page):
        """Test that all stats cards are visible on dashboard."""
        dashboard_page.goto()
        
        # All three stat cards should be visible
        expect(dashboard_page.page.locator(dashboard_page.STAT_ACTIVE)).to_be_visible()
        expect(dashboard_page.page.locator(dashboard_page.STAT_COMPLETED)).to_be_visible()
        expect(dashboard_page.page.locator(dashboard_page.STAT_COPYING)).to_be_visible()
    
    def test_recent_torrents_container_exists(self, dashboard_page):
        """Test that recent torrents container is present."""
        dashboard_page.goto()
        
        expect(dashboard_page.page.locator(dashboard_page.RECENT_TORRENTS)).to_be_visible()


class TestDashboardStats:
    """Tests for dashboard statistics display."""
    
    def test_stats_are_numeric(self, dashboard_page):
        """Test that stats display numeric values."""
        dashboard_page.goto()
        
        # Wait for stats to load
        dashboard_page.wait_for_stats_update()
        
        # All stats should be non-negative integers
        assert dashboard_page.get_active_count() >= 0
        assert dashboard_page.get_completed_count() >= 0
        assert dashboard_page.get_copying_count() >= 0
    
    def test_get_all_stats_returns_dict(self, dashboard_page):
        """Test that get_all_stats returns properly structured dict."""
        dashboard_page.goto()
        dashboard_page.wait_for_stats_update()
        
        stats = dashboard_page.get_all_stats()
        
        assert isinstance(stats, dict)
        assert "active" in stats
        assert "completed" in stats
        assert "copying" in stats
        assert all(isinstance(v, int) for v in stats.values())


class TestDashboardPolling:
    """Tests for dashboard automatic polling behavior."""
    
    def test_dashboard_polls_api(self, dashboard_page, page: Page):
        """Test that dashboard polls the API for updates.
        
        Dashboard.js polls /api/v1/torrents every 2 seconds.
        """
        dashboard_page.goto()
        
        # Wait for at least one API call (should happen within 3 seconds)
        with page.expect_response(
            lambda r: "/api/v1/torrents" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            pass  # Wait for poll to complete
        
        assert response_info.value.status == 200
    
    def test_api_response_contains_expected_fields(self, dashboard_page, page: Page):
        """Test that the API response has expected structure."""
        dashboard_page.goto()
        
        with page.expect_response(
            lambda r: "/api/v1/torrents" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            pass  # Wait for poll to complete
        
        data = response_info.value.json()
        
        # Response should have data envelope with torrents list
        # Supports both old format (direct array) and new format (data envelope)
        torrents = data.get("data") if isinstance(data, dict) else data
        assert isinstance(torrents, list)


class TestDashboardTorrentList:
    """Tests for the torrent list display on dashboard."""
    
    def test_torrent_card_count_matches_method(self, dashboard_page):
        """Test that get_torrent_card_count returns correct count."""
        dashboard_page.goto()
        dashboard_page.wait_for_stats_update()
        
        count = dashboard_page.get_torrent_card_count()
        cards = dashboard_page.get_torrent_cards()
        
        assert count == len(cards)
    
    def test_empty_state_or_torrents_shown(self, dashboard_page):
        """Test that either torrents or empty message is shown."""
        dashboard_page.goto()
        dashboard_page.wait_for_stats_update()
        
        # Either we have torrents or we have the no-torrents message
        has_torrents = dashboard_page.get_torrent_card_count() > 0
        has_empty_msg = dashboard_page.has_no_torrents_message()
        
        # One of these should be true (XOR)
        assert has_torrents or has_empty_msg


class TestDashboardNavigation:
    """Tests for navigation from dashboard to other pages."""
    
    def test_navigate_to_torrents_from_dashboard(self, dashboard_page):
        """Test navigating to torrents page from dashboard."""
        dashboard_page.goto()
        
        dashboard_page.navigate_to_torrents()
        
        expect(dashboard_page.page).to_have_url(f"{dashboard_page.base_url}/torrents")
    
    def test_navigate_to_settings_from_dashboard(self, dashboard_page):
        """Test navigating to settings page from dashboard."""
        dashboard_page.goto()
        
        dashboard_page.navigate_to_settings()
        
        expect(dashboard_page.page).to_have_url(f"{dashboard_page.base_url}/settings")
    
    def test_sidebar_visible_on_dashboard(self, dashboard_page):
        """Test that sidebar is visible on dashboard."""
        dashboard_page.goto()
        
        assert dashboard_page.is_sidebar_visible()
