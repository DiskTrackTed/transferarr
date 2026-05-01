"""Fast UI tests for the Torrents page table view."""

import json
import re
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import expect

from tests.ui.helpers import UI_TIMEOUTS


def build_torrent(
    name: str,
    *,
    state: str = "Seeding",
    progress: float = 100.0,
    total_size: int = 1_000_000_000,
    num_seeds: int = 10,
    download_rate: int = 0,
    upload_rate: int = 2_048,
    added: int = 1_700_000_000,
    tracker: str = "tracker.example",
):
    """Build a mock torrent payload matching the per-client API response."""
    return {
        "name": name,
        "state": state,
        "progress": progress,
        "total_size": total_size,
        "num_seeds": num_seeds,
        "download_payload_rate": download_rate,
        "upload_payload_rate": upload_rate,
        "time_added": added,
        "trackers": [{"url": f"http://{tracker}/announce"}],
    }


def build_paginated_client(prefix: str, count: int) -> dict:
    """Build a deterministic client torrent map large enough for pagination tests."""
    torrents = {}
    for index in range(count):
        torrent_hash = f"{prefix[:3]}{index:03x}".lower()
        torrents[torrent_hash] = build_torrent(
            f"{prefix} Shared Release {index:02d}",
            state="Seeding",
            total_size=500_000_000 + (index * 1_000_000),
            num_seeds=20 - (index % 5),
            upload_rate=4_096 + index,
            added=1_700_000_000 + index,
            tracker=f"{prefix.lower()}.tracker",
        )
    return torrents


def mock_torrents_api(page, clients: dict, *, errors: dict | None = None):
    """Mock the download-clients and per-client torrents API endpoints."""
    errors = errors or {}
    request_counts = {name: 0 for name in clients.keys()}

    def fulfill_json(route, payload, status=200):
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(payload),
        )

    def resolve_client_payload(client_name):
        payload = clients.get(client_name, {})
        if isinstance(payload, list):
            index = min(request_counts.get(client_name, 0), len(payload) - 1)
            return payload[index]
        if callable(payload):
            return payload(request_counts.get(client_name, 0))
        return payload

    def resolve_error_payload(client_name):
        payload = errors.get(client_name)
        if isinstance(payload, list):
            index = min(request_counts.get(client_name, 0), len(payload) - 1)
            return payload[index]
        if callable(payload):
            return payload(request_counts.get(client_name, 0))
        return payload

    def handle_clients(route):
        fulfill_json(
            route,
            {"data": {name: {"type": "deluge"} for name in clients.keys()}},
        )

    def handle_client_torrents(route):
        match = re.search(r"/api/v1/clients/([^/]+)/torrents", route.request.url)
        client_name = unquote(match.group(1)) if match else ""

        error_payload = resolve_error_payload(client_name)
        if error_payload:
            status_code, payload = error_payload
            fulfill_json(route, payload, status=status_code)
            request_counts[client_name] = request_counts.get(client_name, 0) + 1
            return

        fulfill_json(route, {"data": resolve_client_payload(client_name)})
        request_counts[client_name] = request_counts.get(client_name, 0) + 1

    page.route("**/api/v1/download_clients", handle_clients)
    page.route("**/api/v1/clients/*/torrents", handle_client_torrents)

    return request_counts


def mock_manual_transfer_api(page, *, destinations: dict | None = None, submitted: dict | None = None):
    """Mock manual-transfer modal endpoints and capture submitted payloads."""
    destinations = destinations or {
        "source-deluge": [
            {
                "client": "target-deluge",
                "transfer_type": "torrent",
                "connection": "source-to-target",
            }
        ]
    }
    submitted = submitted if submitted is not None else {}

    def fulfill_json(route, payload, status=200):
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(payload),
        )

    def handle_destinations(route):
        query = parse_qs(urlparse(route.request.url).query)
        source = query.get("source", [""])[0]
        fulfill_json(route, {"data": destinations.get(source, [])})

    def handle_manual_transfer(route):
        submitted["payload"] = json.loads(route.request.post_data or "{}")
        fulfill_json(route, {"data": {"total_initiated": len(submitted["payload"].get("hashes", []))}})

    page.route("**/api/v1/transfers/destinations?*", handle_destinations)
    page.route("**/api/v1/transfers/manual", handle_manual_transfer)

    return submitted


class TestTorrentsPageLoading:
    """Basic loading and empty-state coverage for the torrents page."""

    def test_shows_tabs_controls_and_table(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Gamma Release", total_size=300_000_000),
                "bbb222": build_torrent("Alpha Release", total_size=100_000_000),
                "ccc333": build_torrent("Beta Release", total_size=200_000_000),
            },
            "target-deluge": {
                "ddd444": build_torrent("Target Shared Release", tracker="target.example"),
            },
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.get_client_tab_names() == ["source-deluge", "target-deluge"]
        assert torrents_page.get_active_client_tab() == "source-deluge"
        expect(page.locator(torrents_page.TABLE_CONTROLS)).to_be_visible()
        expect(page.locator(f"{torrents_page.CLIENT_TAB_CONTENT}.active {torrents_page.TORRENT_TABLE}")).to_be_visible()
        assert torrents_page.get_torrent_card_count() == 3
        assert torrents_page.get_results_summary().startswith("Showing 1-3 of 3")

    def test_shows_no_clients_state(self, page, torrents_page):
        mock_torrents_api(page, {})

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.has_no_clients_message()
        expect(page.locator(torrents_page.TABLE_CONTROLS)).to_be_hidden()

    def test_shows_client_error_state(self, page, torrents_page):
        mock_torrents_api(
            page,
            {"source-deluge": {}},
            errors={
                "source-deluge": (
                    500,
                    {"error": {"message": "Mocked client failure"}},
                )
            },
        )

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.has_client_error_message()
        expect(page.locator(torrents_page.CLIENT_ERROR_MESSAGE)).to_contain_text("Mocked client failure")


class TestTorrentsTableInteractions:
    """Sort, filter, pagination, and selection behavior for the table view."""

    def test_name_sort_toggles_direction(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Gamma Release", total_size=300_000_000),
                "bbb222": build_torrent("Alpha Release", total_size=100_000_000),
                "ccc333": build_torrent("Beta Release", total_size=200_000_000),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.get_visible_row_values("name") == [
            "Alpha Release",
            "Beta Release",
            "Gamma Release",
        ]

        torrents_page.sort_by("name")
        assert torrents_page.get_visible_row_values("name") == [
            "Gamma Release",
            "Beta Release",
            "Alpha Release",
        ]
        assert "sort-desc" in torrents_page.get_sort_header_class("name")

        torrents_page.sort_by("name")
        assert torrents_page.get_visible_row_values("name") == [
            "Alpha Release",
            "Beta Release",
            "Gamma Release",
        ]
        assert "sort-asc" in torrents_page.get_sort_header_class("name")

    def test_numeric_size_sort_uses_numeric_order(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Gamma Release", total_size=300_000_000),
                "bbb222": build_torrent("Alpha Release", total_size=100_000_000),
                "ccc333": build_torrent("Beta Release", total_size=200_000_000),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.sort_by("size")
        assert torrents_page.get_visible_row_values("name") == [
            "Alpha Release",
            "Beta Release",
            "Gamma Release",
        ]

        torrents_page.sort_by("size")
        assert torrents_page.get_visible_row_values("name") == [
            "Gamma Release",
            "Beta Release",
            "Alpha Release",
        ]

    def test_filters_rows_and_shows_filtered_empty_state(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Shared Seeder", state="Seeding"),
                "bbb222": build_torrent("Shared Downloader", state="Downloading", download_rate=4_096, upload_rate=0),
                "ccc333": build_torrent("Paused Release", state="Paused"),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.set_state_filter("seeding")
        assert torrents_page.get_visible_row_values("name") == ["Shared Seeder"]

        torrents_page.set_search_filter("no-match")
        page.wait_for_timeout(250)
        assert torrents_page.has_filtered_empty_message()
        assert not torrents_page.has_empty_message()
        assert torrents_page.get_results_summary() == "No torrents match current filters (3 total)"

    def test_page_size_and_filters_persist_across_tab_switches(self, page, torrents_page):
        clients = {
            "source-deluge": build_paginated_client("Source", 55),
            "target-deluge": build_paginated_client("Target", 10),
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.set_state_filter("seeding")
        torrents_page.set_search_filter("shared")
        page.wait_for_timeout(250)
        torrents_page.set_page_size(25)
        torrents_page.sort_by("added")
        torrents_page.sort_by("added")
        torrents_page.go_to_next_page()

        assert torrents_page.get_current_page() == 2

        torrents_page.switch_to_client_tab("target-deluge")

        expect(page.locator(f"{torrents_page.CLIENT_TAB}.active")).to_have_text("target-deluge")
        assert torrents_page.get_current_filters() == {
            "state": "seeding",
            "search": "shared",
            "page_size": "25",
        }
        assert torrents_page.get_current_page() == 1
        assert "sort-desc" in torrents_page.get_sort_header_class("added")
        assert torrents_page.get_visible_row_values("name")[0] == "Target Shared Release 09"

    def test_page_size_changes_visible_row_count(self, page, torrents_page):
        clients = {
            "source-deluge": build_paginated_client("Source", 55),
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.get_torrent_card_count() == 50

        torrents_page.set_page_size(25)
        assert torrents_page.get_torrent_card_count() == 25

        torrents_page.set_page_size(100)
        assert torrents_page.get_torrent_card_count() == 55

    def test_page_resets_on_filter_and_page_size_change(self, page, torrents_page):
        clients = {
            "source-deluge": build_paginated_client("Source", 55),
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.set_page_size(25)
        torrents_page.go_to_next_page()
        assert torrents_page.get_current_page() == 2

        torrents_page.set_state_filter("seeding")
        assert torrents_page.get_current_page() == 1

        torrents_page.go_to_next_page()
        assert torrents_page.get_current_page() == 2

        torrents_page.set_page_size(50)
        assert torrents_page.get_current_page() == 1

    def test_selection_survives_sort_and_filter_changes(self, page, torrents_page):
        clients = {
            "source-deluge": build_paginated_client("Source", 12),
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        selected_row = torrents_page.get_torrent_by_hash("sou000")
        selected_row.locator(torrents_page.TORRENT_CHECKBOX).click()

        assert torrents_page.get_selected_count() == 1
        assert len(torrents_page.get_selected_cards()) == 1

        torrents_page.sort_by("added")
        torrents_page.sort_by("added")
        assert torrents_page.get_selected_count() == 1
        assert torrents_page.is_transfer_button_visible()

        torrents_page.set_search_filter("11")
        page.wait_for_timeout(250)

        assert torrents_page.get_selected_count() == 1
        assert torrents_page.is_transfer_button_visible()
        assert len(torrents_page.get_selected_cards()) == 0
        assert torrents_page.get_visible_row_values("name") == ["Source Shared Release 11"]

    def test_selection_persists_across_page_changes(self, page, torrents_page):
        clients = {
            "source-deluge": build_paginated_client("Source", 55),
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.set_page_size(25)
        torrents_page.get_torrent_by_hash("sou000").locator(torrents_page.TORRENT_CHECKBOX).click()

        assert torrents_page.get_selected_count() == 1
        assert len(torrents_page.get_selected_cards()) == 1

        torrents_page.go_to_next_page()

        assert torrents_page.get_current_page() == 2
        assert torrents_page.get_selected_count() == 1
        assert torrents_page.is_transfer_button_visible()
        assert len(torrents_page.get_selected_cards()) == 0

        torrents_page.go_to_prev_page()

        assert torrents_page.get_current_page() == 1
        assert len(torrents_page.get_selected_cards()) == 1
        assert torrents_page.get_torrent_by_hash("sou000").locator(
            torrents_page.TORRENT_CHECKBOX
        ).is_checked()

    def test_selecting_other_client_clears_prior_client_selection(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Source Release"),
            },
            "target-deluge": {
                "bbb222": build_torrent("Target Release"),
            },
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.get_torrent_by_hash("aaa111").locator(torrents_page.TORRENT_CHECKBOX).click()
        assert torrents_page.get_selected_count() == 1
        assert len(torrents_page.get_selected_cards()) == 1

        torrents_page.switch_to_client_tab("target-deluge")
        expect(page.locator(f"{torrents_page.CLIENT_TAB}.active")).to_have_text("target-deluge")

        torrents_page.get_torrent_by_hash("bbb222").locator(torrents_page.TORRENT_CHECKBOX).click()
        assert torrents_page.get_selected_count() == 1
        assert len(torrents_page.get_selected_cards()) == 1

        torrents_page.switch_to_client_tab("source-deluge")
        expect(page.locator(f"{torrents_page.CLIENT_TAB}.active")).to_have_text("source-deluge")
        assert len(torrents_page.get_selected_cards()) == 0
        assert not torrents_page.get_torrent_by_hash("aaa111").locator(
            torrents_page.TORRENT_CHECKBOX
        ).is_checked()

    def test_missing_seed_and_rate_values_render_fallback_and_sort_predictably(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Bravo Has Values", num_seeds=7, upload_rate=4_096),
                "bbb222": build_torrent("Zulu Missing Seeds", num_seeds=None, upload_rate=None),
                "ccc333": build_torrent(
                    "Alpha Missing Rate",
                    state="Paused",
                    num_seeds=None,
                    download_rate=None,
                    upload_rate=None,
                ),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert torrents_page.get_visible_row_values("seeds") == ["--", "7", "--"]
        assert torrents_page.get_visible_row_values("rate") == ["--", "4.0 KB/s", "--"]

        torrents_page.sort_by("seeds")
        assert torrents_page.get_visible_row_values("name") == [
            "Bravo Has Values",
            "Alpha Missing Rate",
            "Zulu Missing Seeds",
        ]

        torrents_page.sort_by("rate")
        assert torrents_page.get_visible_row_values("name") == [
            "Bravo Has Values",
            "Alpha Missing Rate",
            "Zulu Missing Seeds",
        ]

    def test_only_seeding_rows_have_enabled_selection_and_inline_actions(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Seeder", state="Seeding"),
                "bbb222": build_torrent(
                    "Downloader",
                    state="Downloading",
                    progress=45,
                    download_rate=8_192,
                    upload_rate=0,
                ),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert len(torrents_page.get_enabled_checkboxes()) == 1
        assert len(torrents_page.get_inline_transfer_buttons()) == 1

        downloader_row = torrents_page.get_torrent_by_name("Downloader")
        assert downloader_row.locator(torrents_page.TORRENT_TRANSFER_BTN).count() == 0
        expect(downloader_row.locator(torrents_page.TORRENT_CHECKBOX)).to_be_disabled()


class TestTorrentsPolling:
    """Polling behavior for the active-client torrents refresh."""

    def test_polls_the_active_client_endpoint(self, page, torrents_page):
        clients = {
            "source-deluge": {
                "aaa111": build_torrent("Seeded Release"),
            }
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.wait_for_api_refresh(timeout=15000)

    def test_tab_switch_triggers_immediate_fetch_for_new_client(self, page, torrents_page):
        clients = {
            "source-deluge": {"aaa111": build_torrent("Source Release")},
            "target-deluge": {"bbb222": build_torrent("Target Release")},
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        with page.expect_response(
            lambda response: "/api/v1/clients/target-deluge/torrents" in response.url,
            timeout=UI_TIMEOUTS['api_response'],
        ):
            torrents_page.switch_to_client_tab("target-deluge")

        assert torrents_page.get_active_client_tab() == "target-deluge"

    def test_does_not_overlap_poll_requests(self, page, torrents_page):
        clients = {
            "source-deluge": {"aaa111": build_torrent("Seeded Release")},
        }
        mock_torrents_api(page, clients)

        page.add_init_script("""
            (() => {
                const originalFetch = window.fetch.bind(window);
                let activeRequests = 0;
                let maxConcurrent = 0;

                window.__pollMetrics = {
                    getActive: () => activeRequests,
                    getMaxConcurrent: () => maxConcurrent,
                };

                window.fetch = async (...args) => {
                    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
                    if (!url.includes('/api/v1/clients/') || !url.endsWith('/torrents')) {
                        return originalFetch(...args);
                    }

                    activeRequests += 1;
                    if (activeRequests > maxConcurrent) {
                        maxConcurrent = activeRequests;
                    }

                    try {
                        await new Promise((resolve) => setTimeout(resolve, 12000));
                        return await originalFetch(...args);
                    } finally {
                        activeRequests -= 1;
                    }
                };
            })();
        """)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded(timeout=25000)
        page.wait_for_timeout(22000)

        max_concurrent = page.evaluate("window.__pollMetrics.getMaxConcurrent()")
        assert max_concurrent == 1, f"Expected max 1 concurrent poll request, got {max_concurrent}"

    def test_refresh_keeps_selection_when_selected_torrent_still_exists(self, page, torrents_page):
        clients = {
            "source-deluge": [
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
            ],
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.get_torrent_by_hash("aaa111").locator(torrents_page.TORRENT_CHECKBOX).click()
        assert torrents_page.get_selected_count() == 1

        page.evaluate("""
            () => window.refreshClientTorrents('source-deluge')
        """)

        assert torrents_page.get_selected_count() == 1
        assert torrents_page.get_torrent_by_hash("aaa111").locator(
            torrents_page.TORRENT_CHECKBOX
        ).is_checked()

    def test_refresh_prunes_selection_when_selected_torrent_disappears(self, page, torrents_page):
        clients = {
            "source-deluge": [
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
                {
                    "bbb222": build_torrent("Second Release"),
                },
            ],
        }
        mock_torrents_api(page, clients)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.get_torrent_by_hash("aaa111").locator(torrents_page.TORRENT_CHECKBOX).click()
        assert torrents_page.get_selected_count() == 1

        page.evaluate("""
            () => window.refreshClientTorrents('source-deluge')
        """)

        assert torrents_page.get_selected_count() == 0
        assert not torrents_page.is_transfer_button_visible()
        assert len(torrents_page.get_selected_cards()) == 0

    def test_transient_refresh_error_keeps_modal_selection_and_submit_payload(self, page, torrents_page):
        clients = {
            "source-deluge": [
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
            ],
        }
        errors = {
            "source-deluge": [
                None,
                (503, {"error": {"message": "Transient client failure"}}),
            ],
        }
        submitted = mock_manual_transfer_api(page, submitted={})
        mock_torrents_api(page, clients, errors=errors)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.select_torrent_by_hash("aaa111")
        assert torrents_page.get_selected_count() == 1

        torrents_page.click_transfer_button()
        page.wait_for_timeout(UI_TIMEOUTS["modal_animation"])
        page.wait_for_timeout(UI_TIMEOUTS["dropdown_load"])
        torrents_page.select_destination("target-deluge")

        page.evaluate("""
            () => window.refreshClientTorrents('source-deluge')
        """)

        assert torrents_page.is_modal_visible()
        assert torrents_page.get_selected_count() == 1
        assert torrents_page.get_modal_selected_count() == 1

        with page.expect_response(
            lambda response: "/api/v1/transfers/manual" in response.url,
            timeout=UI_TIMEOUTS["api_response"],
        ):
            torrents_page.click_confirm_transfer()

        assert submitted["payload"] == {
            "hashes": ["aaa111"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
            "delete_source_cross_seeds": True,
        }

    def test_transient_refresh_error_keeps_visible_rows_and_selection_when_modal_closed(self, page, torrents_page):
        clients = {
            "source-deluge": [
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
                {
                    "aaa111": build_torrent("Seeded Release"),
                    "bbb222": build_torrent("Second Release"),
                },
            ],
        }
        errors = {
            "source-deluge": [
                None,
                (503, {"error": {"message": "Transient client failure"}}),
            ],
        }
        mock_torrents_api(page, clients, errors=errors)

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        torrents_page.select_torrent_by_hash("aaa111")
        assert torrents_page.get_selected_count() == 1

        page.evaluate("""
            () => window.refreshClientTorrents('source-deluge')
        """)

        assert torrents_page.has_client_error_message()
        assert torrents_page.get_torrent_card_count() == 2
        assert torrents_page.get_torrent_by_hash("aaa111").locator(
            torrents_page.TORRENT_CHECKBOX
        ).is_checked()

        torrents_page.select_torrent_by_hash("aaa111")

        assert torrents_page.get_selected_count() == 0
        assert not torrents_page.is_transfer_button_enabled()
        assert not torrents_page.get_torrent_by_hash("aaa111").locator(
            torrents_page.TORRENT_CHECKBOX
        ).is_checked()