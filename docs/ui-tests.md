# UI Tests

*Last Updated: 2026-01-19*

## Overview

Playwright-based UI tests using the Page Object Model pattern. Tests run in Docker with Chromium (headless by default).

## Directory Structure

```
tests/ui/
    auth/                   # Authentication tests (~25 min)
        test_login_page.py
        test_setup_page.py
        test_login_logout.py
        test_settings_auth.py
    fast/                   # UI-only tests (~5 min)
        test_navigation.py
        test_dashboard.py
        test_torrents.py
        test_settings.py
        test_history.py
    crud/                   # CRUD operations (~8 min)
        test_client_crud.py
        test_connection_crud.py
    e2e/                    # Real transfers (~15 min)
        test_e2e_workflows.py
        test_smoke.py
        test_transfer_types.py
    pages/                  # Page objects
    conftest.py
    helpers.py
```

## Running Tests

```bash
# Run all UI tests
./run_tests.sh tests/ui/ -v

# Run specific category
./run_tests.sh tests/ui/auth/ -v
./run_tests.sh tests/ui/fast/ -v
./run_tests.sh tests/ui/crud/ -v
./run_tests.sh tests/ui/e2e/ -v

# Run specific file
./run_tests.sh tests/ui/fast/test_dashboard.py -v

# Run with screenshots on failure (default)
./run_tests.sh tests/ui/ -v --screenshot=only-on-failure
```

Test artifacts (screenshots, traces) are saved to `test-results/` (gitignored).

## Test Files

### auth/

#### [test_login_page.py](../tests/ui/auth/test_login_page.py)
Login page elements, interactions, form validation, and successful login flows.

**TestLoginPageElements** - Login page UI elements present and styled:

| Test | Description |
|------|-------------|
| `test_login_page_loads` | Page loads with correct title |
| `test_login_container_visible` | Login container is visible |
| `test_login_card_visible` | Login card is visible |
| `test_logo_displays_transferarr` | Logo displays 'Transferarr' |
| `test_subtitle_displays_sign_in` | Subtitle shows sign in message |
| `test_username_field_visible` | Username input field is visible |
| `test_password_field_visible` | Password input field is visible |
| `test_remember_checkbox_visible` | Remember me checkbox is visible |
| `test_submit_button_visible` | Sign in button is visible |
| `test_version_displayed_in_footer` | Version number displayed in footer |

**TestLoginPageInteractions** - Login form interactions:

| Test | Description |
|------|-------------|
| `test_can_type_in_username_field` | Can type in username field |
| `test_can_type_in_password_field` | Can type in password field |
| `test_can_check_remember_me` | Can check remember me checkbox |
| `test_can_uncheck_remember_me` | Can uncheck remember me checkbox |

**TestLoginFormValidation** - Login form validation:

| Test | Description |
|------|-------------|
| `test_invalid_credentials_shows_error` | Invalid credentials show error |
| `test_empty_username_shows_error` | Empty username shows error |
| `test_empty_password_shows_error` | Empty password shows error |

**TestSuccessfulLogin** - Successful login flows:

| Test | Description |
|------|-------------|
| `test_successful_login_redirects_to_dashboard` | Login redirects to dashboard |
| `test_login_preserves_next_parameter` | Login redirects to 'next' URL |
| `test_logged_in_user_sees_sidebar` | After login, sidebar shows user info |
| `test_logged_in_user_sees_logout_link` | After login, logout link visible |

#### [test_setup_page.py](../tests/ui/auth/test_setup_page.py)
Setup page elements, interactions, form validation, account creation, and skip flows.

**TestSetupPageElements** - Setup page UI elements:

| Test | Description |
|------|-------------|
| `test_setup_page_loads` | Page loads with correct title |
| `test_setup_container_visible` | Setup container is visible |
| `test_setup_card_visible` | Setup card is visible |
| `test_logo_displays_transferarr` | Logo displays 'Transferarr' |
| `test_subtitle_displays_setup_message` | Subtitle shows setup message |
| `test_username_field_visible` | Username field is visible |
| `test_password_field_visible` | Password field is visible |
| `test_confirm_password_field_visible` | Confirm password field is visible |
| `test_create_button_visible` | Create account button is visible |
| `test_skip_button_visible` | Skip setup button is visible |
| `test_version_displayed_in_footer` | Version number displayed in footer |

**TestSetupPageInteractions** - Setup form interactions:

| Test | Description |
|------|-------------|
| `test_can_type_in_username_field` | Can type in username field |
| `test_can_type_in_password_field` | Can type in password field |
| `test_can_type_in_confirm_password_field` | Can type in confirm password field |

**TestSetupFormValidation** - Setup form validation:

| Test | Description |
|------|-------------|
| `test_password_mismatch_shows_error` | Password mismatch shows error |
| `test_empty_username_shows_error` | Empty username shows error |
| `test_empty_password_shows_error` | Empty password shows error |

**TestSuccessfulSetup** - Successful setup flows:

| Test | Description |
|------|-------------|
| `test_successful_setup_redirects_to_dashboard` | Account creation redirects to dashboard |
| `test_created_user_is_logged_in` | After setup, user is logged in |

**TestSkipSetup** - Skip setup flows:

| Test | Description |
|------|-------------|
| `test_skip_button_redirects_to_dashboard` | Skip redirects to dashboard |
| `test_skip_disables_auth` | Skipping disables auth |
| `test_after_skip_can_access_pages_directly` | After skip, pages accessible |

#### [test_login_logout.py](../tests/ui/auth/test_login_logout.py)
Complete login/logout workflows including session persistence and protected routes.

**TestLogoutFlow** - Logout functionality:

| Test | Description |
|------|-------------|
| `test_logout_link_in_sidebar` | Logout link appears after login |
| `test_click_logout_redirects_to_login` | Clicking logout redirects to login |
| `test_after_logout_cannot_access_protected_pages` | After logout, protected pages redirect |
| `test_logout_clears_session` | Logout clears session completely |

**TestLoginPersistence** - Session persistence:

| Test | Description |
|------|-------------|
| `test_session_persists_across_page_reload` | Session persists on reload |
| `test_session_persists_across_navigation` | Session persists across pages |

**TestProtectedRouteRedirects** - Protected route behavior:

| Test | Description |
|------|-------------|
| `test_dashboard_redirects_to_login` | Dashboard redirects when not logged in |
| `test_torrents_redirects_to_login` | Torrents redirects when not logged in |
| `test_settings_redirects_to_login` | Settings redirects when not logged in |
| `test_history_redirects_to_login` | History redirects when not logged in |
| `test_redirect_preserves_original_url` | Redirect preserves original URL |
| `test_after_login_returns_to_original_page` | After login, returns to original page |

**TestSidebarUserInfo** - Sidebar user info display:

| Test | Description |
|------|-------------|
| `test_username_displayed_in_sidebar` | Username displayed in sidebar |
| `test_user_icon_visible` | User icon visible in sidebar |
| `test_logout_icon_visible` | Logout icon visible in sidebar |

**TestAuthDisabledUI** - Auth disabled behavior:

| Test | Description |
|------|-------------|
| `test_no_user_info_when_auth_disabled` | No user info when auth disabled |
| `test_no_logout_link_when_auth_disabled` | No logout link when auth disabled |
| `test_can_access_all_pages_without_login` | All pages accessible without login |
| `test_login_page_redirects_when_auth_disabled` | Login page redirects when auth disabled |

#### [test_settings_auth.py](../tests/ui/auth/test_settings_auth.py)
Settings page Auth tab elements, interactions, save/password changes.

**TestAuthTabElements** - Auth tab UI elements present:

| Test | Description |
|------|-------------|
| `test_auth_tab_exists` | Auth tab exists in settings |
| `test_auth_tab_can_be_selected` | Can switch to Auth tab |
| `test_auth_enabled_toggle_visible` | Auth enabled toggle is visible |
| `test_session_timeout_dropdown_visible` | Session timeout dropdown is visible |
| `test_change_password_section_visible` | Change password section is visible |
| `test_save_button_visible` | Save Auth Settings button is visible |
| `test_auth_tab_content_hidden_initially` | Auth content hidden when tab not active |

**TestAuthTabInteractions** - Auth tab form interactions:

| Test | Description |
|------|-------------|
| `test_can_toggle_auth_enabled` | Can toggle auth enabled switch |
| `test_can_change_session_timeout` | Can change session timeout dropdown |
| `test_restart_warning_hidden_by_default` | Restart warning hidden when timeout matches runtime |
| `test_restart_warning_shows_on_timeout_change` | Restart warning appears when timeout changed |
| `test_restart_warning_hides_when_reset` | Restart warning hides when reset to original |
| `test_can_enter_password_fields` | Can enter values in password fields |
| `test_password_fields_are_password_type` | Password fields mask input |

**TestSaveAuthSettings** - Saving auth settings:

| Test | Description |
|------|-------------|
| `test_save_auth_settings_updates_config` | Save button updates config |
| `test_save_shows_success_message` | Save shows success toast |

**TestChangePassword** - Password change functionality:

| Test | Description |
|------|-------------|
| `test_change_password_requires_current` | Password change requires current password |
| `test_change_password_requires_match` | New passwords must match |
| `test_change_password_success` | Password change succeeds with valid input |

**TestAuthTabWhenDisabled** - Auth tab when auth is disabled:

| Test | Description |
|------|-------------|
| `test_auth_tab_visible_when_disabled` | Auth tab still visible |
| `test_can_enable_auth_from_disabled` | Can enable auth from disabled state |

### fast/

#### [test_navigation.py](../tests/ui/fast/test_navigation.py)
Page loading and navigation via sidebar/logo.

| Test | Description |
|------|-------------|
| `test_sidebar_is_visible` | Sidebar navigation is visible on page load |
| `test_navigate_to_dashboard` | Navigate to dashboard via sidebar link |
| `test_navigate_to_torrents` | Navigate to torrents page via sidebar |
| `test_navigate_to_settings` | Navigate to settings page via sidebar |
| `test_logo_navigates_to_dashboard` | Clicking logo returns to dashboard |
| `test_active_nav_item_highlighted` | Active page link is highlighted in sidebar |
| `test_dashboard_direct_access` | Direct URL access to dashboard works |
| `test_torrents_direct_access` | Direct URL access to torrents works |
| `test_settings_direct_access` | Direct URL access to settings works |
| `test_clients_tab_is_default` | Settings page defaults to Clients tab |
| `test_switch_to_connections_tab` | Can switch to Connections tab |
| `test_tab_persistence_via_url_hash` | Tab selection persists via URL hash |
| `test_switch_back_to_clients_tab` | Can switch back to Clients tab |
| `test_dashboard_loads_content` | Dashboard loads stats and content |
| `test_torrents_page_shows_loading` | Torrents page shows loading state |
| `test_settings_page_loads_tabs` | Settings page loads with both tabs |

### [test_dashboard.py](../tests/ui/test_dashboard.py)
Dashboard stats cards, auto-polling, and torrent list.

| Test | Description |
|------|-------------|
| `test_dashboard_loads_with_correct_title` | Page title is correct |
| `test_dashboard_shows_page_heading` | Page heading is visible |
| `test_stats_cards_are_visible` | All 4 stats cards are visible |
| `test_recent_torrents_container_exists` | Torrent list container exists |
| `test_stats_are_numeric` | Stats values are valid numbers |
| `test_get_all_stats_returns_dict` | Stats helper returns all 4 values |
| `test_dashboard_polls_api` | Dashboard auto-refreshes via API polling |
| `test_api_response_contains_expected_fields` | API response has required fields |
| `test_torrent_card_count_matches_method` | Torrent count method works correctly |
| `test_empty_state_or_torrents_shown` | Shows either empty state or torrent cards |
| `test_navigate_to_torrents_from_dashboard` | Can navigate to torrents page |
| `test_navigate_to_settings_from_dashboard` | Can navigate to settings page |
| `test_sidebar_visible_on_dashboard` | Sidebar is visible on dashboard |

#### [test_torrents.py](../tests/ui/fast/test_torrents.py)
Client tabs, tab switching, torrent listings, and polling.

| Test | Description |
|------|-------------|
| `test_torrents_page_loads_with_correct_title` | Page title is correct |
| `test_torrents_page_shows_heading` | Page heading is visible |
| `test_client_tabs_container_exists` | Tab container element exists |
| `test_loading_indicator_eventually_hides` | Loading spinner disappears |
| `test_client_tabs_appear_after_loading` | Client tabs appear after data loads |
| `test_get_client_tab_count` | Can count client tabs |
| `test_get_client_tab_names` | Can get client tab names |
| `test_first_tab_is_active_by_default` | First tab is selected by default |
| `test_get_active_client_tab` | Can get currently active tab name |
| `test_switch_to_second_tab` | Can switch to another tab |
| `test_tab_content_changes_on_switch` | Tab content updates when switching |
| `test_torrent_cards_in_active_tab` | Torrent cards appear in active tab |
| `test_torrent_card_count` | Can count torrents in active tab |
| `test_empty_message_or_torrents` | Shows empty message or torrent cards |
| `test_torrents_page_polls_api` | Page auto-refreshes via API polling |
| `test_wait_for_api_refresh` | Wait helper works for API refresh |
| `test_navigate_to_dashboard_from_torrents` | Can navigate to dashboard |
| `test_navigate_to_settings_from_torrents` | Can navigate to settings |
| `test_sidebar_visible_on_torrents` | Sidebar is visible on torrents page |

#### [test_settings.py](../tests/ui/fast/test_settings.py)
Settings page tabs (Clients/Connections), modal display, and list rendering.

| Test | Description |
|------|-------------|
| `test_settings_page_loads_with_correct_title` | Page title is correct |
| `test_settings_page_shows_heading` | Page heading is visible |
| `test_settings_tabs_exist` | Both tabs exist |
| `test_clients_tab_exists` | Clients tab exists |
| `test_connections_tab_exists` | Connections tab exists |
| `test_clients_tab_active_by_default` | Clients tab is active by default |
| `test_connections_tab_inactive_by_default` | Connections tab starts inactive |
| `test_clients_content_visible_by_default` | Clients content is visible |
| `test_connections_content_hidden_by_default` | Connections content is hidden |
| `test_switch_to_connections_tab` | Can switch to Connections tab |
| `test_switch_to_clients_tab` | Can switch back to Clients tab |
| `test_connections_content_visible_after_switch` | Connections visible after switch |
| `test_clients_content_hidden_after_switch` | Clients hidden after switch |
| `test_get_client_cards` | Can get client card elements |
| `test_get_client_count` | Can count clients |
| `test_get_client_names` | Can get client names |
| `test_add_client_button_exists` | Add Client button exists |
| `test_get_connection_cards` | Can get connection card elements |
| `test_get_connection_count` | Can count connections |
| `test_add_connection_button_exists` | Add Connection button exists |
| `test_open_add_client_modal` | Can open Add Client modal |

#### [test_history.py](../tests/ui/fast/test_history.py)
Transfer History page: stats, filters, table, pagination, status badges, delete functionality.

| Test | Description |
|------|-------------|
| `test_history_in_sidebar` | History link visible in sidebar |
| `test_history_page_loads` | Page loads with correct title |
| `test_navigate_to_history_via_sidebar` | Navigate to history via sidebar link |
| `test_history_nav_item_highlighted` | History is highlighted when active |
| `test_history_stats_banner_visible` | Stats banner shows all 5 stat cards |
| `test_history_stats_labels` | Stats have correct labels |
| `test_history_table_visible` | History table is visible |
| `test_history_shows_correct_columns` | Table has Name, From→To, Size, Duration, Status, Date, Actions |
| `test_history_pagination_controls` | Pagination controls are visible |
| `test_filter_controls_visible` | Filter dropdowns and search visible |
| `test_history_filter_by_status` | Status dropdown filters correctly |
| `test_history_filter_by_client` | Source/target filters work |
| `test_history_search_by_name` | Search input filters by name |
| `test_history_clear_filters` | Clear button resets all filters |
| `test_history_date_filter_from` | From date filter works |
| `test_history_date_filter_to` | To date filter works |
| `test_history_date_range_filter` | Both date filters work together |
| `test_history_page_navigation` | Pagination prev button disabled on page 1 |
| `test_pagination_info_displayed` | Shows "Showing X-Y of Z" |
| `test_history_shows_transfer_records` | Table shows records or empty state |
| `test_history_status_badge_colors` | Status badges have correct styling |
| `test_history_table_sortable_columns` | 3 sortable columns (Name, Size, Date) |
| `test_history_column_sorting` | Clicking header triggers sorting |
| `test_empty_state_message` | Empty state shows "No transfer history" |
| `test_empty_state_icon` | Empty state has history icon |
| `test_loading_indicator_exists` | Loading indicator element exists |
| `test_clear_history_button_exists` | Clear History button is visible |
| `test_clear_history_modal_appears` | Clicking Clear History shows confirmation modal |
| `test_clear_history_modal_cancel` | Cancel button closes the clear history modal |
| `test_clear_history_modal_close_button` | X button closes the clear history modal |
| `test_clear_history_modal_overlay_click` | Clicking overlay closes the modal |
| `test_actions_column_exists` | Actions column header exists in table |
| `test_delete_buttons_on_completed_transfers` | Delete buttons appear on completed/failed rows |
| `test_delete_button_opens_confirmation` | Clicking delete button shows confirmation modal |
| `test_delete_modal_shows_torrent_name` | Delete modal shows the torrent name |
| `test_delete_modal_cancel` | Cancel button closes delete modal |
| `test_delete_modal_close_button` | X button closes delete modal |

### crud/

#### [test_client_crud.py](../tests/ui/crud/test_client_crud.py)
Full client CRUD workflows: add, edit, delete, test connection, form validation.

| Test | Description |
|------|-------------|
| `test_add_client_form_validation_required_fields` | Form validates required fields |
| `test_add_client_successfully` | Can add a new client via UI |
| `test_add_duplicate_client_shows_error` | Duplicate client name shows error |
| `test_connection_success_with_valid_credentials` | Test Connection succeeds with valid creds |
| `test_connection_failure_with_wrong_port` | Test Connection fails with wrong port |
| `test_connection_failure_with_wrong_password` | Test Connection fails with wrong password |
| `test_edit_client_modal_populates_existing_values` | Edit modal pre-fills current values |
| `test_edit_client_changes_saved` | Edited client changes are saved |
| `test_delete_confirmation_modal_shows` | Delete shows confirmation modal |
| `test_cancel_delete_keeps_client` | Canceling delete keeps client |
| `test_connection_type_toggles_username_field` | Username field shows/hides based on type |
| `test_modal_close_button_works` | Modal close button works |
| `test_form_changes_disable_save_button` | Form changes require re-testing connection |

#### [test_connection_crud.py](../tests/ui/crud/test_connection_crud.py)
Connection CRUD workflows: add, edit, delete, test connection.

| Test | Description |
|------|-------------|
| `test_connections_tab_loads` | Connections tab loads correctly |
| `test_connections_list_shows_existing_connections` | Existing connections are listed |
| `test_add_connection_button_visible` | Add Connection button is visible |
| `test_add_connection_modal_opens` | Can open Add Connection modal |
| `test_add_connection_modal_has_client_dropdowns` | Modal has From/To dropdowns |
| `test_add_connection_modal_populates_clients` | Dropdowns populate with clients |
| `test_save_button_disabled_before_test` | Save disabled until test passes |
| `test_from_type_changes_config_visibility` | From type toggles SFTP config |
| `test_to_type_changes_config_visibility` | To type toggles SFTP config |
| `test_path_config_disabled_before_test` | Path config disabled until test |
| `test_modal_close_button_works` | Modal close button works |
| `test_test_connection_button_visible` | Test Connection button is visible |
| `test_test_connection_with_local_type` | Test Connection works with local type |
| `test_edit_connection_opens_modal` | Edit button opens modal |
| `test_edit_modal_shows_connection_title` | Edit modal shows connection name |
| `test_delete_shows_confirmation` | Delete shows confirmation modal |
| `test_cancel_delete_keeps_connection` | Cancel keeps connection |
| `test_cannot_select_same_client_for_from_and_to` | Same client cannot be both From and To |
| `test_connection_card_shows_client_names` | Card shows client names |
| `test_connection_card_shows_status` | Card shows connection status |
| `test_connection_card_shows_transfer_stats` | Card shows transfer statistics |

### e2e/

#### [test_e2e_workflows.py](../tests/ui/e2e/test_e2e_workflows.py)
End-to-end tests combining UI with actual torrent transfers.

| Test | Description |
|------|-------------|
| `test_dashboard_shows_active_torrent` | Dashboard shows torrent from Radarr transfer |
| `test_torrents_page_shows_transfer_progress` | Torrents page shows transfer progress |
| `test_added_client_persists_across_reload` | Added client survives page reload |
| `test_edited_client_persists_across_reload` | Edited client survives page reload |
| `test_torrent_appears_on_both_dashboard_and_torrents_page` | Torrent visible on multiple pages |
| `test_navigation_flow_dashboard_to_settings_to_torrents` | Full navigation flow works |
| `test_dashboard_shows_tv_episode_torrent` | Dashboard shows Sonarr TV episode |

#### [test_smoke.py](../tests/ui/e2e/test_smoke.py)
Full smoke test: add clients/connections via UI, trigger transfer, verify in dashboard.

| Test | Description |
|------|-------------|
| `test_full_setup_and_transfer_workflow` | Complete flow: add clients, connections, trigger transfer, verify UI |

#### [test_transfer_types.py](../tests/ui/e2e/test_transfer_types.py)
Transfer type combination tests: all 4 combinations of local/sftp source and target.

**TestTransferTypeCombinations** - Test adding connections for each transfer type combination:

| Test | Description |
|------|-------------|
| `test_local_to_local_connection` | Add local → local connection via UI |
| `test_local_to_sftp_connection` | Add local → sftp connection via UI |
| `test_sftp_to_local_connection` | Add sftp → local connection via UI |
| `test_sftp_to_sftp_connection` | Add sftp → sftp connection via UI |

**TestSftpFieldVisibility** - Test SFTP config field show/hide behavior:

| Test | Description |
|------|-------------|
| `test_sftp_fields_hidden_for_local_type` | SFTP fields hidden when type is 'local' |
| `test_from_sftp_fields_visible_for_sftp_type` | Source SFTP fields visible when from type is 'sftp' |
| `test_to_sftp_fields_visible_for_sftp_type` | Target SFTP fields visible when to type is 'sftp' |
| `test_both_sftp_fields_visible_for_sftp_to_sftp` | Both SFTP field sets visible for sftp → sftp |
| `test_sftp_fields_toggle_on_type_change` | SFTP fields toggle correctly when type changes |

## Helper Functions

Located in `tests/ui/helpers.py`. These are shared utilities for UI tests:

| Function | Purpose |
|----------|--------|
| `add_connection_via_ui()` | Add a transfer connection via the Settings UI modal. Handles all transfer type combinations (local/sftp). |
| `delete_connection_via_api()` | Delete a connection by name via the REST API. Used for cleanup. |
| `delete_client_via_api()` | Delete a download client by name via the REST API. Used for cleanup. |
| `unwrap_api_response()` | Extract data from standardized API response wrapper. |
| `generate_unique_name()` | Generate a unique name with timestamp for test isolation. |
| `log_test_step()` | Log a test step with visual formatting. |

**Internal Helpers** (prefixed with `_`):
- `_fill_transfer_type_config()` - Fills type-specific config fields (SFTP host/port/user/pass) based on transfer type

**Adding New Transfer Types**:
To support a new transfer type (e.g., `rclone`, `s3`), only `_fill_transfer_type_config()` needs to be updated. Test call sites pass raw config dicts from fixtures.

## Page Objects

Located in `tests/ui/pages/`:

| Page Object | Purpose |
|-------------|---------|
| `BasePage` | Common navigation, `wait_for_api_response()` |
| `DashboardPage` | Stats cards, recent torrents list |
| `TorrentsPage` | Client tabs, torrent listings |
| `SettingsPage` | Client/connection CRUD modals and forms |
| `HistoryPage` | Transfer history stats, filters, table, pagination |

## Key Fixtures

From `tests/ui/conftest.py`:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `page` | function | Playwright Page instance |
| `dashboard_page` | function | DashboardPage object |
| `torrents_page` | function | TorrentsPage object |
| `settings_page` | function | SettingsPage object |
| `crud_test_setup` | function | Cleanup for CRUD tests (tracks created clients) |
| `transfer_history_data` | module | Runs a real transfer to create organic history data |

## Timeouts

Standard timeouts for UI operations are defined in `tests/ui/helpers.py` as the `UI_TIMEOUTS` dict. Keys include `page_load`, `api_response`, `api_response_slow`, `element_visible`, `modal_animation`, `dropdown_load`, and `js_processing`.

## Common Patterns

### Waiting for API responses
```python
with page.expect_response(lambda r: "/api/torrents" in r.url, timeout=10000):
    page.reload()
```

### CRUD test cleanup
Tests that create clients use `crud_test_setup` fixture which tracks `_created_clients` and deletes via API in teardown.

### Assertions
```python
from playwright.sync_api import expect
expect(page.locator(".stat-card")).to_be_visible()
expect(page).to_have_title("Transferarr - Dashboard")
```

## Troubleshooting

**500 error on config save**: Check `config.json` permissions in transferarr container. Should be `666` and owned by `appuser`. Run `./docker/scripts/cleanup.sh config` to regenerate.

**Tests timeout waiting for torrents**: Ensure mock indexer has torrents registered. Check with `curl http://localhost:9696/torrents`.
