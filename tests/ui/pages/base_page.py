"""
Base page class for all page objects.

This module provides common functionality shared across all pages,
including navigation, waiting utilities, and common element selectors.
"""
from playwright.sync_api import Page, expect


class BasePage:
    """Base class for all page objects."""
    
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
    
    # Selectors for common elements (from base.html and components/sidebar.html)
    SIDEBAR = ".sidebar"
    NAV_DASHBOARD = ".sidebar a[href='/']"
    NAV_TORRENTS = ".sidebar a[href='/torrents']"
    NAV_SETTINGS = ".sidebar a[href='/settings']"
    CONTENT = ".content"
    LOGO = ".logo"
    
    def goto(self, path: str = "") -> None:
        """Navigate to a page.
        
        Args:
            path: The path to navigate to (e.g., "/settings")
            
        Raises:
            playwright.sync_api.TimeoutError: If navigation times out
        """
        self.page.goto(f"{self.base_url}{path}")
    
    def navigate_to_dashboard(self) -> None:
        """Click dashboard in sidebar and wait for navigation.
        
        Raises:
            playwright.sync_api.TimeoutError: If navigation fails
        """
        self.page.click(self.NAV_DASHBOARD)
        expect(self.page).to_have_url(f"{self.base_url}/")
    
    def navigate_to_torrents(self) -> None:
        """Click torrents in sidebar and wait for navigation.
        
        Raises:
            playwright.sync_api.TimeoutError: If navigation fails
        """
        self.page.click(self.NAV_TORRENTS)
        expect(self.page).to_have_url(f"{self.base_url}/torrents")
    
    def navigate_to_settings(self) -> None:
        """Click settings in sidebar and wait for navigation.
        
        Raises:
            playwright.sync_api.TimeoutError: If navigation fails
        """
        self.page.click(self.NAV_SETTINGS)
        expect(self.page).to_have_url(f"{self.base_url}/settings")
    
    def click_logo(self) -> None:
        """Click the logo to go to dashboard.
        
        Raises:
            playwright.sync_api.TimeoutError: If navigation fails
        """
        self.page.click(self.LOGO)
        expect(self.page).to_have_url(f"{self.base_url}/")
    
    def wait_for_api_response(self, url_pattern: str, timeout: int = 5000, method: str = None):
        """Wait for an API call to complete.
        
        Args:
            url_pattern: String that should be in the API URL
            timeout: Maximum time to wait in milliseconds
            method: Optional HTTP method to filter by (GET, POST, etc.)
            
        Returns:
            Context manager that yields response info
            
        Raises:
            playwright.sync_api.TimeoutError: If no matching response within timeout
            
        Example:
            with page_object.wait_for_api_response("/api/torrents") as response_info:
                page_object.page.click("#refresh")
            assert response_info.value.status == 200
        """
        def matcher(response):
            url_match = url_pattern in response.url
            method_match = method is None or response.request.method == method
            return url_match and method_match
        
        return self.page.expect_response(matcher, timeout=timeout)
    
    def get_page_title(self) -> str:
        """Get the current page title."""
        return self.page.title()
    
    def is_sidebar_visible(self) -> bool:
        """Check if the sidebar is visible."""
        return self.page.locator(self.SIDEBAR).is_visible()
    
    def get_active_nav_item(self) -> str:
        """Get the text of the active navigation item.
        
        Returns:
            The text content of the active nav item, or empty string if none found
        """
        # The active class is on .tab-link, text is in the nested <a>
        active = self.page.locator(".sidebar .tab-link.active")
        if active.count() > 0:
            return active.first.text_content().strip()
        return ""
