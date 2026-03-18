"""
Integration tests for manual transfer state persistence across restarts.

Verifies that manually-initiated transfers (media_manager=None) correctly
save to state.json, restore on restart, and complete the full lifecycle
including immediate removal from source (no Radarr/Sonarr confirmation needed).
"""
import base64
import time
import uuid

import pytest
import requests

from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import (
    decode_bytes,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
    wait_for_transferarr_state,
)


def get_api_url():
    """Get the base API URL for transferarr."""
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


MOCK_INDEXER_URL = "http://mock-indexer:9696"


def add_torrent_to_deluge(deluge_client, name, create_torrent_fn, size_mb=1):
    """Create a torrent and add it directly to a Deluge instance.

    Returns:
        dict with keys: name, hash, size_mb
    """
    torrent_info = create_torrent_fn(name, size_mb=size_mb)
    torrent_hash = torrent_info["hash"]

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

    deadline = time.time() + 30
    while time.time() < deadline:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        state = decode_bytes(status.get("state", ""))
        if state == "Seeding":
            break
        time.sleep(1)
    else:
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        final_state = decode_bytes(status.get("state", ""))
        pytest.fail(f"Torrent '{name}' did not reach Seeding. State: {final_state}")

    return {"name": name, "hash": result_hash, "size_mb": size_mb}


class TestManualTransferRestart:
    """Test that manual transfers persist across restarts and complete."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_manual_sftp_transfer_survives_restart(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Manual SFTP transfer resumes after restart and completes.

        Uses a 100MB file so the COPYING state lasts long enough to
        restart mid-transfer. After restart, the transfer should resume
        from state.json (with media_manager=None) and complete:
        - Torrent arrives on target seeding
        - Torrent removed from source (immediate-removal, no media manager)
        - Torrent dropped from tracking list
        """
        unique_name = f"manual_restart_sftp_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(
            deluge_source, unique_name, create_torrent, size_mb=100,
        )
        print(f"\n[Step 1] Created 100MB torrent: {unique_name} ({torrent['hash'][:8]}...)")

        # Start transferarr and initiate manual transfer
        transferarr.start(wait_healthy=True)

        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200, f"Initiate failed: {resp.text}"
        assert resp.json()["data"]["total_initiated"] == 1
        print("[Step 2] Manual transfer initiated")

        # Wait for COPYING state (100MB over SFTP should take a few seconds)
        wait_for_transferarr_state(
            transferarr, unique_name,
            ['COPYING', 'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=60,
        )
        print("[Step 3] Torrent is in active transfer state")

        # Restart transferarr
        transferarr.restart(wait_healthy=True)
        print("[Step 4] Transferarr restarted")

        # Verify transfer resumes and completes on target
        wait_for_torrent_in_deluge(
            deluge_target, torrent["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )
        print("[Step 5] Torrent arrived on target seeding")

        # Verify immediate removal from source (media_manager=None path)
        wait_for_torrent_removed(
            deluge_source, torrent["hash"],
            timeout=TIMEOUTS['state_transition'],
        )
        print("[Step 6] Torrent removed from source")

        # Verify dropped from tracking list
        torrents = transferarr.get_torrents()
        found = [t for t in torrents if torrent["hash"] in t.get("id", "")]
        assert len(found) == 0, f"Torrent should be removed from tracking: {found}"
        print("[Step 7] Torrent removed from tracking list")

        print("\n✅ Manual SFTP transfer survived restart and completed")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_manual_torrent_transfer_survives_restart(
        self, transferarr, deluge_source, deluge_target, create_torrent,
    ):
        """Manual torrent (P2P) transfer resumes after restart and completes.

        Uses the torrent-transfer config. The P2P transfer goes through
        multiple states (TORRENT_CREATING → TORRENT_TARGET_ADDING →
        TORRENT_DOWNLOADING → ...) which the tracker re-registration on
        restart must handle correctly.
        """
        unique_name = f"manual_restart_torrent_{uuid.uuid4().hex[:6]}"
        torrent = add_torrent_to_deluge(
            deluge_source, unique_name, create_torrent, size_mb=10,
        )
        print(f"\n[Step 1] Created 10MB torrent: {unique_name} ({torrent['hash'][:8]}...)")

        # Start with torrent-transfer config
        transferarr.start(config_type='torrent-transfer', wait_healthy=True)

        url = f"{get_api_url()}/transfers/manual"
        resp = requests.post(url, json={
            "hashes": [torrent["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200, f"Initiate failed: {resp.text}"
        assert resp.json()["data"]["total_initiated"] == 1
        print("[Step 2] Manual torrent transfer initiated")

        # Wait for any TORRENT_* state (confirms transfer is in progress)
        wait_for_transferarr_state(
            transferarr, unique_name,
            ['TORRENT_CREATE_QUEUE', 'TORRENT_CREATING', 'TORRENT_TARGET_ADDING',
             'TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=60,
        )
        print("[Step 3] Torrent is in active transfer state")

        # Restart transferarr (tracker state is in-memory, lost on restart)
        transferarr.restart(wait_healthy=True)
        print("[Step 4] Transferarr restarted")

        # Verify transfer resumes and completes
        wait_for_torrent_in_deluge(
            deluge_target, torrent["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state='Seeding',
        )
        print("[Step 5] Torrent arrived on target seeding")

        # Verify immediate removal from source
        wait_for_torrent_removed(
            deluge_source, torrent["hash"],
            timeout=TIMEOUTS['state_transition'],
        )
        print("[Step 6] Torrent removed from source")

        # Verify dropped from tracking list
        torrents = transferarr.get_torrents()
        found = [t for t in torrents if torrent["hash"] in t.get("id", "")]
        assert len(found) == 0, f"Torrent should be removed from tracking: {found}"
        print("[Step 7] Torrent removed from tracking list")

        print("\n✅ Manual torrent transfer survived restart and completed")
