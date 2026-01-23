"""
Page object for the login page.

This page appears when auth is enabled and the user is not authenticated.
"""
from playwright.sync_api import Page, expect


class LoginPage:
    """Page object for the login page (/login)."""
    
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
    ALERT_SUCCESS = ".alert-success"
    
    # Form elements
    USERNAME_INPUT = "#username"
    PASSWORD_INPUT = "#password"
    REMEMBER_CHECKBOX = "#remember"
    SUBMIT_BUTTON = "button[type='submit']"
    
    # Footer
    VERSION = ".login-footer .version"
    
    def goto(self) -> None:
        """Navigate to the login page."""
        self.page.goto(f"{self.base_url}/login")
    
    def fill_username(self, username: str) -> None:
        """Fill in the username field."""
        self.page.fill(self.USERNAME_INPUT, username)
    
    def fill_password(self, password: str) -> None:
        """Fill in the password field."""
        self.page.fill(self.PASSWORD_INPUT, password)
    
    def check_remember_me(self) -> None:
        """Check the remember me checkbox."""
        self.page.check(self.REMEMBER_CHECKBOX)
    
    def uncheck_remember_me(self) -> None:
        """Uncheck the remember me checkbox."""
        self.page.uncheck(self.REMEMBER_CHECKBOX)
    
    def click_submit(self) -> None:
        """Click the submit/sign in button."""
        self.page.click(self.SUBMIT_BUTTON)
    
    def login(self, username: str, password: str, remember: bool = False) -> None:
        """Perform a complete login.
        
        Args:
            username: The username to enter
            password: The password to enter
            remember: Whether to check the remember me box
        """
        self.fill_username(username)
        self.fill_password(password)
        if remember:
            self.check_remember_me()
        self.click_submit()
    
    def get_error_message(self) -> str:
        """Get the error message text if visible."""
        error = self.page.locator(self.ALERT_ERROR)
        if error.is_visible():
            return error.inner_text()
        return ""
    
    def get_success_message(self) -> str:
        """Get the success message text if visible."""
        success = self.page.locator(self.ALERT_SUCCESS)
        if success.is_visible():
            return success.inner_text()
        return ""
    
    def is_username_field_visible(self) -> bool:
        """Check if the username field is visible."""
        return self.page.locator(self.USERNAME_INPUT).is_visible()
    
    def is_password_field_visible(self) -> bool:
        """Check if the password field is visible."""
        return self.page.locator(self.PASSWORD_INPUT).is_visible()
    
    def is_remember_checkbox_visible(self) -> bool:
        """Check if the remember me checkbox is visible."""
        return self.page.locator(self.REMEMBER_CHECKBOX).is_visible()
    
    def is_submit_button_visible(self) -> bool:
        """Check if the submit button is visible."""
        return self.page.locator(self.SUBMIT_BUTTON).is_visible()
    
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
        """Wait for redirect after successful login."""
        self.page.wait_for_url(lambda url: "/login" not in url, timeout=timeout)
