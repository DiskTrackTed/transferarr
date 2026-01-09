"""
Dashboard page object for UI testing.

The dashboard displays:
- Stats cards (active, completed, copying torrents)
- Current watchlist with torrent cards
"""
from playwright.sync_api import Page, expect
from .base_page import BasePage


class DashboardPage(BasePage):
    """Page object for the Dashboard page."""
    
    # Selectors from dashboard.html
    CARD_TITLE = ".card-title"
    STATS_CONTAINER = ".stats-container"
    STAT_CARD = ".stat-card"
    STAT_ACTIVE = "#active-torrents"
    STAT_COMPLETED = "#completed-torrents"
    STAT_COPYING = "#copying-torrents"
    
    # Torrent list selectors (from dashboard.js)
    RECENT_TORRENTS = "#recent-torrents-container"
    TORRENT_CARD = ".torrent-card"
    NO_TORRENTS_MSG = ".no-torrents-msg"
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
    
    def goto(self) -> None:
        """Navigate to dashboard and verify it loaded.
        
        Raises:
            playwright.sync_api.TimeoutError: If page doesn't load or title not found
        """
        super().goto("/")
        expect(self.page.locator(self.CARD_TITLE).first).to_have_text("Dashboard")
    
    def get_active_count(self) -> int:
        """Get the active torrents count from stats card.
        
        Returns:
            Number of active torrents, or 0 if element empty/not found
        """
        text = self.page.locator(self.STAT_ACTIVE).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_completed_count(self) -> int:
        """Get the completed torrents count from stats card.
        
        Returns:
            Number of completed torrents, or 0 if element empty/not found
        """
        text = self.page.locator(self.STAT_COMPLETED).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_copying_count(self) -> int:
        """Get the copying torrents count from stats card.
        
        Returns:
            Number of copying torrents, or 0 if element empty/not found
        """
        text = self.page.locator(self.STAT_COPYING).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_all_stats(self) -> dict[str, int]:
        """Get all stats as a dictionary.
        
        Returns:
            Dict with keys 'active', 'completed', 'copying' and integer values
        """
        return {
            "active": self.get_active_count(),
            "completed": self.get_completed_count(),
            "copying": self.get_copying_count(),
        }
    
    def get_torrent_cards(self):
        """Get all torrent cards in the watchlist."""
        return self.page.locator(self.TORRENT_CARD).all()
    
    def get_torrent_card_count(self) -> int:
        """Get the number of torrent cards displayed."""
        return self.page.locator(self.TORRENT_CARD).count()
    
    def has_no_torrents_message(self) -> bool:
        """Check if 'no torrents' message is visible."""
        return self.page.locator(self.NO_TORRENTS_MSG).is_visible()
    
    def get_torrent_by_name(self, name: str):
        """Get a specific torrent card by name.
        
        Args:
            name: Partial or full name of the torrent
            
        Returns:
            Locator for the torrent card
        """
        return self.page.locator(f"{self.TORRENT_CARD}:has-text('{name}')")
    
    def wait_for_stats_update(self, timeout: int = 5000) -> None:
        """Wait for stats to update via API call.
        
        Dashboard polls /api/torrents every 2 seconds, so this waits
        for that poll to complete.
        
        Args:
            timeout: Maximum time to wait in milliseconds
            
        Raises:
            playwright.sync_api.TimeoutError: If no API response within timeout
        """
        with self.page.expect_response(
            lambda r: "/api/torrents" in r.url,
            timeout=timeout
        ):
            pass  # Wait for next poll cycle
    
    def wait_for_torrent_to_appear(self, name: str, timeout: int = 30000) -> None:
        """Wait for a specific torrent to appear in the list.
        
        Args:
            name: Name of the torrent to wait for (partial match supported)
            timeout: Maximum time to wait in milliseconds
            
        Raises:
            playwright.sync_api.TimeoutError: If torrent doesn't appear within timeout
        """
        expect(self.get_torrent_by_name(name)).to_be_visible(timeout=timeout)
