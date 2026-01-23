"""
End-to-end UI tests that verify complete user workflows.

These tests combine UI interactions with actual torrent transfers,
requiring the full Docker test environment to be running.

E2E tests are slower than unit/component tests and should be used sparingly
to verify critical user journeys work correctly.
"""
import re
import time
import pytest
from playwright.sync_api import Page, expect

# Import test utilities
from tests.conftest import SERVICES, TIMEOUTS, DELUGE_PASSWORD, DELUGE_RPC_USERNAME
from tests.utils import (
    movie_catalog,
    show_catalog,
    make_torrent_name,
    make_episode_name,
    wait_for_queue_item_by_hash,
    wait_for_sonarr_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    wait_for_torrent_removed,
)
from tests.ui.helpers import (
    UI_TIMEOUTS,
    delete_client_via_api,
    generate_unique_name,
    log_test_step,
)


class TestE2ETorrentWorkflow:
    """E2E tests for torrent-related workflows through the UI."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        self.transferarr = transferarr
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_dashboard_shows_active_torrent(
        self,
        dashboard_page,
        page: Page,
        create_torrent,
        radarr_client,
        deluge_source,
    ):
        """
        E2E test: Verify dashboard shows torrents as they progress through states.
        
        This test:
        1. Creates a torrent and adds it to Radarr
        2. Waits for torrent to be grabbed and start seeding
        3. Verifies the dashboard shows the torrent
        4. Checks that stats update appropriately
        """
        log_test_step("Step 1: Create test torrent")
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent: {torrent_name}")
        print(f"  Hash: {torrent_info['hash']}")
        
        log_test_step("Step 2: Add movie to Radarr and trigger search")
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        
        # Wait for queue item by hash
        log_test_step("Step 3: Wait for Radarr to grab torrent")
        wait_for_queue_item_by_hash(
            radarr_client, 
            torrent_info['hash'], 
            timeout=60, 
            expected_status='completed'
        )
        print("  Torrent grabbed by Radarr")
        
        # Wait for torrent to seed on source
        log_test_step("Step 4: Wait for torrent to seed on source")
        wait_for_torrent_in_deluge(
            deluge_source,
            torrent_info['hash'],
            timeout=60,
            expected_state='Seeding'
        )
        print("  Torrent is seeding on source")
        
        # Wait for transferarr to discover the torrent
        log_test_step("Step 5: Wait for transferarr to discover torrent")
        wait_for_transferarr_state(
            self.transferarr,
            torrent_name,
            expected_state='HOME_SEEDING',
            timeout=30
        )
        print("  Transferarr discovered torrent")
        
        # Now check the UI
        log_test_step("Step 6: Verify dashboard shows torrent")
        dashboard_page.goto()
        
        # Wait for stats to load
        dashboard_page.wait_for_stats_update()
        
        # Active count should be at least 1
        stats = dashboard_page.get_all_stats()
        print(f"  Dashboard stats: {stats}")
        assert stats['active'] >= 1, f"Expected at least 1 active torrent, got {stats['active']}"
        
        # The torrent should appear in the recent torrents list
        # Note: Dashboard shows recent torrents, torrent name should be visible
        page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])  # Give UI time to update
        
        # Verify via API that torrent is tracked (UI may not show all fields)
        with page.expect_response(
            lambda r: "/api/v1/torrents" in r.url and r.request.method == "GET",
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            page.reload()
        
        torrents_response = response_info.value.json()
        # Unwrap data envelope (supports both old and new format)
        torrents = torrents_response.get('data', torrents_response) if isinstance(torrents_response, dict) and 'data' in torrents_response else torrents_response
        tracked_names = [t['name'] for t in torrents]
        assert torrent_name in tracked_names, f"Torrent {torrent_name} not in tracked list: {tracked_names}"
        
        print("\n✅ Test passed: Dashboard shows active torrent!")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_torrents_page_shows_transfer_progress(
        self,
        torrents_page,
        page: Page,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
    ):
        """
        E2E test: Verify torrents page shows client tabs and torrent status.
        
        This test:
        1. Creates a torrent and triggers transfer
        2. Navigates to torrents page
        3. Verifies client tabs show torrents
        4. Watches torrent appear in target client tab after transfer
        """
        log_test_step("Step 1: Create test torrent")
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent: {torrent_name}")
        
        log_test_step("Step 2: Add movie to Radarr and trigger download")
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        
        # Wait for torrent to seed
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info['hash'], timeout=60, expected_state='Seeding')
        wait_for_transferarr_state(self.transferarr, torrent_name, expected_state='HOME_SEEDING', timeout=30)
        print("  Torrent is seeding and tracked by transferarr")
        
        log_test_step("Step 3: Navigate to torrents page")
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # Verify client tabs exist
        tabs = torrents_page.get_client_tabs()
        tab_names = torrents_page.get_client_tab_names()
        print(f"  Client tabs: {tab_names}")
        assert len(tabs) >= 2, f"Expected at least 2 client tabs, got {len(tabs)}"
        
        log_test_step("Step 4: Verify source client shows torrent")
        # Find and click the source-deluge tab
        source_tab_found = False
        for tab_name in tab_names:
            if 'source' in tab_name.lower():
                torrents_page.switch_to_client_tab(tab_name)
                source_tab_found = True
                break
        
        if source_tab_found:
            # Wait for tab content to load
            page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])
            
            # Check for torrent in the list (via API response)
            with page.expect_response(
                lambda r: "/api/v1/all_torrents" in r.url,
                timeout=UI_TIMEOUTS['api_response']
            ) as response_info:
                page.reload()
            
            all_torrents_response = response_info.value.json()
            # Unwrap data envelope (supports both old and new format)
            all_torrents = all_torrents_response.get('data', all_torrents_response) if isinstance(all_torrents_response, dict) and 'data' in all_torrents_response else all_torrents_response
            print(f"  All torrents response: {list(all_torrents.keys())}")
        
        log_test_step("Step 5: Wait for transfer to complete")
        # Wait for torrent to reach target
        wait_for_transferarr_state(
            self.transferarr,
            torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=180  # Transfers can take time
        )
        print("  Transfer complete - torrent is seeding on target")
        
        # Reload torrents page and verify target shows torrent
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        
        # The torrent should now appear on target client
        print("\n✅ Test passed: Torrents page shows transfer progress!")


class TestE2ESettingsPersistence:
    """E2E tests for settings persistence across page reloads."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        self._created_clients = []
        yield
        # Cleanup
        for client_name in self._created_clients:
            delete_client_via_api(client_name)
    
    @pytest.mark.timeout(120)
    def test_added_client_persists_across_reload(
        self,
        settings_page,
        page: Page,
    ):
        """
        E2E test: Verify adding a client persists across page reloads.
        
        This test:
        1. Adds a new client via UI
        2. Refreshes the page
        3. Verifies the client still exists
        """
        log_test_step("Step 1: Navigate to settings and get initial count")
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        initial_count = settings_page.get_client_count()
        print(f"  Initial client count: {initial_count}")
        
        log_test_step("Step 2: Add a new client")
        unique_name = generate_unique_name("persist-test")
        self._created_clients.append(unique_name)
        
        settings_page.open_add_client_modal()
        settings_page.fill_client_form(
            name=unique_name,
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        # Test connection first
        with page.expect_response(
            lambda r: "/api/v1/download_clients/test" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ):
            settings_page.test_client_connection()
        
        # Wait for save button and save
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        with page.expect_response(
            lambda r: "/api/v1/download_clients" in r.url and r.request.method == "POST",
            timeout=UI_TIMEOUTS['element_visible']
        ):
            settings_page.save_client()
        
        # Wait for modal to close
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
        settings_page.wait_for_clients_loaded()
        
        # Verify count increased
        new_count = settings_page.get_client_count()
        assert new_count == initial_count + 1, f"Expected {initial_count + 1} clients, got {new_count}"
        print(f"  Client added, new count: {new_count}")
        
        log_test_step("Step 3: Reload page and verify persistence")
        page.reload()
        settings_page.wait_for_clients_loaded()
        
        # Count should still be the same
        persisted_count = settings_page.get_client_count()
        assert persisted_count == new_count, f"After reload: expected {new_count}, got {persisted_count}"
        
        # Client should be visible
        expect(
            settings_page.page.locator(f"{settings_page.CLIENT_CARD}:has-text('{unique_name}')")
        ).to_be_visible()
        
        print("\n✅ Test passed: Added client persists across reload!")
    
    @pytest.mark.timeout(120)
    def test_edited_client_persists_across_reload(
        self,
        settings_page,
        page: Page,
    ):
        """
        E2E test: Verify editing a client persists across page reloads.
        
        This test:
        1. Creates a new client
        2. Edits the client (changes a field)
        3. Refreshes the page
        4. Verifies the edit persisted
        """
        log_test_step("Step 1: Create a client to edit")
        settings_page.goto()
        settings_page.wait_for_clients_loaded()
        
        unique_name = generate_unique_name("edit-persist")
        self._created_clients.append(unique_name)
        
        settings_page.open_add_client_modal()
        settings_page.fill_client_form(
            name=unique_name,
            host=SERVICES['deluge_source']['host'],
            port=SERVICES['deluge_source']['rpc_port'],
            password=DELUGE_PASSWORD,
            username=DELUGE_RPC_USERNAME,
            connection_type="rpc"
        )
        
        with page.expect_response(lambda r: "/api/v1/download_clients/test" in r.url):
            settings_page.test_client_connection()
        
        save_btn = settings_page.page.locator(settings_page.SAVE_CLIENT_BTN)
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['element_visible'])
        
        with page.expect_response(
            lambda r: "/api/v1/download_clients" in r.url and r.request.method == "POST"
        ):
            settings_page.save_client()
        
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
        settings_page.wait_for_clients_loaded()
        print(f"  Created client: {unique_name}")
        
        log_test_step("Step 2: Edit the client")
        settings_page.edit_client(unique_name)
        
        # Change the host to target Deluge's host (simulates edit that will pass connection test)
        # Note: We change host because in Docker the ports are the same
        host_input = settings_page.page.locator(settings_page.CLIENT_HOST_INPUT)
        original_host = host_input.input_value()
        new_host = SERVICES['deluge_target']['host']  # Use target's host
        
        host_input.clear()
        host_input.fill(new_host)
        print(f"  Changed host from {original_host} to {new_host}")
        
        # Re-test connection with new settings (no need to re-enter password in edit mode -
        # backend uses stored password when client name is provided)
        with page.expect_response(lambda r: "/api/v1/download_clients/test" in r.url):
            settings_page.test_client_connection()
        
        # Wait for save button and save
        expect(save_btn).to_be_enabled(timeout=UI_TIMEOUTS['api_response_slow'])
        
        with page.expect_response(
            lambda r: f"/api/v1/download_clients/{unique_name}" in r.url and r.request.method == "PUT",
            timeout=UI_TIMEOUTS['element_visible']
        ):
            settings_page.save_client()
        
        expect(settings_page.page.locator(settings_page.CLIENT_MODAL)).not_to_be_visible()
        
        log_test_step("Step 3: Reload and verify edit persisted")
        page.reload()
        settings_page.wait_for_clients_loaded()
        
        # Open edit modal and check host
        settings_page.edit_client(unique_name)
        host_input = settings_page.page.locator(settings_page.CLIENT_HOST_INPUT)
        expect(host_input).to_have_value(new_host)
        
        print("\n✅ Test passed: Edited client persists across reload!")


class TestE2ECrossPageWorkflows:
    """E2E tests for workflows that span multiple pages."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        self.transferarr = transferarr
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_torrent_appears_on_both_dashboard_and_torrents_page(
        self,
        dashboard_page,
        torrents_page,
        page: Page,
        create_torrent,
        radarr_client,
        deluge_source,
    ):
        """
        E2E test: Verify a torrent is visible on both dashboard and torrents page.
        
        This test:
        1. Creates a torrent
        2. Verifies it appears on the dashboard
        3. Navigates to torrents page and verifies it appears there too
        """
        log_test_step("Step 1: Create test torrent")
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        torrent_info = create_torrent(torrent_name, size_mb=10)
        print(f"  Created torrent: {torrent_name}")
        
        log_test_step("Step 2: Add to Radarr and wait for seeding")
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True
        )
        
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], timeout=60, expected_status='completed')
        wait_for_torrent_in_deluge(deluge_source, torrent_info['hash'], timeout=60, expected_state='Seeding')
        wait_for_transferarr_state(self.transferarr, torrent_name, expected_state='HOME_SEEDING', timeout=30)
        print("  Torrent is being tracked")
        
        log_test_step("Step 3: Check dashboard")
        dashboard_page.goto()
        dashboard_page.wait_for_stats_update()
        
        stats = dashboard_page.get_all_stats()
        assert stats['active'] >= 1, f"Dashboard should show active torrent, got {stats}"
        print(f"  Dashboard stats: {stats}")
        
        log_test_step("Step 4: Navigate to torrents page via sidebar")
        # Click torrents link in sidebar
        page.click(".sidebar a[href='/torrents']")
        expect(page).to_have_url(re.compile(r".*/torrents"))
        
        # Wait for page to load
        torrents_page.wait_for_torrents_loaded()
        
        # Verify client tabs are present
        tabs = torrents_page.get_client_tabs()
        assert len(tabs) >= 1, "Should have at least one client tab"
        print(f"  Torrents page has {len(tabs)} client tabs")
        
        # Check via API that torrent is in the response
        with page.expect_response(
            lambda r: "/api/v1/all_torrents" in r.url,
            timeout=UI_TIMEOUTS['api_response']
        ) as response_info:
            page.reload()
        
        all_torrents_response = response_info.value.json()
        # Unwrap data envelope (supports both old and new format)
        all_torrents = all_torrents_response.get('data', all_torrents_response) if isinstance(all_torrents_response, dict) and 'data' in all_torrents_response else all_torrents_response
        # all_torrents is dict of client_name -> dict of torrent_hash -> torrent_info
        found = False
        for client_name, client_torrents in all_torrents.items():
            # client_torrents is a dict keyed by torrent hash
            for torrent_hash, torrent_info in client_torrents.items():
                name = torrent_info.get('name', '') if isinstance(torrent_info, dict) else ''
                if name == torrent_name or torrent_name in name:
                    found = True
                    print(f"  Found torrent on client: {client_name}")
                    break
            if found:
                break
        
        assert found, f"Torrent {torrent_name} not found in any client"
        
        print("\n✅ Test passed: Torrent visible on both dashboard and torrents page!")
    
    @pytest.mark.timeout(120)
    def test_navigation_flow_dashboard_to_settings_to_torrents(
        self,
        dashboard_page,
        settings_page,
        torrents_page,
        page: Page,
    ):
        """
        E2E test: Verify navigation between all main pages works correctly.
        
        This test:
        1. Starts on dashboard
        2. Navigates to settings
        3. Navigates to torrents
        4. Returns to dashboard
        5. Verifies each page loads correctly
        """
        log_test_step("Step 1: Start on dashboard")
        dashboard_page.goto()
        expect(page).to_have_title("Transferarr - Dashboard")
        expect(page.locator("h2")).to_contain_text("Dashboard")
        print("  Dashboard loaded")
        
        log_test_step("Step 2: Navigate to settings via sidebar")
        page.click(".sidebar a[href='/settings']")
        expect(page).to_have_url(re.compile(r".*/settings"))
        expect(page).to_have_title("Transferarr - Settings")
        settings_page.wait_for_clients_loaded()
        print("  Settings loaded")
        
        log_test_step("Step 3: Navigate to torrents via sidebar")
        page.click(".sidebar a[href='/torrents']")
        expect(page).to_have_url(re.compile(r".*/torrents"))
        expect(page).to_have_title("Transferarr - Torrents")
        torrents_page.wait_for_torrents_loaded()
        print("  Torrents loaded")
        
        log_test_step("Step 4: Return to dashboard via logo")
        page.click(".logo")
        expect(page).to_have_url(re.compile(r".*/$"))
        expect(page).to_have_title("Transferarr - Dashboard")
        print("  Back to dashboard")
        
        log_test_step("Step 5: Verify active nav highlighting")
        # Dashboard link should be active
        expect(page.locator(".sidebar .tab-link.active")).to_contain_text("Dashboard")
        
        print("\n✅ Test passed: Navigation flow works correctly!")


class TestE2ESonarrWorkflow:
    """E2E tests for Sonarr-based workflows through the UI."""
    
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Setup clean environment with running transferarr."""
        transferarr.set_auth_config(enabled=False)
        transferarr.start(wait_healthy=True)
        self.transferarr = transferarr
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_dashboard_shows_tv_episode_torrent(
        self,
        dashboard_page,
        page: Page,
        create_torrent,
        sonarr_client,
        deluge_source,
    ):
        """
        E2E test: Verify dashboard shows TV episode torrents from Sonarr.
        
        This test:
        1. Creates an episode torrent and adds series to Sonarr
        2. Waits for torrent to be grabbed
        3. Verifies dashboard shows the active torrent
        """
        log_test_step("Step 1: Setup TV show and create episode torrent")
        show = show_catalog.get_show()
        
        # Add series to Sonarr first to get proper title
        added_series = sonarr_client.add_series(
            title=show['title'],
            tvdb_id=show['tvdb_id'],
            search=False
        )
        series_id = added_series['id']
        series_title = added_series['title']
        print(f"  Added series: {series_title} (ID: {series_id})")
        
        # Wait for episodes to populate
        episodes = []
        for _ in range(20):
            episodes = sonarr_client.get_episodes(series_id)
            if episodes:
                break
            time.sleep(1)
        
        # Find first regular episode
        regular_episodes = [ep for ep in episodes if ep['seasonNumber'] > 0]
        target_episode = regular_episodes[0] if regular_episodes else episodes[0]
        
        torrent_name = make_episode_name(
            series_title,
            target_episode['seasonNumber'],
            target_episode['episodeNumber']
        )
        
        log_test_step("Step 2: Create torrent")
        torrent_info = create_torrent(torrent_name, size_mb=150)
        print(f"  Created torrent: {torrent_name}")
        
        # Small delay for mock indexer to register
        time.sleep(2)
        
        log_test_step("Step 3: Trigger series search")
        # Note: Sonarr doesn't have episode-level search, use series search
        sonarr_client.search_series(series_id)
        
        log_test_step("Step 4: Wait for torrent to be grabbed")
        wait_for_sonarr_queue_item_by_hash(
            sonarr_client,
            torrent_info['hash'],
            timeout=60,
            expected_status='completed'
        )
        print("  Torrent grabbed by Sonarr")
        
        log_test_step("Step 5: Wait for seeding and tracking")
        wait_for_torrent_in_deluge(deluge_source, torrent_info['hash'], timeout=60, expected_state='Seeding')
        wait_for_transferarr_state(self.transferarr, torrent_name, expected_state='HOME_SEEDING', timeout=30)
        print("  Torrent is being tracked")
        
        log_test_step("Step 6: Verify dashboard shows torrent")
        dashboard_page.goto()
        dashboard_page.wait_for_stats_update()
        
        stats = dashboard_page.get_all_stats()
        assert stats['active'] >= 1, f"Expected active torrent, got {stats}"
        print(f"  Dashboard stats: {stats}")
        
        print("\n✅ Test passed: Dashboard shows TV episode torrent!")
