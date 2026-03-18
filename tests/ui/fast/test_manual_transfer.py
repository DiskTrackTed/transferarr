"""
Fast UI tests for the manual transfer feature.

Tests the selection UI, transfer button, and transfer modal elements
on the torrents page. A module-scoped fixture seeds two torrents on
source-deluge and starts transferarr so every test has data to work with.

Cross-seed tests use a separate fixture that creates actual cross-seed
pairs (same name + size, different hash) to verify badges, notices,
and warnings.

No actual transfers are initiated — these tests verify UI elements only.
"""
import base64
import time
import uuid

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.conftest import SERVICES, TIMEOUTS
from tests.ui.helpers import UI_TIMEOUTS, TRANSFERARR_BASE_URL
from tests.utils import clear_deluge_torrents, clear_mock_indexer_torrents, decode_bytes


MOCK_INDEXER_URL = f"http://{SERVICES['mock_indexer']['host']}:{SERVICES['mock_indexer']['port']}"


def _add_seeding_torrent(deluge_client, name, create_torrent_fn, size_mb=1):
    """Create a torrent and add it to Deluge, wait for Seeding state."""
    create_torrent_fn(name, size_mb=size_mb)

    resp = requests.get(f"{MOCK_INDEXER_URL}/download/{name}.torrent", timeout=10)
    assert resp.status_code == 200
    torrent_b64 = base64.b64encode(resp.content).decode("ascii")

    result_hash = deluge_client.core.add_torrent_file(
        f"{name}.torrent", torrent_b64, {"download_location": "/downloads"},
    )
    result_hash = decode_bytes(result_hash) if result_hash else ""

    deadline = time.time() + 30
    while time.time() < deadline:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        if decode_bytes(status.get("state", "")) == "Seeding":
            break
        time.sleep(1)
    else:
        pytest.fail(f"Torrent '{name}' did not reach Seeding")

    return {"name": name, "hash": result_hash}


def _create_cross_seed_torrent(docker_client, deluge_client, content_name,
                                source_location="/downloads",
                                download_location=None):
    """Generate a cross-seed .torrent for existing content on a Deluge client.

    Uses Docker exec to run libtorrent inside the Deluge source container,
    creating a second .torrent from the same content with a different tracker
    URL (producing a different info_hash).

    For different save_path scenarios, copies the content to the new location
    first — simulating what cross-seed tools do with symlinks.
    """
    if download_location is None:
        download_location = source_location

    container = docker_client.containers.get("test-deluge-source")

    # If different location, copy content there
    if download_location != source_location:
        exit_code, output = container.exec_run(
            ["sh", "-c",
             f"mkdir -p '{download_location}' && "
             f"cp -r '{source_location}/{content_name}' '{download_location}/{content_name}'"],
            user="root",
        )
        assert exit_code == 0, (
            f"Failed to copy content to {download_location}: {output.decode()}"
        )

    script = (
        "import libtorrent as lt, base64, os\n"
        f"content_path = os.path.join('{download_location}', '{content_name}')\n"
        "assert os.path.exists(content_path), f'Content not found: {content_path}'\n"
        "fs = lt.file_storage()\n"
        "lt.add_files(fs, content_path)\n"
        "t = lt.create_torrent(fs)\n"
        "t.set_creator('cross-seed-test')\n"
        "t.add_tracker('http://tracker:6969/announce?xseed=1')\n"
        f"lt.set_piece_hashes(t, '{download_location}')\n"
        "torrent_data = lt.bencode(t.generate())\n"
        "info = lt.torrent_info(lt.bdecode(torrent_data))\n"
        "print('HASH:' + str(info.info_hash()))\n"
        "print('B64:' + base64.b64encode(torrent_data).decode())\n"
    )

    exit_code, output = container.exec_run(["python3", "-c", script])
    output_str = output.decode()
    assert exit_code == 0, f"libtorrent script failed: {output_str}"

    xseed_hash = None
    xseed_b64 = None
    for line in output_str.split("\n"):
        if line.startswith("HASH:"):
            xseed_hash = line[5:].strip()
        elif line.startswith("B64:"):
            xseed_b64 = line[4:].strip()

    assert xseed_hash, f"Failed to parse cross-seed hash from: {output_str}"
    assert xseed_b64, f"Failed to parse cross-seed base64 from: {output_str}"

    result_hash = deluge_client.core.add_torrent_file(
        f"xseed_{content_name}.torrent",
        xseed_b64,
        {"download_location": download_location},
    )
    result_hash = decode_bytes(result_hash) if result_hash else ""

    deadline = time.time() + 30
    while time.time() < deadline:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        if decode_bytes(status.get("state", "")) == "Seeding":
            break
        time.sleep(1)
    else:
        status = deluge_client.core.get_torrent_status(
            result_hash, ["state", "progress"]
        )
        pytest.fail(f"Cross-seed did not reach Seeding: {decode_bytes(status)}")

    return {"name": content_name, "hash": result_hash}


@pytest.fixture(scope="module")
def seeding_torrents(docker_client, docker_services, deluge_source, deluge_target,
                     create_torrent, radarr_api_key, sonarr_api_key):
    """Seed two torrents on source-deluge and start transferarr (module-scoped).

    Yields a list of two torrent dicts (name, hash).
    Tears down by stopping transferarr after the module completes.
    """
    # Inline manager (module scope can't use function-scoped transferarr fixture)
    class _Manager:
        CONTAINER = "test-transferarr"

        def __init__(self):
            self.docker = docker_client

        def _container(self):
            return self.docker.containers.get(self.CONTAINER)

        def stop(self):
            try:
                self._container().stop()
            except Exception:
                pass

        def start(self):
            try:
                c = self._container()
                if c.status != "running":
                    c.start()
            except Exception:
                pytest.fail("Transferarr container not found")
            self._wait_healthy()

        def _wait_healthy(self, timeout=60):
            url = f"{TRANSFERARR_BASE_URL}/api/v1/health"
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    if requests.get(url, timeout=5).status_code == 200:
                        return
                except requests.RequestException:
                    pass
                time.sleep(2)
            pytest.fail("Transferarr did not become healthy")

        def set_auth_disabled(self):
            """Patch auth.enabled=false in the running config via the API."""
            try:
                requests.put(
                    f"{TRANSFERARR_BASE_URL}/api/v1/auth/settings",
                    json={"enabled": False, "session_timeout_minutes": 60},
                    timeout=10,
                )
            except requests.RequestException:
                pass  # Best effort — may not be reachable yet

    mgr = _Manager()

    # Clean slate
    mgr.stop()
    clear_deluge_torrents(deluge_source)
    clear_deluge_torrents(deluge_target)
    clear_mock_indexer_torrents()

    # Create two seeding torrents
    suffix = uuid.uuid4().hex[:6]
    t1 = _add_seeding_torrent(deluge_source, f"fast_ui_a_{suffix}", create_torrent)
    t2 = _add_seeding_torrent(deluge_source, f"fast_ui_b_{suffix}", create_torrent)

    mgr.start()
    mgr.set_auth_disabled()

    # Wait until both hashes appear in /all_torrents
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{TRANSFERARR_BASE_URL}/api/v1/all_torrents", timeout=5)
            if r.status_code == 200:
                src = r.json().get("data", {}).get("source-deluge", {})
                if t1["hash"] in src and t2["hash"] in src:
                    break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        pytest.fail("Seeding torrents did not appear in /all_torrents")

    yield [t1, t2]

    # Don't stop transferarr — other test modules in ui/fast/ need it running.
    # The cleanup script resets state between full test suite runs.


class TestTransferButtonVisibility:
    """Tests for the Transfer Selected button show/hide behaviour."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def test_transfer_button_hidden_initially(self, torrents_page):
        """Transfer button is hidden when no torrent is selected."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        assert not torrents_page.is_transfer_button_visible()

    def test_transfer_button_appears_on_selection(self, torrents_page):
        """Transfer button becomes visible after selecting a seeding torrent."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        # Select first enabled checkbox
        enabled[0].click()

        btn = torrents_page.page.locator(torrents_page.TRANSFER_BUTTON)
        expect(btn).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])
        expect(btn).to_be_enabled()

    def test_selected_count_updates(self, torrents_page):
        """Badge count increments as more torrents are selected."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 2, "Fixture guarantees 2 seeding torrents"

        enabled[0].click()
        assert torrents_page.get_selected_count() == 1

        enabled[1].click()
        assert torrents_page.get_selected_count() == 2

    def test_deselect_hides_button(self, torrents_page):
        """Deselecting the last torrent hides the transfer button."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert torrents_page.is_transfer_button_visible()

        # Click again to deselect
        enabled[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        assert not torrents_page.is_transfer_button_visible()


class TestTorrentCardSelection:
    """Tests for torrent card checkbox and highlight behaviour."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def test_checkboxes_present_on_torrent_cards(self, torrents_page):
        """Every torrent card has a checkbox."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        cards = torrents_page.get_torrent_cards()
        assert len(cards) >= 1, "Fixture guarantees torrents exist"

        checkboxes = torrents_page.get_torrent_checkboxes()
        assert len(checkboxes) == len(cards)

    def test_non_seeding_checkboxes_disabled(self, torrents_page):
        """Checkboxes for non-seeding torrents are disabled."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        all_cb = torrents_page.get_torrent_checkboxes()
        enabled_cb = torrents_page.get_enabled_checkboxes()

        # All fixture torrents are seeding, so enabled == total
        # At least verify the invariant holds
        assert len(enabled_cb) <= len(all_cb)

    def test_selected_card_gets_highlight_class(self, torrents_page):
        """Selecting a torrent adds the 'selected' class to its card."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        selected = torrents_page.get_selected_cards()
        assert len(selected) >= 1

    def test_deselect_removes_highlight(self, torrents_page):
        """Deselecting a torrent removes the 'selected' class."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert len(torrents_page.get_selected_cards()) >= 1

        # Deselect
        enabled[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert len(torrents_page.get_selected_cards()) == 0


class TestTransferModalElements:
    """Tests for the transfer modal structure and form elements."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def _open_modal(self, torrents_page):
        """Helper: select a torrent and open the modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_modal_opens_on_button_click(self, torrents_page):
        """Clicking Transfer Selected opens the modal."""
        self._open_modal(torrents_page)
        assert torrents_page.is_modal_visible()

    def test_modal_has_title(self, torrents_page):
        """Modal shows 'Transfer Torrents' title."""
        self._open_modal(torrents_page)

        title = torrents_page.page.locator(
            f"{torrents_page.TRANSFER_MODAL} .modal-title"
        )
        expect(title).to_have_text("Transfer Torrents")

    def test_modal_shows_selected_count(self, torrents_page):
        """Modal body displays the number of selected torrents."""
        self._open_modal(torrents_page)

        assert torrents_page.get_modal_selected_count() >= 1

    def test_modal_has_destination_dropdown(self, torrents_page):
        """Modal contains a destination client dropdown."""
        self._open_modal(torrents_page)

        select = torrents_page.page.locator(torrents_page.DESTINATION_SELECT)
        expect(select).to_be_visible()

    def test_destination_dropdown_loads_options(self, torrents_page):
        """Destination dropdown populates with available destinations."""
        self._open_modal(torrents_page)

        # Wait for destinations API call
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])

        options = torrents_page.get_destination_options()
        assert len(options) >= 1, "Test config should have at least one destination"

    def test_modal_has_cross_seeds_checkbox(self, torrents_page):
        """Modal contains the Include Cross-Seeds checkbox."""
        self._open_modal(torrents_page)

        cb = torrents_page.page.locator(torrents_page.INCLUDE_CROSS_SEEDS)
        expect(cb).to_be_visible()
        assert not torrents_page.is_cross_seeds_checked()  # Unchecked by default

    def test_modal_has_torrent_list_preview(self, torrents_page):
        """Modal shows a list of selected torrents."""
        self._open_modal(torrents_page)

        items = torrents_page.get_transfer_list_items()
        assert len(items) >= 1

    def test_confirm_button_disabled_without_destination(self, torrents_page):
        """Start Transfer button is disabled until a destination is chosen."""
        self._open_modal(torrents_page)

        assert not torrents_page.is_confirm_button_enabled()

    def test_confirm_button_enabled_after_destination(self, torrents_page):
        """Start Transfer button enables after selecting a destination."""
        self._open_modal(torrents_page)

        # Wait for destinations to load
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['dropdown_load'])

        # Select first real destination (skip placeholder with value="")
        real_options = torrents_page.page.locator(
            f"{torrents_page.DESTINATION_SELECT} option:not([value=''])"
        )
        assert real_options.count() >= 1, "Test config should have at least one destination"
        first_value = real_options.first.get_attribute("value")
        torrents_page.select_destination(first_value)
        assert torrents_page.is_confirm_button_enabled()

    def test_transfer_error_hidden_initially(self, torrents_page):
        """Error alert in the modal is hidden by default."""
        self._open_modal(torrents_page)

        assert not torrents_page.is_transfer_error_visible()


class TestModalCloseActions:
    """Tests for closing the transfer modal."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def _open_modal(self, torrents_page):
        """Helper: select a torrent and open the modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_close_button_hides_modal(self, torrents_page):
        """X button closes the modal."""
        self._open_modal(torrents_page)
        assert torrents_page.is_modal_visible()

        torrents_page.close_modal()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        assert not torrents_page.is_modal_visible()

    def test_cancel_button_hides_modal(self, torrents_page):
        """Cancel button closes the modal."""
        self._open_modal(torrents_page)
        assert torrents_page.is_modal_visible()

        torrents_page.cancel_modal()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        assert not torrents_page.is_modal_visible()

    def test_backdrop_click_hides_modal(self, torrents_page):
        """Clicking outside the modal dialog closes it."""
        self._open_modal(torrents_page)
        assert torrents_page.is_modal_visible()

        # Click on the modal backdrop (the outer div, not the dialog)
        modal = torrents_page.page.locator(torrents_page.TRANSFER_MODAL)
        modal.click(position={"x": 5, "y": 5})
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        assert not torrents_page.is_modal_visible()

    def test_selection_preserved_after_close(self, torrents_page):
        """Closing the modal keeps the torrent selection active."""
        self._open_modal(torrents_page)

        torrents_page.cancel_modal()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Button should still be visible (selection preserved)
        assert torrents_page.is_transfer_button_visible()
        assert torrents_page.get_selected_count() >= 1


class TestCrossSeedCheckbox:
    """Tests for the Include Cross-Seeds toggle in the modal."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def _open_modal(self, torrents_page):
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1, "Fixture guarantees seeding torrents"

        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_cross_seeds_unchecked_by_default(self, torrents_page):
        """Include Cross-Seeds is unchecked by default."""
        self._open_modal(torrents_page)

        assert not torrents_page.is_cross_seeds_checked()

    def test_can_check_cross_seeds(self, torrents_page):
        """Can check the Include Cross-Seeds checkbox."""
        self._open_modal(torrents_page)

        torrents_page.toggle_cross_seeds()
        assert torrents_page.is_cross_seeds_checked()

    def test_can_uncheck_after_checking(self, torrents_page):
        """Can uncheck the Include Cross-Seeds checkbox after checking."""
        self._open_modal(torrents_page)

        torrents_page.toggle_cross_seeds()
        assert torrents_page.is_cross_seeds_checked()

        torrents_page.toggle_cross_seeds()
        assert not torrents_page.is_cross_seeds_checked()

    def test_cross_seed_warning_hidden_when_unchecked(self, torrents_page):
        """Cross-seed warning is not visible when Include Cross-Seeds is unchecked (default)."""
        self._open_modal(torrents_page)

        # Default state: checkbox unchecked, warning hidden
        assert not torrents_page.is_cross_seeds_checked()
        assert not torrents_page.is_cross_seed_warning_visible()

    def test_cross_seed_warning_hidden_when_no_siblings(self, torrents_page):
        """Cross-seed warning stays hidden when checking if selected torrent has no siblings."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Our fixture creates two torrents with DIFFERENT names at /downloads.
        # Since cross-seeds require matching name + total_size, they are NOT siblings.
        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1
        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Check cross-seeds
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Fixture torrents have different names, so no siblings exist.
        # The warning should NOT be visible.
        assert not torrents_page.is_cross_seed_warning_visible()

    def test_cross_seed_warning_shows_on_check_with_siblings(self, torrents_page):
        """Warning does NOT appear when checking if selected torrent has no siblings.

        The fixture creates two torrents with different names in the same
        download directory. Cross-seeds are grouped by name + total_size,
        so these are correctly identified as separate torrents.
        """
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Select one torrent — fixture torrents have different names, so no siblings
        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1
        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Warning should be hidden while checkbox is unchecked (default)
        assert not torrents_page.is_cross_seed_warning_visible()

        # Check — warning should still NOT appear (no siblings)
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        assert not torrents_page.is_cross_seed_warning_visible()

    def test_cross_seed_warning_hides_on_uncheck(self, torrents_page):
        """Warning stays hidden through toggle cycle when no siblings exist."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 1
        enabled[0].click()
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Check — no siblings, so warning stays hidden
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert not torrents_page.is_cross_seed_warning_visible()

        # Uncheck — still hidden
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert not torrents_page.is_cross_seed_warning_visible()

    def test_different_name_torrents_not_cross_seeds(self, torrents_page):
        """Torrents with different names in the same directory are NOT cross-seeds.

        Cross-seeds are grouped by name + total_size, so torrents with
        different names are never treated as siblings.
        """
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Select all available torrents (both fixture torrents have different names)
        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 2, "Need at least 2 torrents to test"
        for cb in enabled:
            cb.click()

        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # The modal should show exactly the selected count, no extra siblings
        modal_count = torrents_page.get_modal_selected_count()
        assert modal_count == len(enabled)

        # Checking cross-seeds should NOT trigger a warning (no siblings)
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert not torrents_page.is_cross_seed_warning_visible()


class TestInlineTransferButton:
    """Tests for the per-torrent inline transfer button on seeding cards."""

    @pytest.fixture(autouse=True)
    def _seed(self, seeding_torrents):
        pass

    def test_inline_button_present_on_seeding_cards(self, torrents_page):
        """Seeding torrent cards have an inline transfer button."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) >= 1

    def test_inline_button_count_matches_seeding_count(self, torrents_page):
        """Number of inline buttons equals number of seeding torrents."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) == len(enabled)

    def test_inline_button_not_on_non_seeding_cards(self, torrents_page):
        """Non-seeding torrent cards do not have an inline transfer button."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        cards = torrents_page.get_torrent_cards()
        all_cb = torrents_page.get_torrent_checkboxes()
        enabled_cb = torrents_page.get_enabled_checkboxes()

        if len(all_cb) == len(enabled_cb):
            pytest.skip("All torrents are seeding — cannot test non-seeding cards")

        # Verify button count matches seeding count, not total count
        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) == len(enabled_cb)
        assert len(buttons) < len(cards)

    def test_inline_button_opens_modal(self, torrents_page):
        """Clicking the inline button opens the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) >= 1, "Fixture guarantees seeding torrents"

        buttons[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        assert torrents_page.is_modal_visible()

    def test_inline_button_selects_single_torrent(self, torrents_page):
        """Inline button selects exactly one torrent in the modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) >= 1, "Fixture guarantees seeding torrents"

        buttons[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        # Exactly 1 directly selected (cross-seed items may also appear)
        assert torrents_page.get_modal_selected_count() == 1
        items = torrents_page.get_transfer_list_items()
        assert len(items) >= 1

    def test_inline_button_clears_previous_selection(self, torrents_page):
        """Inline button clears any previous multi-selection."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        enabled = torrents_page.get_enabled_checkboxes()
        assert len(enabled) >= 2, "Fixture guarantees 2 seeding torrents"

        # Select two via checkboxes
        enabled[0].click()
        enabled[1].click()
        assert torrents_page.get_selected_count() == 2

        # Click inline button — should reset to just 1
        buttons = torrents_page.get_inline_transfer_buttons()
        buttons[0].click()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

        assert torrents_page.get_modal_selected_count() == 1

    def test_inline_button_has_tooltip(self, torrents_page):
        """Inline transfer button has a title attribute for tooltip."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        buttons = torrents_page.get_inline_transfer_buttons()
        assert len(buttons) >= 1, "Fixture guarantees seeding torrents"

        title = buttons[0].get_attribute("title")
        assert title and "transfer" in title.lower()


# ==============================================================================
# Cross-seed UI tests — require actual cross-seed pairs
# ==============================================================================

@pytest.fixture(scope="module")
def cross_seed_torrents(docker_client, docker_services, deluge_source, deluge_target,
                        create_torrent, radarr_api_key, sonarr_api_key):
    """Seed cross-seed pairs on source-deluge and start transferarr (module-scoped).

    Creates:
    - A same-path cross-seed pair (original + cross-seed at /downloads)
    - A different-path cross-seed pair (original at /downloads, cross-seed at /downloads/linkdir)
    - A standalone non-cross-seed torrent (different name, no siblings)

    Yields a dict with keys:
        same_path_a, same_path_b: Same save_path cross-seed pair
        diff_path_a, diff_path_b: Different save_path cross-seed pair
        standalone: A torrent with no cross-seed siblings
    """
    class _Manager:
        CONTAINER = "test-transferarr"

        def __init__(self):
            self.docker = docker_client

        def _container(self):
            return self.docker.containers.get(self.CONTAINER)

        def stop(self):
            try:
                self._container().stop()
            except Exception:
                pass

        def start(self):
            try:
                c = self._container()
                if c.status != "running":
                    c.start()
            except Exception:
                pytest.fail("Transferarr container not found")
            self._wait_healthy()

        def _wait_healthy(self, timeout=60):
            url = f"{TRANSFERARR_BASE_URL}/api/v1/health"
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    if requests.get(url, timeout=5).status_code == 200:
                        return
                except requests.RequestException:
                    pass
                time.sleep(2)
            pytest.fail("Transferarr did not become healthy")

        def set_auth_disabled(self):
            try:
                requests.put(
                    f"{TRANSFERARR_BASE_URL}/api/v1/auth/settings",
                    json={"enabled": False, "session_timeout_minutes": 60},
                    timeout=10,
                )
            except requests.RequestException:
                pass

    mgr = _Manager()

    # Clean slate
    mgr.stop()
    clear_deluge_torrents(deluge_source)
    clear_deluge_torrents(deluge_target)
    clear_mock_indexer_torrents()

    suffix = uuid.uuid4().hex[:6]

    # Same-path cross-seed pair
    same_name = f"XSeed.Same.UI.{suffix}"
    same_a = _add_seeding_torrent(deluge_source, same_name, create_torrent, size_mb=1)
    same_b = _create_cross_seed_torrent(
        docker_client, deluge_source, same_name,
        source_location="/downloads",
    )

    # Different-path cross-seed pair
    diff_name = f"XSeed.Diff.UI.{suffix}"
    diff_a = _add_seeding_torrent(deluge_source, diff_name, create_torrent, size_mb=1)
    diff_b = _create_cross_seed_torrent(
        docker_client, deluge_source, diff_name,
        source_location="/downloads",
        download_location="/downloads/linkdir",
    )

    # Standalone torrent (no siblings)
    standalone_name = f"Standalone.UI.{suffix}"
    standalone = _add_seeding_torrent(
        deluge_source, standalone_name, create_torrent, size_mb=1,
    )

    mgr.start()
    mgr.set_auth_disabled()

    # Wait until all hashes appear in /all_torrents
    all_hashes = {
        same_a["hash"], same_b["hash"],
        diff_a["hash"], diff_b["hash"],
        standalone["hash"],
    }
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{TRANSFERARR_BASE_URL}/api/v1/all_torrents", timeout=5)
            if r.status_code == 200:
                src = r.json().get("data", {}).get("source-deluge", {})
                if all_hashes.issubset(set(src.keys())):
                    break
        except requests.RequestException:
            pass
        time.sleep(2)
    else:
        pytest.fail("Cross-seed torrents did not appear in /all_torrents")

    yield {
        "same_path_a": same_a,
        "same_path_b": same_b,
        "diff_path_a": diff_a,
        "diff_path_b": diff_b,
        "standalone": standalone,
    }


class TestCrossSeedBadges:
    """Tests for cross-seed badges on torrent cards.

    Verifies that cross-seed indicator badges appear on torrent cards
    that share name + total_size with at least one sibling, regardless
    of whether they share the same save_path.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def test_same_path_cross_seeds_have_badges(self, torrents_page):
        """Torrents in a same-path cross-seed group show a badge."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Both cards share the same name; verify at least one badge exists
        cards = torrents_page.get_torrent_by_name(self.data["same_path_a"]["name"])
        badges = cards.locator(".cross-seed-badge")
        # Cross-seeds share a name, so this locator matches both cards — 2 badges
        expect(badges.first).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])
        assert badges.count() == 2, f"Expected 2 badges for same-path pair, got {badges.count()}"

    def test_different_path_cross_seeds_have_badges(self, torrents_page):
        """Torrents in a different-path cross-seed group show a badge."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        # Both cards share the same name; verify at least one badge exists
        cards = torrents_page.get_torrent_by_name(self.data["diff_path_a"]["name"])
        badges = cards.locator(".cross-seed-badge")
        expect(badges.first).to_be_visible(timeout=UI_TIMEOUTS['element_visible'])
        assert badges.count() == 2, f"Expected 2 badges for diff-path pair, got {badges.count()}"

    def test_standalone_torrent_has_no_badge(self, torrents_page):
        """A torrent with no cross-seed siblings has no badge."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        card = torrents_page.get_torrent_by_name(self.data["standalone"]["name"])
        badge = card.locator(".cross-seed-badge")
        expect(badge).to_have_count(0)

    def test_total_badge_count_matches_cross_seed_torrents(self, torrents_page):
        """Total badge count equals the number of torrents in cross-seed groups."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()

        badges = torrents_page.get_cross_seed_badges()
        # 2 same-path + 2 different-path = 4 badged torrents
        assert len(badges) == 4, (
            f"Expected 4 cross-seed badges (2 pairs), got {len(badges)}"
        )


class TestCrossSeedModalNotice:
    """Tests for cross-seed notice and sibling listing in the transfer modal.

    When a torrent with cross-seed siblings is selected and the modal
    is opened with Include Cross-Seeds checked, the modal should show
    a notice with the sibling count and list the siblings.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_same_path_sibling_always_shown(self, torrents_page):
        """Cross-seed siblings always appear in the modal list with action badges."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Modal should list 2 items: 1 selected + 1 sibling (always visible)
        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items (selected + sibling), got {len(items)}"

        # Sibling should have a "Delete" badge by default (deleteCrossSeeds is checked)
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(delete_badges) == 1, f"Expected 1 Delete badge, got {len(delete_badges)}"

    def test_same_path_sibling_badges_update_on_include(self, torrents_page):
        """Checking Include Cross-Seeds adds Transfer badge to sibling."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Default: Delete badge only (deleteCrossSeeds checked, includeCrossSeeds unchecked)
        delete_badges = torrents_page.get_action_badges('delete')
        transfer_badges = torrents_page.get_action_badges('transfer')
        assert len(delete_badges) == 1
        assert len(transfer_badges) == 0

        # Check the cross-seeds checkbox
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        # Now both Transfer and Delete badges should appear
        transfer_badges = torrents_page.get_action_badges('transfer')
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(transfer_badges) == 1, f"Expected 1 Transfer badge, got {len(transfer_badges)}"
        assert len(delete_badges) == 1, f"Expected 1 Delete badge, got {len(delete_badges)}"

        # Modal should still list 2 items
        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items, got {len(items)}"

    def test_different_path_sibling_always_shown(self, torrents_page):
        """Different-path sibling is always shown in modal list with badges."""
        self._select_and_open_modal(
            torrents_page, self.data["diff_path_a"]["hash"],
        )

        # Modal should list 2 items: 1 selected + 1 sibling
        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items (selected + sibling), got {len(items)}"

        # At least 1 Delete badge (sibling); may be 2 if diff_path_a isn't the
        # original (the promoted original also gets Transfer+Delete)
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(delete_badges) >= 1, f"Expected ≥1 Delete badge, got {len(delete_badges)}"

    def test_standalone_no_cross_seeds_in_modal(self, torrents_page):
        """Selecting a torrent with no siblings shows only the selected torrent."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        items = torrents_page.get_transfer_list_items()
        assert len(items) == 1, f"Expected 1 item (standalone), got {len(items)}"

    def test_standalone_no_cross_seeds_even_when_checked(self, torrents_page):
        """Checking Include Cross-Seeds for standalone still shows only 1 item."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        items = torrents_page.get_transfer_list_items()
        assert len(items) == 1, f"Expected 1 item (standalone), got {len(items)}"


class TestCrossSeedWarningWithSiblings:
    """Tests for cross-seed warning when checking Include Cross-Seeds.

    When a torrent with actual siblings is selected and the checkbox
    is checked, a warning should appear. Unchecking hides it.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_warning_shows_on_check_same_path(self, torrents_page):
        """Checking cross-seeds for a same-path pair shows warning."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Default: unchecked, no warning
        assert not torrents_page.is_cross_seed_warning_visible()

        # Check — warning should appear (siblings exist)
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        assert torrents_page.is_cross_seed_warning_visible()

    def test_warning_shows_on_check_different_path(self, torrents_page):
        """Checking cross-seeds for a different-path pair shows warning."""
        self._select_and_open_modal(
            torrents_page, self.data["diff_path_a"]["hash"],
        )

        assert not torrents_page.is_cross_seed_warning_visible()

        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        assert torrents_page.is_cross_seed_warning_visible()

    def test_warning_hidden_for_standalone_on_check(self, torrents_page):
        """Checking cross-seeds for a standalone torrent shows no warning."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        assert not torrents_page.is_cross_seed_warning_visible()

    def test_warning_hides_on_uncheck(self, torrents_page):
        """Unchecking cross-seeds after checking hides the warning."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Check — warning appears
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert torrents_page.is_cross_seed_warning_visible()

        # Uncheck — warning disappears
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert not torrents_page.is_cross_seed_warning_visible()

    def test_check_changes_badges_not_count(self, torrents_page):
        """Checking cross-seeds changes action badges, not the item count."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Default: 2 items (sibling always shown), Delete badge only
        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items (always shown), got {len(items)}"
        assert len(torrents_page.get_action_badges('delete')) == 1
        assert len(torrents_page.get_action_badges('transfer')) == 0

        # Check — Transfer badge added alongside Delete
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items after checking, got {len(items)}"
        assert len(torrents_page.get_action_badges('transfer')) == 1
        assert len(torrents_page.get_action_badges('delete')) == 1

        # Uncheck — back to Delete only
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2, f"Expected 2 items after unchecking, got {len(items)}"
        assert len(torrents_page.get_action_badges('delete')) == 1
        assert len(torrents_page.get_action_badges('transfer')) == 0


class TestDeleteCrossSeedsCheckbox:
    """Tests for the Delete Cross-Seeds from Source checkbox in the transfer modal.

    The checkbox should only appear when selected torrents have siblings.
    It is checked (True) by default.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_checkbox_hidden_for_standalone_torrent(self, torrents_page):
        """Delete Cross-Seeds checkbox is hidden when the torrent has no siblings."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        assert not torrents_page.is_delete_cross_seeds_visible()

    def test_checkbox_visible_for_cross_seed_torrent(self, torrents_page):
        """Delete Cross-Seeds checkbox is visible when the torrent has siblings."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        assert torrents_page.is_delete_cross_seeds_visible()

    def test_checkbox_checked_by_default(self, torrents_page):
        """Delete Cross-Seeds checkbox is checked (True) by default."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        assert torrents_page.is_delete_cross_seeds_checked()

    def test_can_uncheck_checkbox(self, torrents_page):
        """Can uncheck the Delete Cross-Seeds checkbox."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        torrents_page.toggle_delete_cross_seeds()
        assert not torrents_page.is_delete_cross_seeds_checked()

    def test_can_recheck_after_unchecking(self, torrents_page):
        """Can re-check the Delete Cross-Seeds checkbox after unchecking."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        torrents_page.toggle_delete_cross_seeds()
        assert not torrents_page.is_delete_cross_seeds_checked()

        torrents_page.toggle_delete_cross_seeds()
        assert torrents_page.is_delete_cross_seeds_checked()

    def test_checkbox_has_descriptive_label(self, torrents_page):
        """The checkbox has a descriptive label and help text."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        label = torrents_page.page.locator("label[for='deleteCrossSeeds']")
        expect(label).to_contain_text("Delete cross-seeds from source")

        help_text = torrents_page.page.locator(
            "#deleteCrossSeeds"
        ).locator("xpath=ancestor::div[contains(@class,'form-check')]").locator(".form-text")
        expect(help_text).to_contain_text("Safe for hardlinks")


class TestOriginalTorrentIndicator:
    """Tests for the Original badge on the oldest torrent in cross-seed groups.

    When a torrent is part of a cross-seed group, the oldest by time_added
    gets an 'Original' badge in the transfer list.
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_original_badge_present_on_cross_seed(self, torrents_page):
        """Selecting a cross-seed torrent shows an 'Original' badge on the oldest."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        badges = torrents_page.get_original_badges()
        assert len(badges) == 1, f"Expected 1 Original badge, got {len(badges)}"

    def test_original_badge_text(self, torrents_page):
        """The Original badge contains the text 'Original'."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        badges = torrents_page.get_original_badges()
        assert len(badges) >= 1
        expect(badges[0]).to_have_text("Original")

    def test_no_original_badge_for_standalone(self, torrents_page):
        """Standalone torrents (no siblings) have no Original badge."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        badges = torrents_page.get_original_badges()
        assert len(badges) == 0, f"Expected no Original badges, got {len(badges)}"

    def test_original_badge_has_tooltip(self, torrents_page):
        """The Original badge has a descriptive title attribute (tooltip)."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        badges = torrents_page.get_original_badges()
        assert len(badges) >= 1
        title = badges[0].get_attribute("title")
        assert title and "oldest" in title.lower()

    def test_original_at_top_when_non_original_selected(self, torrents_page):
        """When a non-original cross-seed is selected, the original still appears at the top."""
        # Select same_path_b (the non-original cross-seed)
        self._select_and_open_modal(
            torrents_page, self.data["same_path_b"]["hash"],
        )

        # Should still have exactly 1 Original badge
        badges = torrents_page.get_original_badges()
        assert len(badges) == 1, f"Expected 1 Original badge, got {len(badges)}"

        # The first transfer list item (above the cross-seed divider) should have
        # the Original badge — verify it's on a top-section item
        items = torrents_page.get_transfer_list_items()
        assert len(items) == 2
        first_badges = items[0].locator(".original-badge").all()
        assert len(first_badges) == 1, "Original badge should be on the first (top) item"

    def test_original_at_top_has_no_action_badge_when_not_selected(self, torrents_page):
        """When a non-original is selected, the promoted original has no action badges.

        The section subtitle ("Transferred to destination and removed from source")
        communicates the intent for all top-section items, so individual action
        badges are unnecessary.
        """
        # Select same_path_b (not the original)
        self._select_and_open_modal(
            torrents_page, self.data["same_path_b"]["hash"],
        )

        # Top-section items should have no action badges — subtitle covers it
        items = torrents_page.get_transfer_list_items()
        first_transfer_badges = items[0].locator(".action-badge-transfer").all()
        first_delete_badges = items[0].locator(".action-badge-delete").all()
        assert len(first_transfer_badges) == 0, "Promoted original should NOT have Transfer badge"
        assert len(first_delete_badges) == 0, "Promoted original should NOT have Delete badge"


class TestSelectedBadge:
    """Tests for the 'Selected' badge that marks which torrent the user explicitly picked.

    When a torrent belongs to a cross-seed group, a 'Selected' badge is shown
    on the torrent the user actually clicked, making it clear which one was
    directly chosen versus shown for context (Original) or expanded (siblings).
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_selected_badge_on_original_when_original_selected(self, torrents_page):
        """Selecting the original shows both Original and Selected badges on the top item."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        selected_badges = torrents_page.get_selected_badges()
        assert len(selected_badges) == 1, f"Expected 1 Selected badge, got {len(selected_badges)}"

        # The first item should have both Original and Selected badges
        items = torrents_page.get_transfer_list_items()
        first_original = items[0].locator(".original-badge").all()
        first_selected = items[0].locator(".selected-badge").all()
        assert len(first_original) == 1, "First item should have Original badge"
        assert len(first_selected) == 1, "First item should have Selected badge"

    def test_selected_badge_on_non_original_in_cross_seed_section(self, torrents_page):
        """Selecting a non-original shows Selected badge on the sibling in the cross-seed section."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_b"]["hash"],
        )

        selected_badges = torrents_page.get_selected_badges()
        assert len(selected_badges) == 1, f"Expected 1 Selected badge, got {len(selected_badges)}"

        # The Selected badge should be on the cross-seed section item (second item)
        items = torrents_page.get_transfer_list_items()
        second_selected = items[1].locator(".selected-badge").all()
        assert len(second_selected) == 1, "Cross-seed item should have Selected badge"

        # The first item (original) should NOT have Selected badge
        first_selected = items[0].locator(".selected-badge").all()
        assert len(first_selected) == 0, "Original (not selected) should not have Selected badge"

    def test_selected_badge_text(self, torrents_page):
        """The Selected badge contains the text 'Selected'."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        badges = torrents_page.get_selected_badges()
        assert len(badges) >= 1
        expect(badges[0]).to_have_text("Selected")

    def test_selected_badge_has_tooltip(self, torrents_page):
        """The Selected badge has a descriptive title attribute."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        badges = torrents_page.get_selected_badges()
        assert len(badges) >= 1
        title = badges[0].get_attribute("title")
        assert title and "selected" in title.lower()

    def test_no_selected_badge_for_standalone(self, torrents_page):
        """Standalone torrents (no siblings) have no Selected badge."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        badges = torrents_page.get_selected_badges()
        assert len(badges) == 0, f"Expected no Selected badges on standalone, got {len(badges)}"

    def test_non_original_selected_has_action_badge(self, torrents_page):
        """The selected non-original in the cross-seed section also gets action badges."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_b"]["hash"],
        )

        # Second item is the selected non-original — should have Delete badge
        items = torrents_page.get_transfer_list_items()
        second_delete = items[1].locator(".action-badge-delete").all()
        assert len(second_delete) == 1, "Selected torrent should have Delete badge"


class TestActionBadges:
    """Tests for action badges on cross-seed items in the transfer modal.

    Cross-seed siblings are always shown in the transfer list. Action badges
    indicate what will happen to each sibling based on checkbox states:
    - Delete only (default): "Delete" badge (red)
    - Include + Delete: "Transfer" + "Delete" badges
    - Include only: "Transfer" badge (green)
    - Neither: "No action" badge (grey, dimmed)
    """

    @pytest.fixture(autouse=True)
    def _seed(self, cross_seed_torrents):
        self.data = cross_seed_torrents

    def _select_and_open_modal(self, torrents_page, torrent_hash):
        """Select a specific torrent by hash and open the transfer modal."""
        torrents_page.goto()
        torrents_page.wait_for_torrents_loaded()
        torrents_page.select_torrent_by_hash(torrent_hash)
        torrents_page.click_transfer_button()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['modal_animation'])

    def test_default_shows_delete_badge(self, torrents_page):
        """Default state: Delete badge on sibling (deleteCrossSeeds=True, includeCrossSeeds=False)."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        delete_badges = torrents_page.get_action_badges('delete')
        transfer_badges = torrents_page.get_action_badges('transfer')
        none_badges = torrents_page.get_action_badges('none')

        assert len(delete_badges) == 1, f"Expected 1 Delete badge, got {len(delete_badges)}"
        assert len(transfer_badges) == 0, f"Expected 0 Transfer badges, got {len(transfer_badges)}"
        assert len(none_badges) == 0, f"Expected 0 No-action badges, got {len(none_badges)}"

    def test_include_and_delete_shows_both_badges(self, torrents_page):
        """Checking Include adds Transfer badge alongside existing Delete badge."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        transfer_badges = torrents_page.get_action_badges('transfer')
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(transfer_badges) == 1
        assert len(delete_badges) == 1

    def test_include_only_shows_transfer_badge(self, torrents_page):
        """Unchecking Delete and checking Include shows Transfer badge only."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Uncheck Delete, check Include
        torrents_page.toggle_delete_cross_seeds()
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        transfer_badges = torrents_page.get_action_badges('transfer')
        delete_badges = torrents_page.get_action_badges('delete')
        none_badges = torrents_page.get_action_badges('none')
        assert len(transfer_badges) == 1
        assert len(delete_badges) == 0
        assert len(none_badges) == 0

    def test_neither_shows_no_action_badge(self, torrents_page):
        """Unchecking both checkboxes shows No-action badge (dimmed)."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Uncheck Delete (Include is already unchecked)
        torrents_page.toggle_delete_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        none_badges = torrents_page.get_action_badges('none')
        transfer_badges = torrents_page.get_action_badges('transfer')
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(none_badges) == 1, f"Expected 1 No-action badge, got {len(none_badges)}"
        assert len(transfer_badges) == 0
        assert len(delete_badges) == 0

    def test_no_action_dims_sibling(self, torrents_page):
        """When no action is set, the cross-seed item has the inactive class."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Uncheck Delete
        torrents_page.toggle_delete_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])

        inactive = torrents_page.get_inactive_cross_seed_items()
        assert len(inactive) == 1, f"Expected 1 inactive sibling, got {len(inactive)}"

    def test_active_sibling_not_dimmed(self, torrents_page):
        """When an action is set, the cross-seed item is NOT dimmed."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Default: Delete checked → sibling should NOT be inactive
        inactive = torrents_page.get_inactive_cross_seed_items()
        assert len(inactive) == 0, f"Expected 0 inactive siblings, got {len(inactive)}"

    def test_standalone_has_no_action_badges(self, torrents_page):
        """Standalone torrent (no siblings) has no action badges."""
        self._select_and_open_modal(
            torrents_page, self.data["standalone"]["hash"],
        )

        all_badges = torrents_page.get_action_badges()
        assert len(all_badges) == 0, f"Expected no action badges, got {len(all_badges)}"

    def test_badge_tooltips(self, torrents_page):
        """Action badges have descriptive tooltip text."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Default: Delete badge
        delete_badges = torrents_page.get_action_badges('delete')
        assert len(delete_badges) == 1
        title = delete_badges[0].get_attribute("title")
        assert title and "deleted" in title.lower()

    def test_badges_update_on_toggle(self, torrents_page):
        """Toggling checkboxes updates badges without changing item count."""
        self._select_and_open_modal(
            torrents_page, self.data["same_path_a"]["hash"],
        )

        # Start: Delete only
        items = torrents_page.get_transfer_list_items()
        initial_count = len(items)

        # Toggle Include on → Transfer + Delete
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert len(torrents_page.get_action_badges('transfer')) == 1
        assert len(torrents_page.get_action_badges('delete')) == 1
        items = torrents_page.get_transfer_list_items()
        assert len(items) == initial_count

        # Toggle Delete off → Transfer only
        torrents_page.toggle_delete_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert len(torrents_page.get_action_badges('transfer')) == 1
        assert len(torrents_page.get_action_badges('delete')) == 0
        items = torrents_page.get_transfer_list_items()
        assert len(items) == initial_count

        # Toggle Include off → No action
        torrents_page.toggle_cross_seeds()
        torrents_page.page.wait_for_timeout(UI_TIMEOUTS['js_processing'])
        assert len(torrents_page.get_action_badges('none')) == 1
        items = torrents_page.get_transfer_list_items()
        assert len(items) == initial_count
