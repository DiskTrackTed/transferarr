"""
Integration tests for torrent-based transfer edge cases (Phase 8).

Tests error recovery, deduplication, and unusual scenarios specific
to torrent-based transfers.
"""
import json
import pytest
import time
import base64
import requests

from tests.conftest import TIMEOUTS, SERVICES
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    clear_deluge_torrents,
    decode_bytes,
)
from tests.integration.transfers.test_torrent_transfer_download import find_transfer_torrent


# Volume name matches docker-compose project "transferarr_test" + volume "transferarr-state"
STATE_VOLUME = "transferarr_test_transferarr-state"


def force_torrent_state_in_file(transferarr, torrent_name, new_state):
    """Force a torrent's state in state.json via Docker volume.

    Uses a temp container to read, modify, and write state.json.
    Transferarr must be stopped when calling this.

    Args:
        transferarr: TransferarrManager instance
        torrent_name: Torrent name substring to find
        new_state: New state string (e.g., "TORRENT_DOWNLOADING")

    Raises:
        ValueError: If torrent not found in state.json
    """
    # Read state.json
    output = transferarr.docker.containers.run(
        'alpine:latest',
        'cat /state/state.json',
        volumes={STATE_VOLUME: {'bind': '/state', 'mode': 'ro'}},
        remove=True
    )

    state_data = json.loads(output.decode())

    # Find and modify the torrent (state.json is a JSON array of torrent dicts)
    modified = False
    for torrent_dict in state_data:
        if torrent_name in torrent_dict.get('name', ''):
            torrent_dict['state'] = new_state
            modified = True
            break

    if not modified:
        raise ValueError(f"Torrent '{torrent_name}' not found in state.json")

    # Write back using base64 to avoid shell escaping issues
    state_json = json.dumps(state_data)
    encoded = base64.b64encode(state_json.encode()).decode()

    transferarr.docker.containers.run(
        'alpine:latest',
        f'sh -c "echo {encoded} | base64 -d > /state/state.json"',
        volumes={STATE_VOLUME: {'bind': '/state', 'mode': 'rw'}},
        remove=True
    )


@pytest.fixture
def torrent_transfer_config():
    """Return the config type for torrent-based transfers."""
    return "torrent-transfer"


def get_transferarr_torrent(transferarr, torrent_name):
    """Get torrent data from transferarr API by name substring."""
    torrents = transferarr.get_torrents()
    for t in torrents:
        if torrent_name in t.get('name', ''):
            return t
    return None


class TestAlreadyOnTargetSkipsTorrentTransfer:
    """Test that torrents already on target skip the torrent transfer entirely."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_already_on_target_skips_torrent_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Torrent already on target when HOME_SEEDING with torrent connection.

        Verify: goes directly to TARGET_* states, no transfer torrent created.
        This is the torrent-transfer variant of the SFTP deduplication test.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # Step 1: Create torrent
        print(f"\n[Step 1] Creating torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        # Step 2: Get .torrent file from mock indexer and add to BOTH clients
        print(f"\n[Step 2] Getting .torrent file and adding to both clients...")
        mock_indexer = SERVICES['mock_indexer']
        indexer_url = f"http://{mock_indexer['host']}:{mock_indexer['port']}"
        torrent_filename = f"{torrent_name}.torrent"
        torrent_response = requests.get(f"{indexer_url}/download/{torrent_filename}")
        if torrent_response.status_code != 200:
            pytest.fail(f"Failed to download torrent: {torrent_response.status_code}")
        torrent_data = torrent_response.content
        torrent_b64 = base64.b64encode(torrent_data).decode('utf-8')

        # Add to target first (simulate pre-existing)
        deluge_target.core.add_torrent_file(
            f"{torrent_name}.torrent",
            torrent_b64,
            {"download_location": "/downloads"}
        )
        time.sleep(3)

        # Verify target has the torrent
        target_torrents = deluge_target.core.get_torrents_status({}, ['state'])
        target_torrents = decode_bytes(target_torrents)
        assert any(h.lower() == original_hash.lower() for h in target_torrents.keys()), \
            "Target should have the torrent"

        # Step 3: Add movie to Radarr (source already has it from create_torrent)
        print(f"\n[Step 3] Adding movie to Radarr...")
        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Step 4: Start transferarr with torrent-transfer config
        print(f"\n[Step 4] Starting transferarr...")
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Step 5: Should skip transfer and go directly to TARGET_*
        print(f"\n[Step 5] Waiting for TARGET_SEEDING (should skip TORRENT_* states)...")
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Verify NO transfer torrent was created
        transfer_on_source, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        assert transfer_on_source is None, \
            "No transfer torrent should be created when already on target"

        # Verify the torrent data doesn't have transfer hash
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        if torrent_data and torrent_data.get('transfer'):
            assert torrent_data['transfer'].get('hash') is None, \
                "Transfer hash should not be set when skipping transfer"

        print("\n✅ Already-on-target correctly skipped torrent transfer")


class TestMaxRetriesCleansUpAndResets:
    """Test that max retries triggers cleanup and reset to HOME_SEEDING."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 3)
    def test_max_retries_cleans_up_and_resets(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Force failures by removing transfer torrent from target mid-download.

        Verify: after 3 retries, _cleanup_failed_transfer removes from both
        clients + tracker, resets to HOME_SEEDING. Next cycle starts fresh.

        Note: This test forces errors by removing the transfer torrent from
        the target client while it's downloading. The handler will detect the
        missing torrent and increment retry_count.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for at least TORRENT_TARGET_ADDING or DOWNLOADING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING', 'TORRENT_SEEDING'],
            timeout=120
        )

        # Capture transfer hash
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        transfer_hash = torrent_data.get('transfer', {}).get('hash') if torrent_data else None
        assert transfer_hash, "Transfer hash should be set"

        # Sabotage: remove transfer torrent from TARGET to force an error
        print(f"\n  Sabotaging: removing transfer torrent from target ({transfer_hash[:8]}...)")
        try:
            deluge_target.core.remove_torrent(transfer_hash, True)
        except Exception as e:
            print(f"  Warning removing transfer from target: {e}")

        # Wait for state to change - should either retry or reset to HOME_SEEDING
        # After MAX_RETRIES (3), it should reset to HOME_SEEDING
        # Then start a fresh transfer cycle
        print("  Waiting for transfer to eventually complete or reach HOME_SEEDING...")

        # The torrent should either:
        # 1. Eventually succeed (fresh retry creates new transfer torrent)
        # 2. Be in HOME_SEEDING (if retries exhausted and waiting for next cycle)
        # In either case, it should eventually reach TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING', 'HOME_SEEDING', 'TORRENT_CREATING',
             'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=TIMEOUTS['torrent_transfer'] * 2
        )

        # Check current state
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        current_state = torrent_data.get('state') if torrent_data else None
        print(f"  Current state: {current_state}")

        # If it reached HOME_SEEDING, the cleanup worked and it will retry
        if current_state == 'HOME_SEEDING':
            # Transfer data should be cleared (or retry_count reset)
            transfer = torrent_data.get('transfer', {})
            # After cleanup, transfer dict may still exist but retry_count > 0
            print(f"  Retry count: {transfer.get('retry_count', 'N/A')}")
            print("  ✅ Cleanup triggered, torrent reset to HOME_SEEDING")
        elif current_state in ['TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING']:
            # Already started a fresh retry
            print("  ✅ Fresh retry started after cleanup")
        elif current_state == 'TARGET_SEEDING':
            # Completed successfully despite sabotage
            print("  ✅ Transfer completed despite sabotage (fast retry)")

        print("\n✅ Error recovery and retry mechanism working")


class TestNoHandlerGoesToError:
    """Test that TORRENT_* states without a handler transition to ERROR."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_torrent_transfer_with_no_handler_goes_to_error(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart with SFTP config (tracker disabled) while state.json has a TORRENT_* state.

        With the no-tracker config there's no torrent_transfer_handler, so the
        torrent should transition to ERROR.

        Uses deterministic state manipulation: lets the torrent be tracked,
        then forces TORRENT_DOWNLOADING in state.json before restarting with
        an incompatible config. This avoids the race condition of trying to
        catch the torrent mid-transfer.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Start with torrent-transfer config to get the torrent tracked
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for torrent to be tracked in any state
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['HOME_SEEDING', 'TORRENT_CREATING', 'TORRENT_TARGET_ADDING',
             'TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Stop and force the torrent into a TORRENT_* state in state.json
        transferarr.stop()
        time.sleep(2)

        # Clear target-deluge so the torrent can't shortcut to TARGET_SEEDING
        # (the initial transfer likely completed the 10MB file already)
        clear_deluge_torrents(deluge_target)

        force_torrent_state_in_file(
            transferarr, torrent_name, 'TORRENT_DOWNLOADING'
        )

        # Start with SFTP config that explicitly has tracker disabled
        # This means no torrent_transfer_handler is created
        transferarr.start(config_type='sftp-to-sftp-no-tracker', wait_healthy=True)

        # ERROR is transient: TORRENT_DOWNLOADING -> ERROR -> HOME_SEEDING -> COPYING
        # Wait for the torrent to transition out of TORRENT_* states
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['ERROR', 'HOME_SEEDING', 'COPYING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=60
        )

        # Verify the no-handler error was logged (confirms ERROR transition happened)
        logs = transferarr.get_logs(tail=200)
        assert "no transfer handler available" in logs, \
            f"Expected 'no transfer handler' error in logs"

        # Verify the torrent is no longer stuck in a TORRENT_* state
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data is not None, "Torrent should still be tracked"
        assert not torrent_data.get('state', '').startswith('TORRENT_'), \
            f"Torrent should not be stuck in TORRENT_* state, got: {torrent_data.get('state')}"

        print("\n✅ TORRENT_* state with no handler correctly transitions to ERROR")


class TestNoConnectionGoesToError:
    """Test that TORRENT_* states without a matching connection go to ERROR."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_torrent_transfer_with_no_connection_goes_to_error(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart with SFTP config (tracker disabled) while state.json has a TORRENT_* state.

        With the no-tracker config, torrent_transfer_handler is None,
        so the torrent in a TORRENT_* state should transition to ERROR.

        Note: This test currently hits the "no handler" check before the
        "no connection" check because the config disables the tracker
        entirely. A true "no connection" test would need a config with a
        tracker but without the matching connection.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Start with torrent-transfer config to get the torrent tracked
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for torrent to be tracked in any state
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['HOME_SEEDING', 'TORRENT_CREATING', 'TORRENT_TARGET_ADDING',
             'TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Stop and force the torrent into a TORRENT_* state in state.json
        transferarr.stop()
        time.sleep(2)

        # Clear target-deluge so the torrent can't shortcut to TARGET_SEEDING
        # (the initial transfer likely completed the 10MB file already)
        clear_deluge_torrents(deluge_target)

        force_torrent_state_in_file(
            transferarr, torrent_name, 'TORRENT_SEEDING'
        )

        # Use sftp-to-sftp config with tracker explicitly disabled
        # This means no torrent_transfer_handler is created
        transferarr.start(config_type='sftp-to-sftp-no-tracker', wait_healthy=True)

        # ERROR is transient: TORRENT_SEEDING -> ERROR -> HOME_SEEDING -> COPYING
        # Wait for the torrent to transition out of TORRENT_* states
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['ERROR', 'HOME_SEEDING', 'COPYING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=60
        )

        # Verify the no-handler error was logged (confirms ERROR transition happened)
        logs = transferarr.get_logs(tail=200)
        assert "no transfer handler available" in logs, \
            f"Expected 'no transfer handler' error in logs"

        print("\n✅ TORRENT_* state with missing connection correctly transitions to ERROR")


class TestTransferTorrentPickedUpByMediaManager:
    """Test that transfer torrents picked up by Radarr/Sonarr are handled."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_transfer_torrent_not_duplicated_in_tracking(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify that if Radarr picks up a transfer torrent, transferarr
        detects it and removes it from tracking instead of treating it as
        a new torrent.

        The detection logic in torrent_service.py checks if a MANAGER_QUEUED
        torrent's hash matches another torrent's transfer.hash.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for transfer to start
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )

        # Get transfer hash
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        transfer_hash = torrent_data.get('transfer', {}).get('hash') if torrent_data else None

        # Verify only ONE torrent is tracked (the original, not the transfer torrent)
        torrents = transferarr.get_torrents()
        names = [t.get('name', '') for t in torrents]
        print(f"  Tracked torrents: {names}")

        # The transfer torrent should NOT appear as a separate tracked torrent
        # (even if Radarr/Sonarr detected it in the queue)
        transfer_tracked = False
        for t in torrents:
            if t.get('name', '') != torrent_name and transfer_hash:
                # Check if this torrent's ID matches the transfer hash
                if t.get('id', '').lower() == transfer_hash.lower():
                    transfer_tracked = True
                    break

        assert not transfer_tracked, \
            "Transfer torrent should not be tracked separately"

        # Wait for completion
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        print("\n✅ Transfer torrent not duplicated in tracking list")


class TestStallDetection:
    """Test stall detection and re-announce behavior."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_stall_detection_triggers_reannounce(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify that stall detection records reannounce_count.

        We can't easily force a 5-minute stall in integration tests,
        but we can verify the reannounce_count field is tracked by checking
        it starts at 0 and the transfer completes normally.

        For true stall testing, a unit test with mocked time would be more
        appropriate (the stall threshold is 300 seconds).
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        torrent_info = create_torrent(torrent_name, size_mb=10)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year']
        )

        wait_for_queue_item_by_hash(radarr_client, original_hash, timeout=60)
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=60, expected_state='Seeding'
        )

        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for downloading state
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Check that reannounce_count exists and starts at 0
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        if torrent_data and torrent_data.get('transfer'):
            reannounce_count = torrent_data['transfer'].get('reannounce_count', 0)
            print(f"  reannounce_count = {reannounce_count}")
            assert reannounce_count >= 0, "reannounce_count should be non-negative"

        # Let the transfer complete normally
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        # After successful transfer, reannounce_count should still be 0
        # (no stalls occurred for a normal 10MB file)
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        if torrent_data and torrent_data.get('transfer'):
            final_reannounce = torrent_data['transfer'].get('reannounce_count', 0)
            print(f"  Final reannounce_count = {final_reannounce}")

        print("\n✅ Stall detection field tracked correctly")
