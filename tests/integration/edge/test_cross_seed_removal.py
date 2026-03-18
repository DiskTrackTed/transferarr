"""
Integration tests for cross-seed sibling removal during transfers.

Tests that cross-seed siblings are (or are not) removed from the source
client when the transferred torrent reaches TARGET_SEEDING and is cleaned up.

Two scenarios:
1. Manual transfer with delete_source_cross_seeds=True (default) — sibling IS removed
2. Automatic transfer with client delete_cross_seeds=False — sibling is NOT removed
"""
import base64
import time
import uuid

import pytest
import requests

from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import (
    decode_bytes,
    movie_catalog,
    make_torrent_name,
    remove_from_queue_by_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
    wait_for_transferarr_state,
)


# ==============================================================================
# Helpers
# ==============================================================================

MOCK_INDEXER_HOST = SERVICES['mock_indexer']['host']
MOCK_INDEXER_PORT = SERVICES['mock_indexer']['port']
MOCK_INDEXER_URL = f"http://{MOCK_INDEXER_HOST}:{MOCK_INDEXER_PORT}"

TRANSFERARR_HOST = SERVICES['transferarr']['host']
TRANSFERARR_PORT = SERVICES['transferarr']['port']
API_URL = f"http://{TRANSFERARR_HOST}:{TRANSFERARR_PORT}/api/v1"


def add_torrent_to_deluge(deluge_client, name, create_torrent_fn, size_mb=1,
                          download_location="/downloads"):
    """Create a torrent and add it directly to a Deluge instance.

    Returns:
        dict with keys: name, hash, size_mb
    """
    create_torrent_fn(name, size_mb=size_mb)

    resp = requests.get(
        f"{MOCK_INDEXER_URL}/download/{name}.torrent", timeout=10,
    )
    assert resp.status_code == 200, f"Failed to download .torrent: {resp.status_code}"
    torrent_b64 = base64.b64encode(resp.content).decode("ascii")

    result_hash = deluge_client.core.add_torrent_file(
        f"{name}.torrent",
        torrent_b64,
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
        status = deluge_client.core.get_torrent_status(result_hash, ["state"])
        pytest.fail(
            f"Torrent '{name}' did not reach Seeding. "
            f"State: {decode_bytes(status.get('state', ''))}"
        )

    return {"name": name, "hash": result_hash, "size_mb": size_mb}


def create_cross_seed_torrent(docker_client, deluge_client, content_name,
                              source_location="/downloads",
                              download_location=None):
    """Generate a cross-seed .torrent for existing content on a Deluge client.

    Uses Docker exec to run libtorrent inside the Deluge source container,
    creating a second .torrent from the same content with a different tracker
    URL (producing a different info_hash).

    Returns:
        dict with keys: name, hash
    """
    if download_location is None:
        download_location = source_location

    container = docker_client.containers.get("test-deluge-source")

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

    assert xseed_hash, f"Failed to parse cross-seed hash: {output_str}"
    assert xseed_b64, f"Failed to parse cross-seed base64: {output_str}"

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
        pytest.fail(
            f"Cross-seed did not reach Seeding: {decode_bytes(status)}"
        )

    return {"name": content_name, "hash": result_hash}


def torrent_exists_on_deluge(deluge_client, torrent_hash):
    """Check whether a torrent exists on a Deluge instance."""
    try:
        torrents = deluge_client.core.get_torrents_status({}, ["name"])
        torrents = decode_bytes(torrents)
        return torrent_hash in torrents
    except Exception:
        return False


def update_client_delete_cross_seeds(client_name, value):
    """Update a download client's delete_cross_seeds setting via the API.

    Fetches the client config, patches delete_cross_seeds, and PUTs it back.
    """
    # GET current config
    resp = requests.get(
        f"{API_URL}/download_clients", timeout=TIMEOUTS['api_response'],
    )
    assert resp.status_code == 200, f"GET clients failed: {resp.text}"
    clients = resp.json()["data"]
    assert client_name in clients, (
        f"Client '{client_name}' not found in {list(clients.keys())}"
    )
    client = clients[client_name]

    # PUT with updated setting (password masked in GET, omit to keep existing)
    resp = requests.put(
        f"{API_URL}/download_clients/{client_name}",
        json={
            "type": client["type"],
            "host": client["host"],
            "port": client["port"],
            "connection_type": client["connection_type"],
            "username": client.get("username", ""),
            "delete_cross_seeds": value,
        },
        timeout=TIMEOUTS['api_response'],
    )
    assert resp.status_code == 200, (
        f"PUT client failed ({resp.status_code}): {resp.text}"
    )


# ==============================================================================
# Tests
# ==============================================================================

class TestManualTransferRemovesCrossSeeds:
    """Manual transfer with delete_source_cross_seeds=True (default).

    When a manual transfer completes (TARGET_SEEDING → immediate removal
    because media_manager is None), the original torrent AND its cross-seed
    siblings should all be removed from the source client.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_manual_transfer_removes_cross_seed_sibling(
        self, docker_client, transferarr, deluge_source, deluge_target,
        create_torrent,
    ):
        """A manual transfer with default settings removes cross-seed siblings.

        Steps:
        1. Create a torrent + cross-seed sibling on source
        2. Start transferarr, initiate manual transfer for original only
        3. Wait for the transfer to complete (torrent on target, removed from source)
        4. Verify the cross-seed sibling was ALSO removed from source
        """
        suffix = uuid.uuid4().hex[:6]
        content_name = f"XSeed.Manual.Remove.{suffix}"

        # 1. Create original + cross-seed on source
        print(f"\n[Step 1] Creating torrent and cross-seed: {content_name}")
        original = add_torrent_to_deluge(
            deluge_source, content_name, create_torrent, size_mb=1,
        )
        sibling = create_cross_seed_torrent(
            docker_client, deluge_source, content_name,
        )
        print(f"  Original hash: {original['hash'][:12]}")
        print(f"  Sibling hash:  {sibling['hash'][:12]}")

        # Verify both exist on source
        assert torrent_exists_on_deluge(deluge_source, original["hash"])
        assert torrent_exists_on_deluge(deluge_source, sibling["hash"])

        # 2. Start transferarr
        print("\n[Step 2] Starting transferarr...")
        transferarr.start(wait_healthy=True)

        # 3. Initiate manual transfer (default: delete_source_cross_seeds=True)
        print("\n[Step 3] Initiating manual transfer for original only...")
        resp = requests.post(f"{API_URL}/transfers/manual", json={
            "hashes": [original["hash"]],
            "source_client": "source-deluge",
            "destination_client": "target-deluge",
            "include_cross_seeds": False,
        }, timeout=TIMEOUTS['api_response'])
        assert resp.status_code == 200, f"Manual transfer failed: {resp.text}"
        result = resp.json()["data"]
        assert result["total_initiated"] == 1

        # 4. Wait for torrent to arrive on target (Seeding)
        print("\n[Step 4] Waiting for torrent on target...")
        wait_for_torrent_in_deluge(
            deluge_target, original["hash"],
            timeout=TIMEOUTS['torrent_transfer'],
            expected_state="Seeding",
        )

        # 5. Wait for original to be removed from source
        print("\n[Step 5] Waiting for original removal from source...")
        wait_for_torrent_removed(
            deluge_source, original["hash"],
            timeout=TIMEOUTS['state_transition'],
        )

        # 6. Verify cross-seed sibling was ALSO removed
        print("\n[Step 6] Verifying cross-seed sibling was removed...")
        wait_for_torrent_removed(
            deluge_source, sibling["hash"],
            timeout=30,  # Should already be gone by now
        )

        assert not torrent_exists_on_deluge(deluge_source, sibling["hash"]), \
            "Cross-seed sibling should have been removed from source"
        print("\n✅ Cross-seed sibling was removed from source (default behavior)")


class TestAutomaticTransferPreservesCrossSeeds:
    """Automatic (Radarr) transfer with client delete_cross_seeds=False.

    When a Radarr-driven transfer completes and the client config has
    delete_cross_seeds=False, only the original torrent should be removed.
    The cross-seed sibling must remain on the source.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_automatic_transfer_preserves_sibling_when_disabled(
        self, docker_client, create_torrent, radarr_client, deluge_source,
        deluge_target, transferarr,
    ):
        """With delete_cross_seeds=False on source-deluge, siblings survive.

        Steps:
        1. Create a torrent, add to Radarr + source Deluge
        2. Create a cross-seed sibling on source
        3. Start transferarr, set delete_cross_seeds=False on source client
        4. Wait for transfer to complete
        5. Trigger removal (remove from Radarr queue)
        6. Verify original removed, sibling preserved
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # 1. Create torrent
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info["hash"]

        # 2. Add movie to Radarr and wait for queue
        print(f"\n[Step 2] Adding movie to Radarr: {movie['title']}")
        added_movie = radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )
        wait_for_queue_item_by_hash(
            radarr_client, original_hash, timeout=60,
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state="Seeding",
        )

        # 3. Create cross-seed sibling on source
        print(f"\n[Step 3] Creating cross-seed sibling...")
        sibling = create_cross_seed_torrent(
            docker_client, deluge_source, torrent_name,
        )
        print(f"  Original hash: {original_hash[:12]}")
        print(f"  Sibling hash:  {sibling['hash'][:12]}")
        assert torrent_exists_on_deluge(deluge_source, sibling["hash"])

        # 4. Start transferarr and disable cross-seed deletion on source
        print("\n[Step 4] Starting transferarr and disabling cross-seed deletion...")
        transferarr.start(wait_healthy=True)
        update_client_delete_cross_seeds("source-deluge", False)

        # 5. Wait for TARGET_SEEDING
        print(f"\n[Step 5] Waiting for TARGET_SEEDING...")
        wait_for_transferarr_state(
            transferarr, torrent_name, "TARGET_SEEDING",
            timeout=TIMEOUTS['torrent_transfer'],
        )

        # 6. Verify torrent is on target
        print("\n[Step 6] Verifying torrent on target...")
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state="Seeding",
        )

        # 7. Trigger removal: remove from Radarr queue so transferarr cleans up
        print("\n[Step 7] Removing from Radarr queue to trigger cleanup...")
        removed = remove_from_queue_by_name(radarr_client, torrent_name)
        assert removed, f"Could not find/remove queue item for {torrent_name}"

        # 8. Wait for original to be removed from source
        print("\n[Step 8] Waiting for original removal from source...")
        wait_for_torrent_removed(
            deluge_source, original_hash,
            timeout=TIMEOUTS['state_transition'],
        )

        # 9. Verify cross-seed sibling still EXISTS on source
        print("\n[Step 9] Verifying sibling is preserved...")
        # Give a few extra seconds — if removal was going to happen it would
        # have happened together with the original.
        time.sleep(5)
        assert torrent_exists_on_deluge(deluge_source, sibling["hash"]), \
            "Cross-seed sibling should NOT have been removed (delete_cross_seeds=False)"
        print("\n✅ Cross-seed sibling preserved on source (delete_cross_seeds=False)")
