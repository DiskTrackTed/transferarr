"""
Torrents page object for UI testing.

The torrents page displays:
- Client tabs for each download client
- Torrent lists per client with state indicators
"""
from playwright.sync_api import Page, expect
from .base_page import BasePage


class TorrentsPage(BasePage):
    """Page object for the Torrents page."""
    
    # Selectors from torrents.html and torrents.js
    CARD_TITLE = ".card-title"
    LOADING_INDICATOR = "#loading-indicator"
    CLIENT_TABS = "#client-tabs"
    CLIENT_TAB = ".client-tab"
    CLIENT_TAB_CONTENTS = "#client-tab-contents"
    CLIENT_TAB_CONTENT = ".client-tab-content"
    
    # Torrent card selectors (note: different from dashboard's .torrent-card)
    TORRENT_CARD = ".simple-torrent-card"
    TORRENT_NAME = ".simple-torrent-name"
    TORRENT_STATE = ".simple-torrent-state"
    EMPTY_MESSAGE = ".empty-message"
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
    
    def goto(self) -> None:
        """Navigate to torrents page and verify it loaded.
        
        Raises:
            playwright.sync_api.TimeoutError: If page doesn't load or title not found
        """
        super().goto("/torrents")
        expect(self.page.locator(self.CARD_TITLE).first).to_have_text("All Torrents")
    
    def wait_for_torrents_loaded(self, timeout: int = 10000) -> None:
        """Wait for torrents to load (loading indicator hidden).
        
        Args:
            timeout: Maximum time to wait in milliseconds
            
        Raises:
            playwright.sync_api.TimeoutError: If loading doesn't complete within timeout
        """
        self.page.wait_for_selector(
            self.LOADING_INDICATOR, 
            state="hidden", 
            timeout=timeout
        )
    
    def get_client_tabs(self):
        """Get all client tabs."""
        return self.page.locator(self.CLIENT_TAB).all()
    
    def get_client_tab_count(self) -> int:
        """Get the number of client tabs."""
        return self.page.locator(self.CLIENT_TAB).count()
    
    def get_client_tab_names(self) -> list[str]:
        """Get the names of all client tabs.
        
        Returns:
            List of client tab names (e.g., ['source-deluge', 'target-deluge'])
        """
        tabs = self.get_client_tabs()
        return [tab.text_content().strip() for tab in tabs]
    
    def switch_to_client_tab(self, client_name: str) -> None:
        """Switch to a specific client's tab.
        
        Args:
            client_name: Name of the client tab to switch to
            
        Raises:
            playwright.sync_api.TimeoutError: If tab not found
        """
        self.page.click(f"{self.CLIENT_TAB}:has-text('{client_name}')")
    
    def get_active_client_tab(self) -> str:
        """Get the name of the active client tab."""
        active = self.page.locator(f"{self.CLIENT_TAB}.active")
        if active.count() > 0:
            return active.first.text_content().strip()
        return ""
    
    def get_torrent_cards(self):
        """Get all visible torrent cards in the active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_CARD}"
        ).all()
    
    def get_torrent_card_count(self) -> int:
        """Get the number of torrent cards in the active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_CARD}"
        ).count()
    
    def get_torrent_by_name(self, name: str):
        """Get a specific torrent card by name.
        
        Args:
            name: Partial or full name of the torrent
            
        Returns:
            Locator for the torrent card
        """
        return self.page.locator(f"{self.TORRENT_CARD}:has-text('{name}')")
    
    def has_empty_message(self) -> bool:
        """Check if empty message is visible in active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.EMPTY_MESSAGE}"
        ).is_visible()
    
    def wait_for_api_refresh(self, timeout: int = 5000) -> None:
        """Wait for next API poll.
        
        Torrents page polls /api/all_torrents every 3 seconds.
        
        Args:
            timeout: Maximum time to wait in milliseconds
            
        Raises:
            playwright.sync_api.TimeoutError: If no API response within timeout
        """
        with self.page.expect_response(
            lambda r: "/api/all_torrents" in r.url,
            timeout=timeout
        ):
            pass  # Wait for next poll cycle
