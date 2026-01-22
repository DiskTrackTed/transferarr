"""
History page tests for Transferarr UI.

Tests for the Transfer History page including navigation, display,
filtering, pagination, and status badges.
"""
import re
import pytest
from playwright.sync_api import Page, expect

from tests.ui.helpers import UI_TIMEOUTS


class TestHistoryNavigation:
    """Tests for history page navigation and accessibility."""
    
    def test_history_in_sidebar(self, page: Page, base_url: str):
        """Test that History link appears in sidebar navigation."""
        page.goto(base_url)
        
        # History link should be visible in sidebar
        history_link = page.locator(".sidebar a[href='/history']")
        expect(history_link).to_be_visible()
        expect(history_link).to_contain_text("History")
    
    def test_history_page_loads(self, page: Page, base_url: str):
        """Test that history page loads successfully."""
        page.goto(f"{base_url}/history")
        
        # Page should load with correct title
        expect(page).to_have_title("Transferarr - History")
        expect(page.locator("h2")).to_contain_text("Transfer History")
    
    def test_navigate_to_history_via_sidebar(self, page: Page, base_url: str):
        """Test navigation to history page via sidebar link."""
        page.goto(base_url)
        
        # Click history link
        page.click(".sidebar a[href='/history']")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/history")
        expect(page.locator("h2")).to_contain_text("Transfer History")
    
    def test_history_nav_item_highlighted(self, page: Page, base_url: str):
        """Test that History is highlighted in sidebar when active."""
        page.goto(f"{base_url}/history")
        
        # History tab should be active
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("History")


class TestHistoryPageElements:
    """Tests for history page UI elements."""
    
    def test_history_stats_banner_visible(self, page: Page, base_url: str):
        """Test that stats banner is visible with all stat cards."""
        page.goto(f"{base_url}/history")
        
        # Stats container should be visible
        stats = page.locator("#history-stats")
        expect(stats).to_be_visible()
        
        # Should have 5 stat cards
        stat_cards = page.locator("#history-stats .stat-card")
        expect(stat_cards).to_have_count(5)
    
    def test_history_stats_labels(self, page: Page, base_url: str):
        """Test that stats have correct labels."""
        page.goto(f"{base_url}/history")
        
        # Check for expected stat labels
        expect(page.locator("#history-stats")).to_contain_text("Total Transfers")
        expect(page.locator("#history-stats")).to_contain_text("Completed")
        expect(page.locator("#history-stats")).to_contain_text("Failed")
        expect(page.locator("#history-stats")).to_contain_text("Success Rate")
        expect(page.locator("#history-stats")).to_contain_text("Data Transferred")
    
    def test_history_table_visible(self, page: Page, base_url: str):
        """Test that history table is visible."""
        page.goto(f"{base_url}/history")
        
        # Wait for table to be visible
        table = page.locator("#history-table")
        expect(table).to_be_visible()
    
    def test_history_shows_correct_columns(self, page: Page, base_url: str):
        """Test that table has correct column headers."""
        page.goto(f"{base_url}/history")
        
        # Check column headers
        headers = page.locator("#history-table thead th")
        expect(headers.nth(0)).to_contain_text("Name")
        expect(headers.nth(1)).to_contain_text("From")
        expect(headers.nth(2)).to_contain_text("Transferred")
        expect(headers.nth(3)).to_contain_text("Duration")
        expect(headers.nth(4)).to_contain_text("Status")
        expect(headers.nth(5)).to_contain_text("Date")
        expect(headers.nth(6)).to_contain_text("Actions")
    
    def test_history_pagination_controls(self, page: Page, base_url: str):
        """Test that pagination controls are visible."""
        page.goto(f"{base_url}/history")
        
        # Pagination container should exist
        pagination = page.locator("#pagination")
        expect(pagination).to_be_visible()
        
        # Should have prev/next buttons
        expect(page.locator("#btn-prev")).to_be_visible()
        expect(page.locator("#btn-next")).to_be_visible()
        
        # Should show page info
        expect(page.locator("#pagination")).to_contain_text("Page")


class TestHistoryFilters:
    """Tests for history page filtering functionality."""
    
    def test_filter_controls_visible(self, page: Page, base_url: str):
        """Test that filter controls are visible."""
        page.goto(f"{base_url}/history")
        
        # Filter controls should be visible
        expect(page.locator("#filter-status")).to_be_visible()
        expect(page.locator("#filter-source")).to_be_visible()
        expect(page.locator("#filter-target")).to_be_visible()
        expect(page.locator("#filter-search")).to_be_visible()
        expect(page.locator("#filter-from-date")).to_be_visible()
        expect(page.locator("#filter-to-date")).to_be_visible()
        expect(page.locator("#btn-clear-filters")).to_be_visible()
    
    def test_history_filter_by_status(self, page: Page, base_url: str):
        """Test filtering by status dropdown."""
        page.goto(f"{base_url}/history")
        
        # Wait for API response to complete
        page.wait_for_load_state("networkidle")
        
        # Select a status filter
        status_select = page.locator("#filter-status")
        status_select.select_option("completed")
        
        # Filter should be applied (API call made)
        # Wait for the network request
        page.wait_for_timeout(500)
        
        # Verify the filter is set
        expect(status_select).to_have_value("completed")
    
    def test_history_filter_by_client(self, page: Page, base_url: str):
        """Test filtering by source/target client dropdowns."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Source filter should be interactable
        source_select = page.locator("#filter-source")
        expect(source_select).to_be_visible()
        
        # Target filter should be interactable
        target_select = page.locator("#filter-target")
        expect(target_select).to_be_visible()
    
    def test_history_search_by_name(self, page: Page, base_url: str):
        """Test search input for filtering by name."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Type in search box
        search_input = page.locator("#filter-search")
        search_input.fill("test")
        
        # Wait for debounced search
        page.wait_for_timeout(500)
        
        # Verify input value
        expect(search_input).to_have_value("test")
    
    def test_history_clear_filters(self, page: Page, base_url: str):
        """Test clear filters button resets all filters."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Set some filters
        page.locator("#filter-status").select_option("completed")
        page.locator("#filter-search").fill("test")
        page.locator("#filter-from-date").fill("2025-01-01")
        page.locator("#filter-to-date").fill("2025-12-31")
        page.wait_for_timeout(500)
        
        # Click clear button
        page.click("#btn-clear-filters")
        page.wait_for_timeout(500)
        
        # Verify filters are cleared
        expect(page.locator("#filter-status")).to_have_value("")
        expect(page.locator("#filter-search")).to_have_value("")
        expect(page.locator("#filter-from-date")).to_have_value("")
        expect(page.locator("#filter-to-date")).to_have_value("")
    
    def test_history_date_filter_from(self, page: Page, base_url: str):
        """Test filtering by from date."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Set from date filter
        from_date_input = page.locator("#filter-from-date")
        from_date_input.fill("2025-01-01")
        
        page.wait_for_timeout(500)
        
        # Verify the filter is set
        expect(from_date_input).to_have_value("2025-01-01")
    
    def test_history_date_filter_to(self, page: Page, base_url: str):
        """Test filtering by to date."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Set to date filter
        to_date_input = page.locator("#filter-to-date")
        to_date_input.fill("2025-12-31")
        
        page.wait_for_timeout(500)
        
        # Verify the filter is set
        expect(to_date_input).to_have_value("2025-12-31")
    
    def test_history_date_range_filter(self, page: Page, base_url: str):
        """Test filtering by date range (both from and to)."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Set both date filters
        page.locator("#filter-from-date").fill("2025-01-01")
        page.locator("#filter-to-date").fill("2025-12-31")
        
        page.wait_for_timeout(500)
        
        # Verify both filters are set
        expect(page.locator("#filter-from-date")).to_have_value("2025-01-01")
        expect(page.locator("#filter-to-date")).to_have_value("2025-12-31")


class TestHistoryPagination:
    """Tests for history page pagination functionality."""
    
    def test_history_page_navigation(self, page: Page, base_url: str):
        """Test pagination page navigation buttons."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # On first page, prev should be disabled
        prev_btn = page.locator("#btn-prev")
        expect(prev_btn).to_be_disabled()
        
        # Current page should show 1
        expect(page.locator("#current-page")).to_contain_text("1")
    
    def test_pagination_info_displayed(self, page: Page, base_url: str):
        """Test that pagination info shows record counts."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Should show "Showing X-Y of Z"
        pagination_info = page.locator(".pagination-info")
        expect(pagination_info).to_be_visible()
        expect(pagination_info).to_contain_text("Showing")
        expect(pagination_info).to_contain_text("of")


class TestHistoryDataDisplay:
    """Tests for history data display with actual transfer records."""
    
    def test_history_shows_transfer_records(self, page: Page, base_url: str):
        """Test that transfer records are displayed (or empty state)."""
        page.goto(f"{base_url}/history")
        
        # Wait for data to load
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Extra time for API response
        
        # Should show either transfer rows or empty state
        table_body = page.locator("#history-tbody")
        empty_state = page.locator("#empty-state")
        
        # One of these should be visible/have content
        has_rows = table_body.locator("tr").count() > 0
        is_empty = empty_state.is_visible()
        
        # Either we have data or the empty state is shown
        assert has_rows or is_empty, "Expected either transfer records or empty state message"
    
    def test_history_status_badge_colors(self, page: Page, base_url: str):
        """Test that status badges have correct styling classes."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Status badges should use the .status-badge class
        # Check CSS is loaded by verifying badge styles exist
        completed_badge = page.locator(".status-badge.completed").first
        
        # If there are completed transfers, badge should have correct class
        if completed_badge.count() > 0:
            expect(completed_badge).to_be_visible()
    
    def test_history_table_sortable_columns(self, page: Page, base_url: str):
        """Test that sortable columns are clickable."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Sortable columns should have the sortable class
        sortable_headers = page.locator("th.sortable")
        expect(sortable_headers).to_have_count(3)  # Name, Size, Date
        
        # Should have sort icons
        expect(sortable_headers.first.locator("i")).to_be_visible()
    
    def test_history_column_sorting(self, page: Page, base_url: str):
        """Test that clicking a column header triggers sorting."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Click on the Date column header to sort
        date_header = page.locator("th.sortable[data-sort='created_at']")
        date_header.click()
        
        # Header should now have sort indicator class
        page.wait_for_timeout(500)
        expect(date_header).to_have_class(re.compile(r"sort-(asc|desc)"))


class TestHistoryEmptyState:
    """Tests for empty state behavior."""
    
    def test_empty_state_message(self, page: Page, base_url: str):
        """Test that empty state has appropriate message."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # If no data, empty state should show
        empty_state = page.locator("#empty-state")
        
        if empty_state.is_visible():
            expect(empty_state).to_contain_text("No transfer history")
    
    def test_empty_state_icon(self, page: Page, base_url: str):
        """Test that empty state has history icon."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        empty_state = page.locator("#empty-state")
        
        if empty_state.is_visible():
            icon = empty_state.locator("i.fa-history")
            expect(icon).to_be_visible()


class TestHistoryLoadingState:
    """Tests for loading state behavior."""
    
    def test_loading_indicator_exists(self, page: Page, base_url: str):
        """Test that loading indicator element exists."""
        page.goto(f"{base_url}/history")
        
        # Loading indicator element should exist (may be hidden after load)
        loading = page.locator("#loading-indicator")
        expect(loading).to_be_attached()


@pytest.mark.timeout(360)  # 6 minutes for transfer + tests
class TestHistoryDeleteFeatures:
    """Tests for history delete UI features that require transfer history data.
    
    This class uses a module-scoped fixture to run one real transfer before
    the tests, ensuring organic history data exists for testing delete functionality.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, transfer_history_data):
        """Auto-use the transfer history data fixture for all tests in this class.
        
        The transfer_history_data fixture (module-scoped) runs a real transfer
        once before any test in this module, creating organic history data.
        """
        pass
    
    def test_clear_history_button_exists(self, page: Page, base_url: str):
        """Test that Clear History button is visible."""
        page.goto(f"{base_url}/history")
        
        clear_btn = page.locator("#btn-clear-history")
        expect(clear_btn).to_be_visible()
        expect(clear_btn).to_contain_text("Clear History")
    
    def test_clear_history_modal_appears(self, page: Page, base_url: str):
        """Test that clicking Clear History shows confirmation modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Click clear history button
        page.click("#btn-clear-history")
        
        # Modal should appear
        modal = page.locator("#clear-history-modal")
        expect(modal).to_be_visible()
        
        # Modal should have confirmation text
        expect(modal).to_contain_text("Are you sure")
        expect(modal).to_contain_text("clear the transfer history")
    
    def test_clear_history_modal_cancel(self, page: Page, base_url: str):
        """Test that Cancel button closes the clear history modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        page.click("#btn-clear-history")
        expect(page.locator("#clear-history-modal")).to_be_visible()
        
        # Click cancel
        page.click("#clear-modal-cancel")
        
        # Modal should be hidden
        expect(page.locator("#clear-history-modal")).to_be_hidden()
    
    def test_clear_history_modal_close_button(self, page: Page, base_url: str):
        """Test that X button closes the clear history modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        page.click("#btn-clear-history")
        expect(page.locator("#clear-history-modal")).to_be_visible()
        
        # Click close button
        page.click("#clear-modal-close")
        
        # Modal should be hidden
        expect(page.locator("#clear-history-modal")).to_be_hidden()
    
    def test_clear_history_modal_overlay_click(self, page: Page, base_url: str):
        """Test that clicking overlay closes the clear history modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        page.click("#btn-clear-history")
        expect(page.locator("#clear-history-modal")).to_be_visible()
        
        # Click on the overlay (outside the modal content)
        # Use force click at the edge of the overlay
        page.locator("#clear-history-modal").click(position={"x": 10, "y": 10})
        
        # Modal should be hidden
        expect(page.locator("#clear-history-modal")).to_be_hidden()
    
    def test_actions_column_exists(self, page: Page, base_url: str):
        """Test that Actions column header exists in table."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # Check for Actions column header
        actions_header = page.locator("th.actions-col")
        expect(actions_header).to_be_visible()
        expect(actions_header).to_contain_text("Actions")
    
    def test_delete_buttons_on_completed_transfers(self, page: Page, base_url: str):
        """Test that delete buttons appear on completed/failed transfer rows."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        # With transfer_history_setup fixture, we should have at least one row
        delete_buttons = page.locator(".btn-delete-transfer")
        expect(delete_buttons.first).to_be_visible()
    
    def test_delete_button_opens_confirmation(self, page: Page, base_url: str):
        """Test that clicking delete button shows confirmation modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        delete_buttons = page.locator(".btn-delete-transfer")
        
        # Click first delete button
        delete_buttons.first.click()
        
        # Modal should appear
        modal = page.locator("#delete-transfer-modal")
        expect(modal).to_be_visible()
        expect(modal).to_contain_text("Are you sure")
        expect(modal).to_contain_text("delete this transfer record")
    
    def test_delete_modal_shows_torrent_name(self, page: Page, base_url: str):
        """Test that delete modal shows the torrent name being deleted."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        delete_buttons = page.locator(".btn-delete-transfer")
        
        # Get torrent name from button data attribute
        expected_name = delete_buttons.first.get_attribute("data-name")
        
        # Click delete button
        delete_buttons.first.click()
        
        # Modal should show the torrent name
        torrent_name_elem = page.locator("#delete-torrent-name")
        expect(torrent_name_elem).to_have_text(expected_name)
    
    def test_delete_modal_cancel(self, page: Page, base_url: str):
        """Test that Cancel button closes delete modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        delete_buttons = page.locator(".btn-delete-transfer")
        
        # Open modal
        delete_buttons.first.click()
        expect(page.locator("#delete-transfer-modal")).to_be_visible()
        
        # Click cancel
        page.click("#delete-modal-cancel")
        
        # Modal should be hidden
        expect(page.locator("#delete-transfer-modal")).to_be_hidden()
    
    def test_delete_modal_close_button(self, page: Page, base_url: str):
        """Test that X button closes delete modal."""
        page.goto(f"{base_url}/history")
        page.wait_for_load_state("networkidle")
        
        delete_buttons = page.locator(".btn-delete-transfer")
        
        # Open modal
        delete_buttons.first.click()
        expect(page.locator("#delete-transfer-modal")).to_be_visible()
        
        # Click close button
        page.click("#delete-modal-close")
        
        # Modal should be hidden
        expect(page.locator("#delete-transfer-modal")).to_be_hidden()
