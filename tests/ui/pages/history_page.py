"""
History page object for UI testing.

The history page displays:
- Stats banner (total, completed, failed, success rate, data transferred)
- Filters (status, source, target, search)
- Transfer history table with pagination
"""
from playwright.sync_api import Page, expect, Locator
from .base_page import BasePage


class HistoryPage(BasePage):
    """Page object for the Transfer History page."""
    
    # Stats selectors
    STATS_CONTAINER = "#history-stats"
    STAT_CARD = ".stat-card"
    STAT_TOTAL = "#stat-total"
    STAT_COMPLETED = "#stat-completed"
    STAT_FAILED = "#stat-failed"
    STAT_SUCCESS_RATE = "#stat-success-rate"
    STAT_TOTAL_BYTES = "#stat-total-bytes"
    
    # Filter selectors
    FILTERS_CARD = ".filters-card"
    FILTER_STATUS = "#filter-status"
    FILTER_SOURCE = "#filter-source"
    FILTER_TARGET = "#filter-target"
    FILTER_SEARCH = "#filter-search"
    FILTER_FROM_DATE = "#filter-from-date"
    FILTER_TO_DATE = "#filter-to-date"
    BTN_CLEAR_FILTERS = "#btn-clear-filters"
    
    # Table selectors
    HISTORY_TABLE = "#history-table"
    TABLE_BODY = "#history-tbody"
    TABLE_ROW = "#history-tbody tr"
    SORTABLE_HEADER = "th.sortable"
    BTN_DELETE_TRANSFER = ".btn-delete-transfer"
    ACTIONS_COL = ".actions-col"
    
    # State selectors
    LOADING_INDICATOR = "#loading-indicator"
    EMPTY_STATE = "#empty-state"
    
    # Pagination selectors
    PAGINATION = "#pagination"
    BTN_PREV = "#btn-prev"
    BTN_NEXT = "#btn-next"
    CURRENT_PAGE = "#current-page"
    TOTAL_PAGES = "#total-pages"
    SHOWING_START = "#showing-start"
    SHOWING_END = "#showing-end"
    TOTAL_COUNT = "#total-count"
    
    # Clear History selectors
    BTN_CLEAR_HISTORY = "#btn-clear-history"
    CLEAR_HISTORY_MODAL = "#clear-history-modal"
    CLEAR_MODAL_CANCEL = "#clear-modal-cancel"
    CLEAR_MODAL_CONFIRM = "#clear-modal-confirm"
    CLEAR_MODAL_CLOSE = "#clear-modal-close"
    
    # Delete Transfer Modal selectors
    DELETE_TRANSFER_MODAL = "#delete-transfer-modal"
    DELETE_MODAL_CANCEL = "#delete-modal-cancel"
    DELETE_MODAL_CONFIRM = "#delete-modal-confirm"
    DELETE_MODAL_CLOSE = "#delete-modal-close"
    DELETE_TORRENT_NAME = "#delete-torrent-name"
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
    
    def goto(self) -> None:
        """Navigate to history page and verify it loaded."""
        super().goto("/history")
        expect(self.page.locator("h2").first).to_contain_text("Transfer History")
    
    # === Stats Methods ===
    
    def get_total_transfers(self) -> int:
        """Get total transfers count from stats."""
        text = self.page.locator(self.STAT_TOTAL).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_completed_count(self) -> int:
        """Get completed transfers count from stats."""
        text = self.page.locator(self.STAT_COMPLETED).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_failed_count(self) -> int:
        """Get failed transfers count from stats."""
        text = self.page.locator(self.STAT_FAILED).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def get_success_rate(self) -> str:
        """Get success rate string from stats."""
        return self.page.locator(self.STAT_SUCCESS_RATE).text_content() or "0%"
    
    def get_data_transferred(self) -> str:
        """Get total data transferred string from stats."""
        return self.page.locator(self.STAT_TOTAL_BYTES).text_content() or "0 B"
    
    def get_all_stats(self) -> dict:
        """Get all stats as a dictionary."""
        return {
            "total": self.get_total_transfers(),
            "completed": self.get_completed_count(),
            "failed": self.get_failed_count(),
            "success_rate": self.get_success_rate(),
            "data_transferred": self.get_data_transferred()
        }
    
    # === Filter Methods ===
    
    def set_status_filter(self, status: str) -> None:
        """Set the status filter dropdown."""
        self.page.locator(self.FILTER_STATUS).select_option(status)
    
    def set_source_filter(self, source: str) -> None:
        """Set the source client filter dropdown."""
        self.page.locator(self.FILTER_SOURCE).select_option(source)
    
    def set_target_filter(self, target: str) -> None:
        """Set the target client filter dropdown."""
        self.page.locator(self.FILTER_TARGET).select_option(target)
    
    def set_search_filter(self, search: str) -> None:
        """Set the search filter input."""
        self.page.locator(self.FILTER_SEARCH).fill(search)
    
    def set_from_date_filter(self, date: str) -> None:
        """Set the from date filter (YYYY-MM-DD format)."""
        self.page.locator(self.FILTER_FROM_DATE).fill(date)
    
    def set_to_date_filter(self, date: str) -> None:
        """Set the to date filter (YYYY-MM-DD format)."""
        self.page.locator(self.FILTER_TO_DATE).fill(date)
    
    def clear_filters(self) -> None:
        """Click the clear filters button."""
        self.page.click(self.BTN_CLEAR_FILTERS)
    
    def get_current_filters(self) -> dict:
        """Get current filter values."""
        return {
            "status": self.page.locator(self.FILTER_STATUS).input_value(),
            "source": self.page.locator(self.FILTER_SOURCE).input_value(),
            "target": self.page.locator(self.FILTER_TARGET).input_value(),
            "search": self.page.locator(self.FILTER_SEARCH).input_value(),
            "from_date": self.page.locator(self.FILTER_FROM_DATE).input_value(),
            "to_date": self.page.locator(self.FILTER_TO_DATE).input_value()
        }
    
    # === Table Methods ===
    
    def get_row_count(self) -> int:
        """Get the number of rows in the history table."""
        return self.page.locator(self.TABLE_ROW).count()
    
    def get_rows(self) -> Locator:
        """Get all table rows as a locator."""
        return self.page.locator(self.TABLE_ROW)
    
    def is_empty_state_visible(self) -> bool:
        """Check if empty state message is visible."""
        return self.page.locator(self.EMPTY_STATE).is_visible()
    
    def is_loading(self) -> bool:
        """Check if loading indicator is visible."""
        return self.page.locator(self.LOADING_INDICATOR).is_visible()
    
    def sort_by(self, column: str) -> None:
        """Click a sortable column header to sort.
        
        Args:
            column: Column name (torrent_name, size_bytes, created_at)
        """
        self.page.click(f"th.sortable[data-sort='{column}']")
    
    # === Pagination Methods ===
    
    def get_current_page(self) -> int:
        """Get current page number."""
        text = self.page.locator(self.CURRENT_PAGE).text_content()
        try:
            return int(text) if text else 1
        except ValueError:
            return 1
    
    def get_total_pages(self) -> int:
        """Get total pages count."""
        text = self.page.locator(self.TOTAL_PAGES).text_content()
        try:
            return int(text) if text else 1
        except ValueError:
            return 1
    
    def get_total_record_count(self) -> int:
        """Get total record count from pagination info."""
        text = self.page.locator(self.TOTAL_COUNT).text_content()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0
    
    def go_to_next_page(self) -> None:
        """Click next page button."""
        self.page.click(self.BTN_NEXT)
    
    def go_to_prev_page(self) -> None:
        """Click previous page button."""
        self.page.click(self.BTN_PREV)
    
    def is_prev_enabled(self) -> bool:
        """Check if previous button is enabled."""
        return not self.page.locator(self.BTN_PREV).is_disabled()
    
    def is_next_enabled(self) -> bool:
        """Check if next button is enabled."""
        return not self.page.locator(self.BTN_NEXT).is_disabled()
    
    # === Delete Methods ===
    
    def click_clear_history_button(self) -> None:
        """Click the Clear History button."""
        self.page.click(self.BTN_CLEAR_HISTORY)
    
    def is_clear_history_modal_visible(self) -> bool:
        """Check if clear history modal is visible."""
        modal = self.page.locator(self.CLEAR_HISTORY_MODAL)
        return modal.is_visible() and modal.evaluate("el => el.style.display !== 'none'")
    
    def confirm_clear_history(self) -> None:
        """Click confirm button in clear history modal."""
        self.page.click(self.CLEAR_MODAL_CONFIRM)
    
    def cancel_clear_history(self) -> None:
        """Click cancel button in clear history modal."""
        self.page.click(self.CLEAR_MODAL_CANCEL)
    
    def close_clear_history_modal(self) -> None:
        """Click close button in clear history modal."""
        self.page.click(self.CLEAR_MODAL_CLOSE)
    
    def get_delete_buttons(self) -> "Locator":
        """Get all delete buttons in the table."""
        return self.page.locator(self.BTN_DELETE_TRANSFER)
    
    def click_delete_for_row(self, row_index: int = 0) -> None:
        """Click delete button for a specific row.
        
        Args:
            row_index: Zero-based index of the row to delete
        """
        buttons = self.page.locator(self.BTN_DELETE_TRANSFER)
        buttons.nth(row_index).click()
    
    def is_delete_transfer_modal_visible(self) -> bool:
        """Check if delete transfer modal is visible."""
        modal = self.page.locator(self.DELETE_TRANSFER_MODAL)
        return modal.is_visible() and modal.evaluate("el => el.style.display !== 'none'")
    
    def get_delete_modal_torrent_name(self) -> str:
        """Get the torrent name shown in delete confirmation modal."""
        return self.page.locator(self.DELETE_TORRENT_NAME).text_content() or ""
    
    def confirm_delete_transfer(self) -> None:
        """Click confirm button in delete transfer modal."""
        self.page.click(self.DELETE_MODAL_CONFIRM)
    
    def cancel_delete_transfer(self) -> None:
        """Click cancel button in delete transfer modal."""
        self.page.click(self.DELETE_MODAL_CANCEL)
    
    def close_delete_transfer_modal(self) -> None:
        """Click close button in delete transfer modal."""
        self.page.click(self.DELETE_MODAL_CLOSE)
    
    # === Convenience Methods ===
    
    def wait_for_data(self, timeout: int = 5000) -> None:
        """Wait for table data to load (loading indicator hidden)."""
        self.page.locator(self.LOADING_INDICATOR).wait_for(state="hidden", timeout=timeout)
