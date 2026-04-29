"""
Torrents page object for UI testing.

The torrents page displays:
- Client tabs for each download client
- Torrent lists per client with state indicators
- Torrent selection checkboxes and transfer button
- Transfer modal for manual transfers
"""
from urllib.parse import quote

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
    CLIENT_ERROR_MESSAGE = ".client-error-message"
    NO_CLIENTS_MESSAGE = ".no-clients-message"
    
    # Selection selectors
    TORRENT_CHECKBOX = ".torrent-checkbox"
    TORRENT_CHECKBOX_WRAPPER = ".torrent-checkbox-wrapper"
    CROSS_SEED_BADGE = ".cross-seed-badge"
    TRANSFER_BUTTON = "#transfer-selected-btn"
    SELECTED_COUNT = "#selected-count"
    
    # Inline per-torrent transfer button
    TORRENT_TRANSFER_BTN = ".torrent-transfer-btn"
    TORRENT_ACTION_WRAPPER = ".torrent-action-wrapper"
    
    # Transfer modal selectors
    TRANSFER_MODAL = "#transferModal"
    MODAL_CLOSE_BTN = "#transferModalClose"
    MODAL_CANCEL_BTN = "#transferModalCancel"
    CONFIRM_TRANSFER_BTN = "#confirmTransferBtn"
    DESTINATION_SELECT = "#destinationClient"
    INCLUDE_CROSS_SEEDS = "#includeCrossSeeds"
    MODAL_SELECTED_COUNT = "#modal-selected-count"
    TRANSFER_TORRENT_LIST = "#transfer-torrent-list"
    TRANSFER_LIST_ITEM = ".transfer-list-item"
    CROSS_SEED_DIVIDER = ".cross-seed-divider"
    TRANSFER_ERROR = "#transfer-error"
    CROSS_SEED_WARNING = "#cross-seed-warning"
    DELETE_CROSS_SEEDS = "#deleteCrossSeeds"
    ORIGINAL_BADGE = ".original-badge"
    SELECTED_BADGE = ".selected-badge"
    ACTION_BADGE = ".action-badge"
    ACTION_BADGE_TRANSFER = ".action-badge-transfer"
    ACTION_BADGE_DELETE = ".action-badge-delete"
    ACTION_BADGE_NONE = ".action-badge-none"
    CROSS_SEED_INACTIVE = ".cross-seed-inactive"
    TRANSFER_ITEM_NAME_TEXT = ".transfer-item-name-text"
    TRANSFER_ITEM_TRACKER = ".transfer-item-tracker"
    TRANSFER_ITEM_BADGES = ".transfer-item-badges"
    
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
    
    def wait_for_api_refresh(self, client_name: str | None = None, timeout: int = 15000) -> None:
        """Wait for next API poll.
        
        Torrents page polls /api/v1/clients/<client>/torrents every 10 seconds.
        
        Args:
            client_name: Expected client name. Defaults to the active tab.
            timeout: Maximum time to wait in milliseconds
            
        Raises:
            playwright.sync_api.TimeoutError: If no API response within timeout
        """
        active_client = client_name or self.get_active_client_tab()
        if active_client:
            encoded_name = quote(active_client, safe='')
            matcher = lambda r: f"/api/v1/clients/{encoded_name}/torrents" in r.url
        else:
            matcher = lambda r: "/api/v1/clients/" in r.url and r.url.endswith("/torrents")

        with self.page.expect_response(matcher, timeout=timeout):
            pass  # Wait for next poll cycle

    def has_client_error_message(self) -> bool:
        """Check if a client-level error message is visible in the active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.CLIENT_ERROR_MESSAGE}"
        ).is_visible()

    def has_no_clients_message(self) -> bool:
        """Check if the page shows the no-clients-configured state."""
        return self.page.locator(self.NO_CLIENTS_MESSAGE).is_visible()

    # ===================================================================
    # Selection helpers
    # ===================================================================

    def get_torrent_checkboxes(self):
        """Get all torrent checkboxes in the active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_CHECKBOX}"
        ).all()

    def get_enabled_checkboxes(self):
        """Get checkboxes that are not disabled (seeding torrents only)."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_CHECKBOX}:not(:disabled)"
        ).all()

    def select_torrent_by_index(self, index: int) -> None:
        """Click the checkbox of the Nth torrent card in the active tab.
        
        Args:
            index: Zero-based index of the torrent to select
        """
        cb = self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_CHECKBOX}"
        ).nth(index)
        cb.click()

    def select_torrent_by_hash(self, torrent_hash: str) -> None:
        """Click the checkbox of a torrent identified by hash.
        
        Args:
            torrent_hash: The torrent info-hash (used as data-hash attribute)
        """
        cb = self.page.locator(
            f"{self.TORRENT_CHECKBOX}[data-hash='{torrent_hash}']"
        )
        cb.click()

    def get_selected_count(self) -> int:
        """Get the number shown in the transfer button badge."""
        return int(self.page.locator(self.SELECTED_COUNT).text_content())

    def is_transfer_button_visible(self) -> bool:
        """Check if the Transfer Selected button is visible."""
        btn = self.page.locator(self.TRANSFER_BUTTON)
        # The button uses visibility:hidden when count==0 (keeps layout space)
        return btn.is_visible()

    def is_transfer_button_enabled(self) -> bool:
        """Check if the Transfer Selected button is enabled."""
        return self.page.locator(self.TRANSFER_BUTTON).is_enabled()

    def click_transfer_button(self) -> None:
        """Click the Transfer Selected button to open the modal."""
        self.page.locator(self.TRANSFER_BUTTON).click()

    def get_selected_cards(self):
        """Get torrent cards that have the 'selected' CSS class."""
        return self.page.locator(f"{self.TORRENT_CARD}.selected").all()

    def get_cross_seed_badges(self):
        """Get all visible cross-seed badges."""
        return self.page.locator(self.CROSS_SEED_BADGE).all()

    # ===================================================================
    # Inline transfer button helpers
    # ===================================================================

    def get_inline_transfer_buttons(self):
        """Get all visible inline transfer buttons in the active tab."""
        return self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_TRANSFER_BTN}"
        ).all()

    def click_inline_transfer_button(self, index: int = 0) -> None:
        """Click the inline transfer button on the Nth torrent card.
        
        Args:
            index: Zero-based index among visible inline transfer buttons
        """
        self.page.locator(
            f"{self.CLIENT_TAB_CONTENT}.active {self.TORRENT_TRANSFER_BTN}"
        ).nth(index).click()

    def click_inline_transfer_on_card(self, card_locator) -> None:
        """Click the inline transfer button within a specific torrent card.
        
        Args:
            card_locator: A Playwright Locator pointing to a .simple-torrent-card
        """
        card_locator.locator(self.TORRENT_TRANSFER_BTN).click()

    # ===================================================================
    # Transfer modal helpers
    # ===================================================================

    def is_modal_visible(self) -> bool:
        """Check if the transfer modal is visible (has 'show' class)."""
        return self.page.locator(f"{self.TRANSFER_MODAL}.show").count() > 0

    def close_modal(self) -> None:
        """Close the modal via the X button."""
        self.page.locator(self.MODAL_CLOSE_BTN).click()

    def cancel_modal(self) -> None:
        """Close the modal via the Cancel button."""
        self.page.locator(self.MODAL_CANCEL_BTN).click()

    def get_modal_selected_count(self) -> int:
        """Get the selected-count shown inside the modal body."""
        return int(self.page.locator(self.MODAL_SELECTED_COUNT).text_content())

    def get_destination_options(self) -> list[str]:
        """Get the text of all destination dropdown options (excluding placeholder)."""
        options = self.page.locator(f"{self.DESTINATION_SELECT} option").all()
        return [
            o.text_content().strip()
            for o in options
            if o.get_attribute("value")
        ]

    def select_destination(self, client_name: str) -> None:
        """Select a destination client from the dropdown.
        
        Args:
            client_name: The value (client name) to select
        """
        self.page.select_option(self.DESTINATION_SELECT, client_name)

    def is_cross_seeds_checked(self) -> bool:
        """Check if the Include Cross-Seeds checkbox is checked."""
        return self.page.locator(self.INCLUDE_CROSS_SEEDS).is_checked()

    def toggle_cross_seeds(self) -> None:
        """Toggle the Include Cross-Seeds checkbox."""
        self.page.locator(self.INCLUDE_CROSS_SEEDS).click()

    def get_transfer_list_items(self):
        """Get all torrent list items inside the modal."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.TRANSFER_LIST_ITEM}"
        ).all()

    def is_confirm_button_enabled(self) -> bool:
        """Check if the Start Transfer button is enabled."""
        return self.page.locator(self.CONFIRM_TRANSFER_BTN).is_enabled()

    def click_confirm_transfer(self) -> None:
        """Click the Start Transfer confirmation button."""
        self.page.locator(self.CONFIRM_TRANSFER_BTN).click()

    def get_transfer_error(self) -> str:
        """Get the text of the error message in the modal (empty if hidden)."""
        el = self.page.locator(self.TRANSFER_ERROR)
        if el.is_visible():
            return el.text_content().strip()
        return ""

    def is_transfer_error_visible(self) -> bool:
        """Check if the transfer error alert is displayed."""
        return self.page.locator(self.TRANSFER_ERROR).is_visible()

    def is_cross_seed_warning_visible(self) -> bool:
        """Check if the cross-seed warning alert is displayed."""
        return self.page.locator(self.CROSS_SEED_WARNING).is_visible()

    def get_cross_seed_warning_text(self) -> str:
        """Get the text of the cross-seed warning (empty if hidden)."""
        el = self.page.locator(self.CROSS_SEED_WARNING)
        if el.is_visible():
            return el.text_content().strip()
        return ""

    def is_delete_cross_seeds_checked(self) -> bool:
        """Check if the Delete Cross-Seeds checkbox is checked."""
        return self.page.locator(self.DELETE_CROSS_SEEDS).is_checked()

    def is_delete_cross_seeds_visible(self) -> bool:
        """Check if the Delete Cross-Seeds form group is visible."""
        group = self.page.locator(
            f"{self.DELETE_CROSS_SEEDS}"
        ).locator("xpath=ancestor::div[contains(@class,'form-group')]")
        return group.is_visible()

    def toggle_delete_cross_seeds(self) -> None:
        """Toggle the Delete Cross-Seeds checkbox."""
        self.page.locator(self.DELETE_CROSS_SEEDS).click()

    def get_original_badges(self):
        """Get all original-badge elements inside the transfer list."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.ORIGINAL_BADGE}"
        ).all()

    def get_selected_badges(self):
        """Get all selected-badge elements inside the transfer list."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.SELECTED_BADGE}"
        ).all()

    def get_action_badges(self, badge_type=None):
        """Get action badge elements inside the transfer list.

        Args:
            badge_type: Optional filter — 'transfer', 'delete', or 'none'.
                        If None, returns all action badges.
        """
        if badge_type == 'transfer':
            selector = self.ACTION_BADGE_TRANSFER
        elif badge_type == 'delete':
            selector = self.ACTION_BADGE_DELETE
        elif badge_type == 'none':
            selector = self.ACTION_BADGE_NONE
        else:
            selector = self.ACTION_BADGE
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {selector}"
        ).all()

    def get_cross_seed_list_items(self):
        """Get cross-seed items (with .cross-seed-item class) from the transfer list."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} .cross-seed-item"
        ).all()

    def get_inactive_cross_seed_items(self):
        """Get dimmed/inactive cross-seed items from the transfer list."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.CROSS_SEED_INACTIVE}"
        ).all()

    def get_tracker_labels(self):
        """Get all tracker label elements inside the transfer list."""
        return self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.TRANSFER_ITEM_TRACKER}"
        ).all()

    def get_name_tooltips(self):
        """Get the title attributes from transfer item name texts.

        Returns:
            List of tooltip strings (one per transfer list item)
        """
        elements = self.page.locator(
            f"{self.TRANSFER_TORRENT_LIST} {self.TRANSFER_ITEM_NAME_TEXT}"
        ).all()
        return [el.get_attribute("title") or "" for el in elements]
