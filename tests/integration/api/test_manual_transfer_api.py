"""
Integration tests for Manual Transfer API endpoints.

Tests /api/v1/transfers/destinations and /api/v1/transfers/manual
against a running transferarr instance with Docker test services.
"""
import base64
import os
import time
import uuid

import pytest
import requests

from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import (
    decode_bytes,
    wait_for_transferarr_state,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
)


# ==============================================================================
# Helpers
# ==============================================================================

def get_api_url():
    """Get the base API URL for transferarr."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


MOCK_INDEXER_HOST = os.environ.get("MOCK_INDEXER_HOST", "mock-indexer")
MOCK_INDEXER_PORT = os.environ.get("MOCK_INDEXER_PORT", "9696")
MOCK_INDEXER_URL = f"http://{MOCK_INDEXER_HOST}:{MOCK_INDEXER_PORT}"


def add_torrent_to_deluge(deluge_client, name, create_torrent_fn, size_mb=1):
    """Create a torrent and add it directly to a Deluge instance.

    Returns:
        dict with keys: name, hash, size_mb
    """
    torrent_info = create_torrent_fn(name, size_mb=size_mb)
    torrent_hash = torrent_info["hash"]

    # Download .torrent file from mock indexer
    torrent_filename = f"{name}.torrent"
    resp = requests.get(f"{MOCK_INDEXER_URL}/download/{torrent_filename}")
    assert resp.status_code == 200, f"Failed to download .torrent: {resp.status_code}"
    torrent_b64 = base64.b64encode(resp.content).decode("ascii")

    result_hash = deluge_client.core.add_torrent_file(
        f"{name}.torrent",
        torrent_b64,
        {"download_location": "/downloads"},
    )
    result_hash = decode_bytes(result_hash) if result_hash else ""

    # Wait for torrent to be fully loaded and start seeding
    deadline = time.time() + 30
    while time.time() < deadline:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        state = decode_bytes(status.get("state", ""))
        if state == "Seeding":
            break
        time.sleep(1)
    else:
        # Get final state for debugging
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        final_state = decode_bytes(status.get("state", ""))
        pytest.fail(f"Torrent '{name}' did not reach Seeding. State: {final_state}")

    return {"name": name, "hash": result_hash, "size_mb": size_mb}


# ==============================================================================
# GET /api/v1/transfers/destinations
# ==============================================================================

class TestDestinationsEndpoint:
    """Tests for GET /api/v1/transfers/destinations."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with default config (sftp-to-sftp)."""
        transferarr.start(wait_healthy=True)

    def test_returns_destinations_for_known_source(self):
        """Returns destinations when source client has outgoing connections."""
        url = f"{get_api_url()}/transfers/destinations"
        resp = requests.get(
            url, params={"source": "source-deluge"},
            timeout=TIMEOUTS['api_response'],
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        destinations = data["data"]
        assert isinstance(destinations, list)
        assert len(destinations) >= 1

        dest = destinations[0]
        assert "client" in dest
        assert "connection" in dest
        assert "transfer_type" in dest
        assert dest["client"] == "target-deluge"
        assert dest["transfer_type"] in ("file", "torrent")

    def test_returns_400_without_source_param(self):
        """Missing 'source' query param returns 400."""
        url = f"{get_api_url()}/transfers/destinations"
        resp = requests.get(url, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400

    def test_returns_404_for_unknown_source(self):
        """Non-existent source client returns 404."""
        url = f"{get_api_url()}/transfers/destinations"
        resp = requests.get(
            url, params={"source": "no-such-client"},
            timeout=TIMEOUTS['api_response'],
        )

        assert resp.status_code == 404

    def test_returns_empty_for_target_client(self):
        """Target client (no outgoing connections) returns empty list."""
        url = f"{get_api_url()}/transfers/destinations"
        resp = requests.get(
            url, params={"source": "target-deluge"},
            timeout=TIMEOUTS['api_response'],
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []


# ==============================================================================
# POST /api/v1/transfers/manual — validation
# ==============================================================================

class TestManualTransferValidation:
    """Tests for POST /api/v1/transfers/manual validation errors."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with default config."""
        transferarr.start(wait_healthy=True)

    def test_rejects_empty_hashes(self):
        """Empty hashes array returns 400."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400

    def test_rejects_missing_source_client(self):
        """Missing source_client returns 400."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["abc123"],
            "destination_client": "target-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400

    def test_rejects_missing_destination_client(self):
        """Missing destination_client returns 400."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["abc123"],
            "source_client": "source-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400

    def test_rejects_unknown_source_client(self):
        """Unknown source client returns 404."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["abc123"],
            "source_client": "no-such-client",
            "destination_client": "target-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 404

    def test_rejects_unknown_destination_client(self):
        """Unknown destination client returns 404."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "no-such-client",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 404

    def test_rejects_same_source_and_destination(self):
        """Source == destination returns 400."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["abc123"],
            "source_client": "source-deluge",
            "destination_client": "source-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400

    def test_rejects_nonexistent_hash(self):
        """Hash not on source client returns 400."""
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": ["0000000000000000000000000000000000000000"],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400
        assert "not found" in resp.json().get("error", {}).get("message", "").lower()


# ==============================================================================
# POST /api/v1/transfers/manual — happy path
# ==============================================================================

class TestManualTransferInitiation:
    """Tests for POST /api/v1/transfers/manual — successful transfers."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_initiate_single_torrent_transfer(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Initiate a manual transfer for a single seeding torrent."""
        # 1. Create a torrent and add it to source Deluge
        unique_name = f"manual_xfer_single_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(deluge_source, unique_name, create_torrent)

        # 2. Start transferarr
        transferarr.start(wait_healthy=True)

        # 3. Verify torrent appears in all_torrents
        all_url = f"{get_api_url()}/all_torrents"
        resp = requests.get(all_url, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200
        all_data = resp.json()["data"]
        assert "source-deluge" in all_data
        assert torrent["hash"] in all_data["source-deluge"]

        # 4. Initiate manual transfer
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        result = resp.json()
        assert result["data"]["total_initiated"] == 1
        assert result["data"]["total_errors"] == 0
        assert len(result["data"]["initiated"]) == 1
        assert result["data"]["initiated"][0]["hash"] == torrent["hash"]

        # 5. Verify torrent appears in tracked torrents
        torrents = transferarr.get_torrents()
        found = [t for t in torrents if torrent["hash"] in t.get("id", "")]
        assert len(found) == 1, f"Expected torrent in tracked list. Tracked: {torrents}"

        # 6. Wait for torrent to arrive on target Deluge in Seeding state.
        #    Manual transfers have no media_manager, so they pass through
        #    TARGET_SEEDING and are immediately removed from the tracked list.
        #    We verify completion by checking the target client directly.
        wait_for_torrent_in_deluge(
            deluge_target, torrent["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )

        # 7. Verify torrent exists on target Deluge
        target_status = deluge_target.core.get_torrent_status(
            torrent["hash"], ["state", "name"]
        )
        target_state = decode_bytes(target_status.get("state", ""))
        assert target_state == "Seeding", f"Target state: {target_state}"

        # 8. Verify immediate removal from source (media_manager=None skips
        #    torrent_ready_to_remove and removes immediately at TARGET_SEEDING)
        wait_for_torrent_removed(
            deluge_source, torrent["hash"],
            timeout=TIMEOUTS['state_transition'],
        )

        # 9. Verify torrent dropped from tracked list
        torrents = transferarr.get_torrents()
        found = [t for t in torrents if torrent["hash"] in t.get("id", "")]
        assert len(found) == 0, f"Torrent should be removed from tracking. Found: {found}"

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_initiate_multiple_torrents(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Initiate manual transfer for multiple torrents at once."""
        # Create two torrents
        name1 = f"manual_multi_a_{uuid.uuid4().hex[:6]}"
        name2 = f"manual_multi_b_{uuid.uuid4().hex[:6]}"
        t1 = add_torrent_to_deluge(deluge_source, name1, create_torrent)
        t2 = add_torrent_to_deluge(deluge_source, name2, create_torrent)

        # Start transferarr and initiate
        transferarr.start(wait_healthy=True)

        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [t1["hash"], t2["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200
        result = resp.json()
        assert result["data"]["total_initiated"] == 2
        assert result["data"]["total_errors"] == 0

        # Wait for both to arrive on target Deluge
        wait_for_torrent_in_deluge(
            deluge_target, t1["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )
        wait_for_torrent_in_deluge(
            deluge_target, t2["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_rejects_not_seeding_torrent(
        self, transferarr, deluge_source, create_torrent,
    ):
        """A torrent that isn't seeding is rejected."""
        # Create torrent but add it paused so it's not seeding
        unique_name = f"manual_paused_{uuid.uuid4().hex[:6]}"
        torrent_info = create_torrent(unique_name, size_mb=1)
        torrent_hash = torrent_info["hash"]

        # Download .torrent and add as paused
        torrent_filename = f"{unique_name}.torrent"
        resp = requests.get(f"{MOCK_INDEXER_URL}/download/{torrent_filename}")
        assert resp.status_code == 200
        torrent_b64 = base64.b64encode(resp.content).decode("ascii")

        result_hash = deluge_source.core.add_torrent_file(
            f"{unique_name}.torrent",
            torrent_b64,
            {"download_location": "/downloads", "add_paused": True},
        )
        result_hash = decode_bytes(result_hash) if result_hash else ""
        time.sleep(2)

        # Verify it's paused
        status = deluge_source.core.get_torrent_status(result_hash, ["state"])
        state = decode_bytes(status.get("state", ""))
        assert state == "Paused", f"Expected Paused, got {state}"

        # Start transferarr and attempt transfer
        transferarr.start(wait_healthy=True)

        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [result_hash],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400
        assert "seeding" in resp.json().get("error", {}).get("message", "").lower()

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_all_torrents_includes_save_path(
        self, transferarr, deluge_source, create_torrent,
    ):
        """Verify /all_torrents response includes save_path and total_size."""
        unique_name = f"manual_fields_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(deluge_source, unique_name, create_torrent)

        transferarr.start(wait_healthy=True)

        all_url = f"{get_api_url()}/all_torrents"
        resp = requests.get(all_url, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200

        client_data = resp.json()["data"].get("source-deluge", {})
        torrent_data = client_data.get(torrent["hash"])
        assert torrent_data is not None, f"Torrent {torrent['hash']} not in response"

        assert "save_path" in torrent_data, f"Missing save_path. Keys: {torrent_data.keys()}"
        assert "total_size" in torrent_data, f"Missing total_size. Keys: {torrent_data.keys()}"
        assert isinstance(torrent_data["save_path"], str)
        assert torrent_data["total_size"] > 0


# ==============================================================================
# Destinations with torrent transfer config
# ==============================================================================

class TestDestinationsWithTorrentConfig:
    """Tests for destinations endpoint with torrent transfer connections."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment, transferarr):
        """Start transferarr with torrent-transfer config."""
        transferarr.start(config_type='torrent-transfer', wait_healthy=True)

    def test_destinations_show_torrent_transfer_type(self):
        """Destinations for torrent config show transfer_type='torrent'."""
        url = f"{get_api_url()}/transfers/destinations"
        resp = requests.get(
            url, params={"source": "source-deluge"},
            timeout=TIMEOUTS['api_response'],
        )

        assert resp.status_code == 200
        destinations = resp.json()["data"]
        assert len(destinations) >= 1

        # Find the torrent connection
        torrent_dests = [d for d in destinations if d["transfer_type"] == "torrent"]
        assert len(torrent_dests) >= 1, f"No torrent destinations found: {destinations}"


# ==============================================================================
# POST /api/v1/transfers/manual — torrent (P2P) transfer method
# ==============================================================================

class TestManualTransferTorrentWithoutTracker:
    """Tests that manual torrent-type transfers are rejected when tracker is disabled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['api_response'] * 2)
    def test_rejects_torrent_transfer_when_tracker_disabled(
        self, transferarr, deluge_source, create_torrent,
    ):
        """POST /transfers/manual returns 400 when connection is torrent-type but tracker is disabled.

        Uses the torrent-transfer-no-tracker config which has a torrent-type
        connection but tracker.enabled=false.  The upfront validation in
        validate_and_initiate() should reject the request before any torrent
        enters the tracking list.
        """
        unique_name = f"no_tracker_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(deluge_source, unique_name, create_torrent)

        # Start with torrent connection + tracker disabled
        transferarr.start(config_type='torrent-transfer-no-tracker', wait_healthy=True)

        # Attempt manual transfer — should be rejected upfront
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        error_msg = resp.json().get("error", {}).get("message", "")
        assert "tracker" in error_msg.lower(), (
            f"Expected tracker-related error message, got: {error_msg}"
        )

        # Verify no torrent leaked into the tracking list
        torrents_url = f"{get_api_url()}/torrents"
        resp = requests.get(torrents_url, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200
        tracked = resp.json().get("data", [])
        tracked_hashes = {t.get("id", "").lower() for t in tracked}
        assert torrent["hash"].lower() not in tracked_hashes, (
            "Torrent should NOT appear in tracking list after rejected transfer"
        )


class TestManualTorrentTypeTransfer:
    """Tests for manual transfers using the torrent (P2P) transfer method.

    Unlike the SFTP-based tests in TestManualTransferInitiation, these use
    config_type='torrent-transfer' so the connection uses BitTorrent P2P
    via the built-in tracker instead of file copy.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_manual_torrent_transfer_completes(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Manual transfer via torrent method transfers files over P2P.

        Creates a seeding torrent on source, initiates a manual transfer
        with the torrent-transfer config, and verifies the torrent arrives
        on the target client via BitTorrent P2P.
        """
        unique_name = f"manual_torrent_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(deluge_source, unique_name, create_torrent)

        # Start with torrent-transfer config (uses tracker, no SFTP)
        transferarr.start(config_type='torrent-transfer', wait_healthy=True)

        # Verify torrent appears in all_torrents
        all_url = f"{get_api_url()}/all_torrents"
        resp = requests.get(all_url, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200
        assert torrent["hash"] in resp.json()["data"].get("source-deluge", {})

        # Initiate manual transfer
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200, f"Expected 200: {resp.text}"
        result = resp.json()["data"]
        assert result["total_initiated"] == 1
        assert result["total_errors"] == 0
        assert result["initiated"][0]["method"] == "torrent"

        # Wait for torrent to arrive on target via P2P
        wait_for_torrent_in_deluge(
            deluge_target, torrent["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )


# ==============================================================================
# POST /api/v1/transfers/manual — cross-seed expansion
# ==============================================================================

class TestManualTransferCrossSeed:
    """Tests for cross-seed expansion in manual transfers.

    Cross-seeds are torrents sharing the same save_path on a client.
    When include_cross_seeds=True (default), selecting one torrent
    should automatically expand to include its siblings.

    Both torrents are added with download_location=/downloads, giving
    them the same save_path. clean_test_environment ensures no stale
    torrents pollute the grouping.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_cross_seed_expansion_transfers_sibling(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Selecting one torrent with cross-seeds enabled also transfers its sibling.

        Creates two torrents sharing the same save_path (/downloads),
        then initiates a manual transfer for only one hash.
        The API should expand the selection to include the sibling.
        """
        suffix = uuid.uuid4().hex[:6]
        name_a = f"xseed_primary_{suffix}"
        name_b = f"xseed_sibling_{suffix}"

        # 1. Create two seeding torrents — both land in /downloads (same save_path)
        torrent_a = add_torrent_to_deluge(deluge_source, name_a, create_torrent)
        torrent_b = add_torrent_to_deluge(deluge_source, name_b, create_torrent)

        # 2. Start transferarr and verify both appear with matching save_path
        transferarr.start(wait_healthy=True)

        all_url = f"{get_api_url()}/all_torrents"
        resp = requests.get(all_url, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200
        source_data = resp.json()["data"].get("source-deluge", {})
        assert torrent_a["hash"] in source_data, "Torrent A not in source listing"
        assert torrent_b["hash"] in source_data, "Torrent B not in source listing"

        # Verify they share save_path (cross-seed condition)
        path_a = source_data[torrent_a["hash"]]["save_path"]
        path_b = source_data[torrent_b["hash"]]["save_path"]
        assert path_a == path_b, f"save_paths differ: {path_a} vs {path_b}"

        # 3. Initiate manual transfer with ONLY hash A, cross-seeds enabled
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent_a["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200, f"Expected 200: {resp.text}"
        result = resp.json()["data"]

        # Should have initiated 2 transfers (A + sibling B)
        assert result["total_initiated"] == 2, (
            f"Expected 2 initiated (cross-seed expansion), got {result['total_initiated']}. "
            f"Initiated: {result['initiated']}, Errors: {result['errors']}"
        )
        initiated_hashes = {t["hash"] for t in result["initiated"]}
        assert torrent_a["hash"] in initiated_hashes
        assert torrent_b["hash"] in initiated_hashes

        # 4. Wait for BOTH torrents to arrive on target in Seeding state
        wait_for_torrent_in_deluge(
            deluge_target, torrent_a["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )
        wait_for_torrent_in_deluge(
            deluge_target, torrent_b["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_cross_seed_disabled_transfers_only_selected(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """With cross-seeds disabled, only the explicitly selected torrent transfers.

        Same setup as the expansion test, but include_cross_seeds=False.
        Only the selected hash should be initiated.
        """
        suffix = uuid.uuid4().hex[:6]
        name_a = f"xseed_only_a_{suffix}"
        name_b = f"xseed_only_b_{suffix}"

        # Create two torrents sharing save_path
        torrent_a = add_torrent_to_deluge(deluge_source, name_a, create_torrent)
        torrent_b = add_torrent_to_deluge(deluge_source, name_b, create_torrent)

        transferarr.start(wait_healthy=True)

        # Initiate with ONLY hash A and cross-seeds DISABLED
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent_a["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200
        result = resp.json()["data"]

        # Should have initiated only 1 transfer (no expansion)
        assert result["total_initiated"] == 1, (
            f"Expected 1 initiated (no cross-seed expansion), got {result['total_initiated']}"
        )
        assert result["initiated"][0]["hash"] == torrent_a["hash"]

        # Wait for A to arrive on target
        wait_for_torrent_in_deluge(
            deluge_target, torrent_a["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )

        # B should NOT be on target — give a brief window then verify absence
        time.sleep(5)
        target_torrents = deluge_target.core.get_torrents_status({}, ["name"])
        target_torrents = decode_bytes(target_torrents)
        assert torrent_b["hash"] not in target_torrents, (
            f"Sibling torrent B should NOT have been transferred"
        )
