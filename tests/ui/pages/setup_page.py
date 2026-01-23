"""
Page object for the setup page.

This page appears on first-run when auth is enabled but no credentials are configured.
"""
from playwright.sync_api import Page, expect


class SetupPage:
    """Page object for the setup page (/setup)."""
    
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url
    
    # Selectors
    LOGIN_CONTAINER = ".login-container"
    LOGIN_CARD = ".login-card"
    LOGO = ".logo"
    SUBTITLE = ".login-subtitle"
    ALERT = ".alert"
    ALERT_ERROR = ".alert-error"
    
    # Form elements
    USERNAME_INPUT = "#username"
    PASSWORD_INPUT = "#password"
    CONFIRM_PASSWORD_INPUT = "#confirm_password"
    CREATE_BUTTON = "#create-form button[type='submit']"
    SKIP_BUTTON = "#skip-form button[type='submit']"
    
    # Footer
    VERSION = ".login-footer .version"
    
    def goto(self) -> None:
        """Navigate to the setup page."""
        self.page.goto(f"{self.base_url}/setup")
    
    def fill_username(self, username: str) -> None:
        """Fill in the username field."""
        self.page.fill(self.USERNAME_INPUT, username)
    
    def fill_password(self, password: str) -> None:
        """Fill in the password field."""
        self.page.fill(self.PASSWORD_INPUT, password)
    
    def fill_confirm_password(self, password: str) -> None:
        """Fill in the confirm password field."""
        self.page.fill(self.CONFIRM_PASSWORD_INPUT, password)
    
    def click_create_account(self) -> None:
        """Click the create account button."""
        self.page.click(self.CREATE_BUTTON)
    
    def click_skip(self) -> None:
        """Click the skip setup button."""
        self.page.click(self.SKIP_BUTTON)
    
    def create_account(self, username: str, password: str, confirm_password: str = None) -> None:
        """Perform a complete account creation.
        
        Args:
            username: The username to enter
            password: The password to enter
            confirm_password: The confirmation password (defaults to same as password)
        """
        self.fill_username(username)
        self.fill_password(password)
        self.fill_confirm_password(confirm_password or password)
        self.click_create_account()
    
    def get_error_message(self) -> str:
        """Get the error message text if visible."""
        error = self.page.locator(self.ALERT_ERROR)
        if error.is_visible():
            return error.inner_text()
        return ""
    
    def is_username_field_visible(self) -> bool:
        """Check if the username field is visible."""
        return self.page.locator(self.USERNAME_INPUT).is_visible()
    
    def is_password_field_visible(self) -> bool:
        """Check if the password field is visible."""
        return self.page.locator(self.PASSWORD_INPUT).is_visible()
    
    def is_confirm_password_field_visible(self) -> bool:
        """Check if the confirm password field is visible."""
        return self.page.locator(self.CONFIRM_PASSWORD_INPUT).is_visible()
    
    def is_create_button_visible(self) -> bool:
        """Check if the create account button is visible."""
        return self.page.locator(self.CREATE_BUTTON).is_visible()
    
    def is_skip_button_visible(self) -> bool:
        """Check if the skip button is visible."""
        return self.page.locator(self.SKIP_BUTTON).is_visible()
    
    def get_logo_text(self) -> str:
        """Get the logo text."""
        return self.page.locator(self.LOGO).inner_text()
    
    def get_subtitle_text(self) -> str:
        """Get the subtitle text."""
        return self.page.locator(self.SUBTITLE).inner_text()
    
    def get_version_text(self) -> str:
        """Get the version text from the footer."""
        return self.page.locator(self.VERSION).inner_text()
    
    def wait_for_redirect(self, timeout: int = 5000) -> None:
        """Wait for redirect after successful setup or skip."""
        self.page.wait_for_url(lambda url: "/setup" not in url, timeout=timeout)
