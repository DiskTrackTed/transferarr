"""
E2E UI test for the manual transfer workflow.

This test adds a torrent directly to Deluge (bypassing Radarr/Sonarr),
selects it on the Torrents page, opens the transfer modal, picks a
destination, and verifies the transfer completes.

Prerequisites:
- Full Docker test environment running
- Source and target Deluge instances available
"""
import base64
import time
import uuid
from urllib.parse import quote

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import decode_bytes, wait_for_torrent_in_deluge, wait_for_transferarr_state
from tests.ui.helpers import UI_TIMEOUTS, log_test_step


# Mock indexer URL for downloading .torrent files
MOCK_INDEXER_URL = f"http://{SERVICES.get('mock_indexer', {}).get('host', 'localhost')}:{SERVICES.get('mock_indexer', {}).get('port', 9696)}"


def _get_client_torrents(client_name: str, timeout: int = 10) -> dict:
    """Fetch torrents for a single client from transferarr."""
    response = requests.get(
        f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/clients/{quote(client_name, safe='')}/torrents",
        timeout=timeout,
    )
    assert response.status_code == 200, f"Unexpected status {response.status_code}: {response.text}"
    return response.json().get("data", {})


def _wait_for_client_hash(client_name: str, torrent_hash: str, timeout: int = 30) -> None:
    """Wait until a torrent hash appears in a client's API listing.

    The per-client endpoint can briefly reset connections or return a non-200
    during startup even after the health endpoint is live, so polling here
    treats those transient failures as retryable.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if torrent_hash in _get_client_torrents(client_name):
                return
        except (AssertionError, requests.RequestException):
            pass
        time.sleep(2)

    pytest.fail(
        f"Torrent {torrent_hash} did not appear in the {client_name} client listing within {timeout} s"
    )


def _add_torrent_to_deluge(deluge_client, name, create_torrent_fn, size_mb=1):
    """Create a torrent and add it directly to Deluge.

    Returns dict with keys: name, hash, size_mb.
    """
    torrent_info = create_torrent_fn(name, size_mb=size_mb)
    torrent_hash = torrent_info["hash"]

    # Download .torrent from mock indexer
    resp = requests.get(
        f"{MOCK_INDEXER_URL}/download/{name}.torrent", timeout=10
    )
    assert resp.status_code == 200, f"Failed to download .torrent: {resp.status_code}"
    torrent_b64 = base64.b64encode(resp.content).decode("ascii")

    result_hash = deluge_client.core.add_torrent_file(
        f"{name}.torrent",
        torrent_b64,
        {"download_location": "/downloads"},
    )
    result_hash = decode_bytes(result_hash) if result_hash else ""

    # Wait for Seeding
    deadline = time.time() + 30
    while time.time() < deadline:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        if decode_bytes(status.get("state", "")) == "Seeding":
            break
        time.sleep(1)
    else:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        pytest.fail(
            f"Torrent '{name}' did not reach Seeding. "
            f"State: {decode_bytes(status.get('state', ''))}"
        )

    return {"name": name, "hash": result_hash, "size_mb": size_mb}


class TestManualTransferE2E:
    """End-to-end test: select torrents on the page, transfer via modal."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with auth disabled."""
        transferarr.set_auth_config(enabled=False)
        self.transferarr = transferarr

    @pytest.mark.timeout(TIMEOUTS["torrent_transfer"])
    def test_manual_transfer_via_ui(
        self,
        torrents_page,
        page: Page,
        create_torrent,
        deluge_source,
        deluge_target,
    ):
        """Select a torrent, open modal, pick destination, confirm — verify transfer."""
        unique_name = f"ui_manual_xfer_{uuid.uuid4().hex[:6]}"

        # -----------------------------------------------------------
        # 1. Add a torrent directly to source Deluge
        # -----------------------------------------------------------
        log_test_step("Step 1: Add torrent to source Deluge")
        torrent = _add_torrent_to_deluge(
            deluge_source, unique_name, create_torrent, size_mb=1
        )
        print(f"  Torrent: {unique_name}  hash={torrent['hash']}")

        # -----------------------------------------------------------
        # 2. Start transferarr and wait for the torrent to appear
        # -----------------------------------------------------------
        log_test_step("Step 2: Start transferarr")
        self.transferarr.start(wait_healthy=True)

        _wait_for_client_hash("source-deluge", torrent["hash"])

        # -----------------------------------------------------------
        # 3. Navigate to the Torrents page and select the torrent
        # -----------------------------------------------------------
        log_test_step("Step 3: Select torrent on Torrents page")
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Wait for the page to render the card with our hash
        page.wait_for_timeout(UI_TIMEOUTS["api_response"])  # Wait for poll

        # Click the checkbox for our specific torrent
        cb = page.locator(
            f".torrent-checkbox[data-hash='{torrent['hash']}']"
        )
        expect(cb).to_be_visible(timeout=UI_TIMEOUTS["element_visible"])
        cb.click()

        # Transfer button should now be visible
        btn = page.locator(torrents_page.TRANSFER_BUTTON)
        expect(btn).to_be_visible(timeout=UI_TIMEOUTS["element_visible"])
        expect(btn).to_be_enabled()

        # -----------------------------------------------------------
        # 4. Open modal and pick a destination
        # -----------------------------------------------------------
        log_test_step("Step 4: Open transfer modal and pick destination")
        torrents_page.click_transfer_button()
        page.wait_for_timeout(UI_TIMEOUTS["modal_animation"])
        assert torrents_page.is_modal_visible()

        # Verify the torrent appears in the list preview
        items = torrents_page.get_transfer_list_items()
        assert len(items) >= 1
        item_texts = [i.text_content() for i in items]
        assert any(unique_name in t for t in item_texts), (
            f"Torrent '{unique_name}' not in modal list: {item_texts}"
        )

        # Wait for destinations to load
        page.wait_for_timeout(UI_TIMEOUTS["dropdown_load"])
        options = torrents_page.get_destination_options()
        assert len(options) >= 1, f"No destinations loaded: {options}"

        # Select the first destination (target-deluge)
        torrents_page.select_destination("target-deluge")
        assert torrents_page.is_confirm_button_enabled()

        # -----------------------------------------------------------
        # 5. Confirm transfer
        # -----------------------------------------------------------
        log_test_step("Step 5: Confirm transfer")
        with page.expect_response(
            lambda r: "/api/v1/transfers/manual" in r.url
            and r.request.method == "POST",
            timeout=UI_TIMEOUTS["api_response"],
        ) as resp_info:
            torrents_page.click_confirm_transfer()

        assert resp_info.value.status == 200
        result = resp_info.value.json()
        data = result.get("data", result)
        assert data["total_initiated"] >= 1
        print(f"  Transfer API response: initiated={data['total_initiated']}")

        # Modal should close and selection should clear
        page.wait_for_timeout(UI_TIMEOUTS["modal_animation"])
        assert not torrents_page.is_modal_visible()

        # -----------------------------------------------------------
        # 6. Wait for transfer to complete
        # -----------------------------------------------------------
        log_test_step("Step 6: Wait for torrent on target Deluge")
        # Manual transfers have no media_manager, so they pass through
        # TARGET_SEEDING and are immediately removed from the tracked list.
        # Verify completion by checking the target client directly.
        wait_for_torrent_in_deluge(
            deluge_target,
            torrent["hash"],
            timeout=TIMEOUTS["torrent_transfer"],
            expected_state="Seeding",
        )
        print("  Torrent is Seeding on target")

        # Verify file exists on target
        target_status = deluge_target.core.get_torrent_status(
            torrent["hash"], ["state", "name"]
        )
        target_state = decode_bytes(target_status.get("state", ""))
        assert target_state == "Seeding", f"Target state: {target_state}"

        print("\n✅ Manual transfer E2E passed!")

    @pytest.mark.timeout(TIMEOUTS["torrent_transfer"])
    def test_success_notification_shown(
        self,
        torrents_page,
        page: Page,
        create_torrent,
        deluge_source,
    ):
        """After confirming, a success toast notification appears."""
        unique_name = f"ui_manual_toast_{uuid.uuid4().hex[:6]}"
        torrent = _add_torrent_to_deluge(deluge_source, unique_name, create_torrent, size_mb=1)

        self.transferarr.start(wait_healthy=True)

        _wait_for_client_hash("source-deluge", torrent["hash"])

        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Wait for the torrent card with an enabled checkbox to appear
        deadline = time.time() + 30
        enabled = []
        while time.time() < deadline:
            page.wait_for_timeout(UI_TIMEOUTS["api_response"])
            enabled = torrents_page.get_enabled_checkboxes()
            if len(enabled) > 0:
                break
            page.reload()
            torrents_page.wait_for_torrents_loaded()

        assert len(enabled) > 0, "No seeding torrents available after waiting"

        enabled[0].click()
        torrents_page.click_transfer_button()
        page.wait_for_timeout(UI_TIMEOUTS["modal_animation"])

        # Select destination and confirm
        page.wait_for_timeout(UI_TIMEOUTS["dropdown_load"])
        options = torrents_page.get_destination_options()
        assert len(options) > 0, "No destinations available in dropdown"

        # Select "target-deluge" — the known destination in the test environment
        torrents_page.select_destination("target-deluge")

        with page.expect_response(
            lambda r: "/api/v1/transfers/manual" in r.url
            and r.request.method == "POST",
            timeout=UI_TIMEOUTS["api_response"],
        ):
            torrents_page.click_confirm_transfer()

        # A success notification should appear
        notification = page.locator(".notification-success")
        expect(notification).to_be_visible(timeout=UI_TIMEOUTS["element_visible"])
        expect(notification).to_contain_text("Transfer Initiated")
        print("✅ Success notification shown")
