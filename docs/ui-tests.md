# UI Tests

*Last Updated: 2026-01-08*

## Overview

Playwright-based UI tests using the Page Object Model pattern. Tests run in Docker with Chromium (headless by default).

## Running Tests

```bash
# Run all UI tests
./run_tests.sh tests/ui/ -v

# Run specific file
./run_tests.sh tests/ui/test_dashboard.py -v

# Run with screenshots on failure (default)
./run_tests.sh tests/ui/ -v --screenshot=only-on-failure
```

Test artifacts (screenshots, traces) are saved to `test-results/` (gitignored).

## Test Files

### [test_navigation.py](../tests/ui/test_navigation.py)
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

### [test_torrents.py](../tests/ui/test_torrents.py)
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

### [test_settings.py](../tests/ui/test_settings.py)
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

### [test_client_crud.py](../tests/ui/test_client_crud.py)
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

### [test_connection_crud.py](../tests/ui/test_connection_crud.py)
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

### [test_e2e_workflows.py](../tests/ui/test_e2e_workflows.py)
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

### [test_smoke.py](../tests/ui/test_smoke.py)
Full smoke test: add clients/connections via UI, trigger transfer, verify in dashboard.

| Test | Description |
|------|-------------|
| `test_full_setup_and_transfer_workflow` | Complete flow: add clients, connections, trigger transfer, verify UI |

## Page Objects

Located in `tests/ui/pages/`:

| Page Object | Purpose |
|-------------|---------|
| `BasePage` | Common navigation, `wait_for_api_response()` |
| `DashboardPage` | Stats cards, recent torrents list |
| `TorrentsPage` | Client tabs, torrent listings |
| `SettingsPage` | Client/connection CRUD modals and forms |

## Key Fixtures

From `tests/ui/conftest.py`:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `page` | function | Playwright Page instance |
| `dashboard_page` | function | DashboardPage object |
| `torrents_page` | function | TorrentsPage object |
| `settings_page` | function | SettingsPage object |
| `crud_test_setup` | function | Cleanup for CRUD tests (tracks created clients) |

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
