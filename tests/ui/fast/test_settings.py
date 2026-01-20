"""
Settings page tests for Transferarr UI.

Tests the settings page functionality including:
- Tab switching between Clients and Connections
- Client and connection list display
- Modal interactions
- Form validation
"""
import re
import pytest
from playwright.sync_api import Page, expect


class TestSettingsPageLoading:
    """Tests for settings page loading and initial state."""
    
    def test_settings_page_loads_with_correct_title(self, page: Page, base_url: str):
        """Test that settings page loads with correct title."""
        page.goto(f"{base_url}/settings")
        
        expect(page).to_have_title("Transferarr - Settings")
    
    def test_settings_page_shows_heading(self, settings_page):
        """Test that settings page shows the correct heading."""
        settings_page.goto()
        
        expect(settings_page.page.locator("h2")).to_contain_text("Settings")
    
    def test_settings_tabs_exist(self, settings_page):
        """Test that settings tabs container is present."""
        settings_page.goto()
        
        expect(settings_page.page.locator(settings_page.SETTINGS_TABS)).to_be_attached()
    
    def test_clients_tab_exists(self, settings_page):
        """Test that Clients tab exists."""
        settings_page.goto()
        
        expect(settings_page.get_clients_tab()).to_be_attached()
    
    def test_connections_tab_exists(self, settings_page):
        """Test that Connections tab exists."""
        settings_page.goto()
        
        expect(settings_page.get_connections_tab()).to_be_attached()


class TestSettingsTabs:
    """Tests for settings tab functionality."""
    
    def test_clients_tab_active_by_default(self, settings_page):
        """Test that Clients tab is active by default."""
        settings_page.goto()
        
        clients_tab = settings_page.get_clients_tab()
        expect(clients_tab).to_have_class(re.compile(r"active"))
    
    def test_connections_tab_inactive_by_default(self, settings_page):
        """Test that Connections tab is inactive by default."""
        settings_page.goto()
        
        connections_tab = settings_page.get_connections_tab()
        expect(connections_tab).not_to_have_class(re.compile(r"active"))
    
    def test_clients_content_visible_by_default(self, settings_page):
        """Test that clients content is visible by default."""
        settings_page.goto()
        
        expect(settings_page.page.locator(settings_page.CLIENTS_CONTENT)).to_be_visible()
    
    def test_connections_content_hidden_by_default(self, settings_page):
        """Test that connections content is hidden by default."""
        settings_page.goto()
        
        expect(settings_page.page.locator(settings_page.CONNECTIONS_CONTENT)).to_be_hidden()


class TestTabSwitching:
    """Tests for switching between settings tabs."""
    
    def test_switch_to_connections_tab(self, settings_page):
        """Test switching to connections tab."""
        settings_page.goto()
        
        settings_page.switch_to_connections_tab()
        
        connections_tab = settings_page.get_connections_tab()
        expect(connections_tab).to_have_class(re.compile(r"active"))
    
    def test_switch_to_clients_tab(self, settings_page):
        """Test switching to clients tab from connections."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        settings_page.switch_to_clients_tab()
        
        clients_tab = settings_page.get_clients_tab()
        expect(clients_tab).to_have_class(re.compile(r"active"))
    
    def test_connections_content_visible_after_switch(self, settings_page):
        """Test that connections content is visible after switching."""
        settings_page.goto()
        
        settings_page.switch_to_connections_tab()
        
        expect(settings_page.page.locator(settings_page.CONNECTIONS_CONTENT)).to_be_visible()
    
    def test_clients_content_hidden_after_switch(self, settings_page):
        """Test that clients content is hidden after switching to connections."""
        settings_page.goto()
        
        settings_page.switch_to_connections_tab()
        
        expect(settings_page.page.locator(settings_page.CLIENTS_CONTENT)).to_be_hidden()


class TestClientsList:
    """Tests for clients list display."""
    
    def test_get_client_cards(self, settings_page):
        """Test that get_client_cards returns list."""
        settings_page.goto()
        
        cards = settings_page.get_client_cards()
        assert isinstance(cards, list)
    
    def test_get_client_count(self, settings_page):
        """Test that get_client_count returns correct count."""
        settings_page.goto()
        
        count = settings_page.get_client_count()
        cards = settings_page.get_client_cards()
        
        assert count == len(cards)
    
    def test_get_client_names(self, settings_page):
        """Test that get_client_names returns list of strings."""
        settings_page.goto()
        
        names = settings_page.get_client_names()
        
        assert isinstance(names, list)
        if len(names) > 0:
            assert all(isinstance(name, str) for name in names)
    
    def test_add_client_button_exists(self, settings_page):
        """Test that Add Client button exists."""
        settings_page.goto()
        
        add_btn = settings_page.page.locator(settings_page.ADD_CLIENT_BTN)
        expect(add_btn).to_be_visible()


class TestConnectionsList:
    """Tests for connections list display."""
    
    def test_get_connection_cards(self, settings_page):
        """Test that get_connection_cards returns list."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        cards = settings_page.get_connection_cards()
        assert isinstance(cards, list)
    
    def test_get_connection_count(self, settings_page):
        """Test that get_connection_count returns correct count."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.wait_for_connections_loaded()
        
        count = settings_page.get_connection_count()
        cards = settings_page.get_connection_cards()
        
        assert count == len(cards)
    
    def test_add_connection_button_exists(self, settings_page):
        """Test that Add Connection button exists."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        add_btn = settings_page.page.locator(settings_page.ADD_CONNECTION_BTN)
        expect(add_btn).to_be_visible()


class TestClientModal:
    """Tests for client add/edit modal."""
    
    def test_open_add_client_modal(self, settings_page):
        """Test opening the add client modal."""
        settings_page.goto()
        
        settings_page.open_add_client_modal()
        
        modal = settings_page.page.locator(settings_page.CLIENT_MODAL)
        expect(modal).to_be_visible()
    
    def test_close_client_modal(self, settings_page):
        """Test closing the client modal."""
        settings_page.goto()
        settings_page.open_add_client_modal()
        
        settings_page.close_client_modal()
        
        modal = settings_page.page.locator(settings_page.CLIENT_MODAL)
        expect(modal).to_be_hidden()
    
    def test_client_modal_has_name_field(self, settings_page):
        """Test that client modal has name input field."""
        settings_page.goto()
        settings_page.open_add_client_modal()
        
        name_field = settings_page.page.locator(settings_page.CLIENT_NAME_INPUT)
        expect(name_field).to_be_visible()
    
    def test_client_modal_has_save_button(self, settings_page):
        """Test that client modal has save button."""
        settings_page.goto()
        settings_page.open_add_client_modal()
        
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_visible()


class TestConnectionModal:
    """Tests for connection add/edit modal."""
    
    def test_open_add_connection_modal(self, settings_page):
        """Test opening the add connection modal."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        
        settings_page.open_add_connection_modal()
        
        modal = settings_page.page.locator(settings_page.CONNECTION_MODAL)
        expect(modal).to_be_visible()
    
    def test_close_connection_modal(self, settings_page):
        """Test closing the connection modal."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        settings_page.close_connection_modal()
        
        modal = settings_page.page.locator(settings_page.CONNECTION_MODAL)
        expect(modal).to_be_hidden()
    
    def test_connection_modal_has_from_select(self, settings_page):
        """Test that connection modal has From client select."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        from_select = settings_page.page.locator(settings_page.CONNECTION_FROM_SELECT)
        expect(from_select).to_be_visible()
    
    def test_connection_modal_has_to_select(self, settings_page):
        """Test that connection modal has To client select."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        to_select = settings_page.page.locator(settings_page.CONNECTION_TO_SELECT)
        expect(to_select).to_be_visible()
    
    def test_connection_modal_has_save_button(self, settings_page):
        """Test that connection modal has save button."""
        settings_page.goto()
        settings_page.switch_to_connections_tab()
        settings_page.open_add_connection_modal()
        
        save_btn = settings_page.page.locator(settings_page.SAVE_CONNECTION_BTN)
        expect(save_btn).to_be_visible()


class TestSettingsNavigation:
    """Tests for navigation from settings page."""
    
    def test_navigate_to_dashboard_from_settings(self, settings_page):
        """Test navigating to dashboard from settings page."""
        settings_page.goto()
        
        settings_page.navigate_to_dashboard()
        
        expect(settings_page.page).to_have_url(f"{settings_page.base_url}/")
    
    def test_navigate_to_torrents_from_settings(self, settings_page):
        """Test navigating to torrents from settings page."""
        settings_page.goto()
        
        settings_page.navigate_to_torrents()
        
        expect(settings_page.page).to_have_url(f"{settings_page.base_url}/torrents")
    
    def test_sidebar_visible_on_settings(self, settings_page):
        """Test that sidebar is visible on settings page."""
        settings_page.goto()
        
        assert settings_page.is_sidebar_visible()
