"""
Integration tests for Manual Transfer API endpoints.

Tests /api/v1/transfers/destinations and /api/v1/transfers/manual
against a running transferarr instance with Docker test services.
"""
import base64
import os
import time
import uuid
from urllib.parse import quote

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


def get_client_torrents_url(client_name: str) -> str:
    """Get the per-client torrents endpoint URL."""
    return f"{get_api_url()}/clients/{quote(client_name, safe='')}/torrents"


MOCK_INDEXER_HOST = os.environ.get("MOCK_INDEXER_HOST", "mock-indexer")
MOCK_INDEXER_PORT = os.environ.get("MOCK_INDEXER_PORT", "9696")
MOCK_INDEXER_URL = f"http://{MOCK_INDEXER_HOST}:{MOCK_INDEXER_PORT}"


def add_torrent_to_deluge(deluge_client, name, create_torrent_fn, size_mb=1,
                          download_location="/downloads"):
    """Create a torrent and add it directly to a Deluge instance.

    Args:
        deluge_client: Deluge RPC client
        name: Torrent name
        create_torrent_fn: Factory function from create_torrent fixture
        size_mb: Size in megabytes
        download_location: Download location path in the container

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
        {"download_location": download_location},
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


def create_cross_seed_torrent(docker_client, deluge_client, content_name,
                              source_location="/downloads",
                              download_location=None):
    """Generate a cross-seed .torrent for existing content on a Deluge client.

    Uses Docker exec to run libtorrent inside the Deluge source container,
    creating a second .torrent from the same content with a different tracker
    URL (producing a different info_hash).

    For different save_path scenarios, copies the content to the new location
    first — simulating what cross-seed tools do with symlinks.

    Args:
        docker_client: Docker SDK client
        deluge_client: Deluge RPC client
        content_name: Name of the content directory (same as original torrent)
        source_location: Where the original content lives (e.g., /downloads)
        download_location: Where to place the cross-seed torrent.
            If None, uses source_location (same save_path).
            If different, copies content to the new location.

    Returns:
        dict with keys: name, hash
    """
    if download_location is None:
        download_location = source_location

    container = docker_client.containers.get("test-deluge-source")

    # If different location, copy content there (simulates symlink from cross-seed tool)
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

    # Generate a second .torrent via libtorrent with a different tracker URL.
    # The different tracker URL produces a different info_hash.
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

    # Add cross-seed .torrent to Deluge
    result_hash = deluge_client.core.add_torrent_file(
        f"xseed_{content_name}.torrent",
        xseed_b64,
        {"download_location": download_location},
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
        status = deluge_client.core.get_torrent_status(
            result_hash, ["state", "progress"]
        )
        pytest.fail(
            f"Cross-seed torrent did not reach Seeding: {decode_bytes(status)}"
        )

    return {"name": content_name, "hash": result_hash}


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

        # 3. Verify torrent appears in the source client's torrent listing
        resp = requests.get(
            get_client_torrents_url("source-deluge"),
            timeout=TIMEOUTS['api_response'],
        )
        assert resp.status_code == 200
        source_data = resp.json()["data"]
        assert torrent["hash"] in source_data

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
    def test_client_torrents_includes_save_path(
        self, transferarr, deluge_source, create_torrent,
    ):
        """Verify per-client torrent response includes save_path and total_size."""
        unique_name = f"manual_fields_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(deluge_source, unique_name, create_torrent)

        transferarr.start(wait_healthy=True)

        resp = requests.get(
            get_client_torrents_url("source-deluge"),
            timeout=TIMEOUTS['api_response'],
        )
        assert resp.status_code == 200

        torrent_data = resp.json()["data"].get(torrent["hash"])
        assert torrent_data is not None, f"Torrent {torrent['hash']} not in response"

        assert "save_path" in torrent_data, f"Missing save_path. Keys: {torrent_data.keys()}"
        assert "total_size" in torrent_data, f"Missing total_size. Keys: {torrent_data.keys()}"
        assert isinstance(torrent_data["save_path"], str)
        assert torrent_data["total_size"] > 0

    @pytest.mark.timeout(TIMEOUTS['api_response'])
    def test_client_torrents_unknown_client_returns_404(self, transferarr):
        """Unknown client returns 404 from the per-client torrents endpoint."""
        transferarr.start(wait_healthy=True)

        resp = requests.get(
            get_client_torrents_url("missing-client"),
            timeout=TIMEOUTS['api_response'],
        )

        assert resp.status_code == 404
        error = resp.json()["error"]
        assert error["code"] == "CLIENT_NOT_FOUND"


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

        # Verify torrent appears in the source client's listing
        resp = requests.get(
            get_client_torrents_url("source-deluge"),
            timeout=TIMEOUTS['api_response'],
        )
        assert resp.status_code == 200
        assert torrent["hash"] in resp.json()["data"]

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

    Cross-seeds are torrents that share the same name and total_size on
    a client.  They may live in the same or different directories (the
    cross-seed tool often creates symlinks in a separate linkdir).

    When include_cross_seeds=True, selecting one torrent
    should automatically expand to include its siblings.

    Each test creates a cross-seed pair: the original torrent plus a
    second .torrent generated from the same content with a different
    tracker URL (producing a different info_hash).
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_cross_seed_expansion_same_save_path(
        self, docker_client, transferarr, deluge_source, deluge_target,
        create_torrent,
    ):
        """Cross-seed expansion when both torrents share the same save_path.

        Creates a torrent and a cross-seed (same name+size, different hash)
        both at /downloads.  Selecting one with cross-seeds enabled should
        expand to include the sibling.
        """
        suffix = uuid.uuid4().hex[:6]
        content_name = f"XSeed.Same.Path.{suffix}"

        # 1. Create original torrent and its cross-seed at the same location
        torrent_a = add_torrent_to_deluge(
            deluge_source, content_name, create_torrent, size_mb=1,
        )
        torrent_b = create_cross_seed_torrent(
            docker_client, deluge_source, content_name,
            source_location="/downloads",
        )

        # 2. Verify both have the same save_path and name in the API
        transferarr.start(wait_healthy=True)

        resp = requests.get(
            get_client_torrents_url("source-deluge"),
            timeout=TIMEOUTS['api_response'],
        )
        assert resp.status_code == 200
        source_data = resp.json()["data"]
        assert torrent_a["hash"] in source_data, "Original not in listing"
        assert torrent_b["hash"] in source_data, "Cross-seed not in listing"

        info_a = source_data[torrent_a["hash"]]
        info_b = source_data[torrent_b["hash"]]
        assert info_a["save_path"] == info_b["save_path"], "save_paths should match"
        assert info_a["name"] == info_b["name"], "names should match"
        assert info_a["total_size"] == info_b["total_size"], "sizes should match"

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

        # Should have initiated 2 transfers (A + cross-seed B)
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
    def test_cross_seed_expansion_different_save_path(
        self, docker_client, transferarr, deluge_source, deluge_target,
        create_torrent,
    ):
        """Cross-seed expansion when torrents have different save_paths.

        Simulates the symlink scenario: original torrent at /downloads,
        cross-seed at /downloads/linkdir (as cross-seed tools typically do).
        Despite different save_paths, both share the same name and total_size
        so the API should expand the selection.
        """
        suffix = uuid.uuid4().hex[:6]
        content_name = f"XSeed.Diff.Path.{suffix}"

        # 1. Create original at /downloads
        torrent_a = add_torrent_to_deluge(
            deluge_source, content_name, create_torrent, size_mb=1,
        )

        # 2. Create cross-seed at /downloads/linkdir (copies content there)
        torrent_b = create_cross_seed_torrent(
            docker_client, deluge_source, content_name,
            source_location="/downloads",
            download_location="/downloads/linkdir",
        )

        # 3. Verify they have DIFFERENT save_paths but same name+size
        transferarr.start(wait_healthy=True)

        resp = requests.get(
            get_client_torrents_url("source-deluge"),
            timeout=TIMEOUTS['api_response'],
        )
        assert resp.status_code == 200
        source_data = resp.json()["data"]
        assert torrent_a["hash"] in source_data, "Original not in listing"
        assert torrent_b["hash"] in source_data, "Cross-seed not in listing"

        info_a = source_data[torrent_a["hash"]]
        info_b = source_data[torrent_b["hash"]]
        assert info_a["save_path"] != info_b["save_path"], (
            f"save_paths should differ: {info_a['save_path']} vs {info_b['save_path']}"
        )
        assert info_a["name"] == info_b["name"], "names should match"
        assert info_a["total_size"] == info_b["total_size"], "sizes should match"

        # 4. Initiate manual transfer with ONLY hash A, cross-seeds enabled
        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent_a["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": True,
        }, timeout=TIMEOUTS['api_response'])

        assert resp.status_code == 200, f"Expected 200: {resp.text}"
        result = resp.json()["data"]

        # Should have initiated 2 transfers — different save_path doesn't matter
        assert result["total_initiated"] == 2, (
            f"Expected 2 initiated (cross-seed expansion across dirs), "
            f"got {result['total_initiated']}. "
            f"Initiated: {result['initiated']}, Errors: {result['errors']}"
        )
        initiated_hashes = {t["hash"] for t in result["initiated"]}
        assert torrent_a["hash"] in initiated_hashes
        assert torrent_b["hash"] in initiated_hashes

        # 5. Wait for BOTH torrents to arrive on target
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
        self, docker_client, transferarr, deluge_source, deluge_target,
        create_torrent,
    ):
        """With cross-seeds disabled, only the explicitly selected torrent transfers.

        Creates a cross-seed pair (same name+size), but requests the transfer
        with include_cross_seeds=False.  Only the selected hash should move.
        """
        suffix = uuid.uuid4().hex[:6]
        content_name = f"XSeed.Disabled.{suffix}"

        # Create original + cross-seed
        torrent_a = add_torrent_to_deluge(
            deluge_source, content_name, create_torrent, size_mb=1,
        )
        torrent_b = create_cross_seed_torrent(
            docker_client, deluge_source, content_name,
            source_location="/downloads",
        )

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
            f"Cross-seed sibling should NOT have been transferred"
        )
