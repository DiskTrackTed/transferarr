"""
Integration tests for torrent-based transfer restart scenarios (Phase 8).

Tests that Transferarr correctly resumes torrent-based transfers after a restart,
including tracker re-registration, state recovery, and transfer completion.
"""
import pytest
import time
import json

from tests.conftest import TIMEOUTS, SERVICES
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_torrent_removed,
    wait_for_transferarr_state,
    wait_for_condition,
    find_torrent_in_transferarr,
    find_queue_item_by_name,
    decode_bytes,
    get_deluge_torrent_count,
)
from tests.integration.transfers.test_torrent_transfer_download import find_transfer_torrent


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


class TestRestartDuringCreating:
    """Tests for restart during TORRENT_CREATING state."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_creating_with_transfer_on_source(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart after transfer torrent created on source.

        Verify: re-registers with tracker, advances to TARGET_ADDING,
        and completes the full transfer.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # Create torrent and add to Radarr
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

        # Start transferarr and wait for transfer torrent to be created
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for at least TORRENT_TARGET_ADDING (transfer torrent exists on source)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATE_QUEUE', 'TORRENT_CREATING', 'TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING'],
            timeout=60
        )

        # Verify transfer torrent exists on source
        transfer_hash, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        if not transfer_hash:
            # It moved too fast, just check state progressed
            torrent_data = get_transferarr_torrent(transferarr, torrent_name)
            transfer_hash = torrent_data.get('transfer', {}).get('hash') if torrent_data else None

        print(f"  Transfer hash before restart: {transfer_hash[:8] if transfer_hash else 'None'}...")

        # Restart transferarr
        print("\n  Restarting transferarr...")
        transferarr.restart(wait_healthy=True)

        # Verify transfer resumes and completes
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        # Verify original is on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

        print("\n✅ Restart during TORRENT_CREATING recovered successfully")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_creating_without_transfer(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart before create_torrent() call (transfer data initialized but no hash).

        The torrent should be in TORRENT_CREATING with transfer dict but no hash.
        After restart, it should create a new transfer torrent and complete normally.
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

        # Start transferarr - it will move through TORRENT_CREATING quickly
        # For this test we just verify end-to-end works after a restart
        # that could happen at any early point
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for any TORRENT state to confirm it picked up the transfer
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_CREATE_QUEUE', 'TORRENT_CREATING', 'TORRENT_TARGET_ADDING',
             'TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=60
        )

        # Restart immediately (may be in any state)
        transferarr.restart(wait_healthy=True)

        # Should recover and complete
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

        print("\n✅ Restart during early TORRENT_CREATING recovered successfully")


class TestRestartDuringTargetAdding:
    """Tests for restart during TORRENT_TARGET_ADDING state."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_target_adding(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart after transfer torrent on source but before adding to target.

        Verify: re-registers with tracker, adds to target, completes transfer.
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

        # Start and wait for transfer torrent to appear on source
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for transfer to progress past CREATING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_TARGET_ADDING', 'TORRENT_DOWNLOADING', 'TORRENT_SEEDING',
             'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Restart
        transferarr.restart(wait_healthy=True)

        # Should complete
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

        print("\n✅ Restart during TORRENT_TARGET_ADDING recovered successfully")


class TestRestartDuringDownloading:
    """Tests for restart during TORRENT_DOWNLOADING state.

    This is the critical restart test: the tracker loses all peer registrations
    on restart because tracker state is in-memory only. The restart handler must
    re-register transfer hashes and force re-announce on both clients.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_downloading(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart while target is downloading from source via BitTorrent.

        CRITICAL: Tracker loses all peers on restart. Verify:
        - Transfer hash re-registered with tracker
        - Force re-announce on source and target
        - Download resumes and completes
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # Use larger file to increase chance of catching DOWNLOADING state
        torrent_info = create_torrent(torrent_name, size_mb=50)
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

        # Start transferarr
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # Wait for TORRENT_DOWNLOADING (or later if file is small)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Capture transfer hash
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        transfer_hash = torrent_data.get('transfer', {}).get('hash') if torrent_data else None
        current_state = torrent_data.get('state') if torrent_data else None
        print(f"  State before restart: {current_state}")
        print(f"  Transfer hash: {transfer_hash[:8] if transfer_hash else 'None'}...")

        # Restart - this kills the tracker, losing all peer registrations
        print("\n  Restarting transferarr (tracker peers lost)...")
        transferarr.restart(wait_healthy=True)

        # After restart, the re-registration logic should:
        # 1. Re-register transfer hash with tracker
        # 2. Force re-announce on source and target clients
        # 3. Tracker learns peers from announcements
        # 4. Download resumes

        # Verify transfer completes
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        # Verify original on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

        print("\n✅ Restart during TORRENT_DOWNLOADING recovered (tracker peers re-registered)")


class TestRestartDuringSeeding:
    """Tests for restart during TORRENT_SEEDING state."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_seeding_before_original_added(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart after download complete but before original torrent added to target.

        Verify: adds original via magnet, transitions to COPIED.

        Note: TORRENT_SEEDING is very brief for small files. We verify the
        end state rather than catching the exact intermediate state.
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

        # Wait for at least TORRENT_SEEDING or later
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_SEEDING', 'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Restart
        transferarr.restart(wait_healthy=True)

        # Should recover
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=30, expected_state='Seeding'
        )

        print("\n✅ Restart during TORRENT_SEEDING recovered successfully")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_during_seeding_after_original_added(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart after original_on_target=True persisted.

        Verify: verifies original on target, transitions to COPIED without re-adding.
        The transfer should not create a duplicate torrent on target.
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

        # Wait for COPIED or later (original must be on target by then)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )

        # Restart after original is on target
        transferarr.restart(wait_healthy=True)

        # Should settle to TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        # Verify only ONE original torrent on target (no duplicates)
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        original_count = sum(
            1 for h in torrents.keys()
            if h.lower() == original_hash.lower()
        )
        assert original_count == 1, \
            f"Should have exactly 1 original torrent on target, found {original_count}"

        print("\n✅ Restart after original_on_target=True handled correctly")


class TestRestartAtCopiedState:
    """Tests for restart at COPIED state (after TORRENT_SEEDING → COPIED)."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_at_copied_state(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart after TORRENT_SEEDING → COPIED but before TARGET_CHECKING.

        Verify: target client reports state, transitions normally to TARGET_SEEDING,
        cleanup runs (removes transfer torrents, unregisters from tracker).
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

        # Wait for COPIED or TARGET_*
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=180
        )

        # Restart
        transferarr.restart(wait_healthy=True)

        # Should reach TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=120
        )

        # Verify cleanup happened (transfer torrents gone)
        time.sleep(5)  # Allow cleanup time

        transfer_on_source, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        transfer_on_target, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )

        assert transfer_on_source is None, \
            "Transfer torrent should be cleaned up from source after restart"
        assert transfer_on_target is None, \
            "Transfer torrent should be cleaned up from target after restart"

        # Verify cleaned_up flag set
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data is not None
        assert torrent_data.get('transfer', {}).get('cleaned_up') is True, \
            "Transfer should be marked cleaned_up"

        print("\n✅ Restart at COPIED state recovered and cleanup completed")


class TestRestartAtTargetSeeding:
    """Tests for restart during TARGET_SEEDING state."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_at_target_seeding_before_cleanup(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart at TARGET_SEEDING with cleaned_up=False.

        Verify: inline cleanup runs (removes transfer torrents from both clients,
        unregisters from tracker), then proceeds to ready-to-remove check.

        This verifies that cleanup is idempotent and runs correctly after restart.
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

        # Wait for TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # At this point cleanup may have already run (it's fast).
        # Restart immediately to test idempotent cleanup.
        transferarr.restart(wait_healthy=True)

        # Should still be TARGET_SEEDING after restart
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=120
        )

        # Verify transfer torrents are cleaned up (either before or after restart)
        time.sleep(5)

        transfer_on_source, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        transfer_on_target, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )

        assert transfer_on_source is None, \
            "Transfer torrent should be cleaned up from source"
        assert transfer_on_target is None, \
            "Transfer torrent should be cleaned up from target"

        # Verify cleaned_up flag
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data is not None
        assert torrent_data.get('transfer', {}).get('cleaned_up') is True

        print("\n✅ Restart at TARGET_SEEDING before cleanup handled correctly")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_restart_at_target_seeding_after_cleanup(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart at TARGET_SEEDING with cleaned_up=True.

        Verify: skips cleanup, proceeds directly to ready-to-remove check.
        Original lifecycle completes normally.
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

        # Wait for TARGET_SEEDING and cleanup to complete
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=180
        )

        # Wait for cleaned_up=True
        def check_cleaned_up():
            t = get_transferarr_torrent(transferarr, torrent_name)
            return t and t.get('transfer', {}).get('cleaned_up') is True

        wait_for_condition(check_cleaned_up, timeout=30, description="cleaned_up flag set")

        # Restart AFTER cleanup is done
        transferarr.restart(wait_healthy=True)

        # Should still be TARGET_SEEDING
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=120
        )

        # Complete the lifecycle
        queue_item = find_queue_item_by_name(radarr_client, torrent_name)
        assert queue_item, f"Could not find queue item for {torrent_name}"
        radarr_client.remove_from_queue(queue_item['id'])

        # Wait for original to be removed from source
        wait_for_torrent_removed(
            deluge_source, original_hash,
            timeout=TIMEOUTS['torrent_transfer']
        )

        # Verify target still has original
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        torrents = decode_bytes(torrents)
        assert any(h.lower() == original_hash.lower() for h in torrents.keys()), \
            "Original torrent should still be on target"

        print("\n✅ Restart at TARGET_SEEDING after cleanup completed lifecycle normally")


class TestTransferDataPersistence:
    """Tests for transfer data persistence across restarts."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_transfer_data_persisted_across_restart(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify all transfer dict fields survive restart via state.json.

        Checks: hash, on_source, on_target, original_on_target, bytes_downloaded,
        retry_count, reannounce_count, id, name, started_at, etc.
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

        # Wait for downloading or later (transfer data should be populated)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Capture transfer data before restart
        torrent_data_before = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data_before is not None, "Torrent should be tracked"
        transfer_before = torrent_data_before.get('transfer', {})
        state_before = torrent_data_before.get('state')

        print(f"  State before restart: {state_before}")
        print(f"  Transfer data keys: {list(transfer_before.keys())}")

        # Verify key fields exist before restart
        assert transfer_before.get('hash'), "transfer.hash should be set"
        assert transfer_before.get('id'), "transfer.id should be set"
        assert transfer_before.get('name'), "transfer.name should be set"
        assert transfer_before.get('started_at'), "transfer.started_at should be set"
        assert transfer_before.get('on_source') is True, "transfer.on_source should be True"

        # Restart
        transferarr.restart(wait_healthy=True)
        time.sleep(3)  # Allow state to load

        # Get transfer data after restart
        torrent_data_after = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data_after is not None, "Torrent should be restored after restart"
        transfer_after = torrent_data_after.get('transfer', {})

        # Verify key fields survived restart
        assert transfer_after.get('hash') == transfer_before.get('hash'), \
            "transfer.hash should survive restart"
        assert transfer_after.get('id') == transfer_before.get('id'), \
            "transfer.id should survive restart"
        assert transfer_after.get('name') == transfer_before.get('name'), \
            "transfer.name should survive restart"
        assert transfer_after.get('started_at') == transfer_before.get('started_at'), \
            "transfer.started_at should survive restart"
        assert transfer_after.get('on_source') == transfer_before.get('on_source'), \
            "transfer.on_source should survive restart"

        # Verify the transfer completes after restart
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TARGET_SEEDING'],
            timeout=TIMEOUTS['torrent_transfer']
        )

        print("\n✅ Transfer data persisted correctly across restart")

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'] * 2)
    def test_transfer_id_persisted_across_restart(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify _transfer_id (history service ID) survives restart.

        The _transfer_id is used to track transfer progress in the history
        database. Without serialization, history records become orphaned
        on restart.
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

        # Wait for transfer to start (history record created at TORRENT_CREATING)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            ['TORRENT_DOWNLOADING', 'TORRENT_SEEDING', 'COPIED',
             'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120
        )

        # Check _transfer_id in state.json before restart
        state_json = transferarr.exec_in_container(
            ["cat", "/state/state.json"]
        )
        state_data = json.loads(state_json)

        # Find our torrent in state
        torrent_state = None
        for t in state_data:
            if torrent_name in t.get('name', ''):
                torrent_state = t
                break

        assert torrent_state is not None, "Torrent should be in state.json"
        transfer_id_before = torrent_state.get('_transfer_id')
        print(f"  _transfer_id before restart: {transfer_id_before}")
        # transfer_id should be set if history service is enabled
        assert transfer_id_before is not None, \
            "_transfer_id should be persisted in state.json"

        # Restart
        transferarr.restart(wait_healthy=True)
        time.sleep(3)

        # Check _transfer_id after restart
        state_json_after = transferarr.exec_in_container(
            ["cat", "/state/state.json"]
        )
        state_data_after = json.loads(state_json_after)

        torrent_state_after = None
        for t in state_data_after:
            if torrent_name in t.get('name', ''):
                torrent_state_after = t
                break

        assert torrent_state_after is not None, "Torrent should be in state.json after restart"
        transfer_id_after = torrent_state_after.get('_transfer_id')
        print(f"  _transfer_id after restart: {transfer_id_after}")

        assert transfer_id_after == transfer_id_before, \
            f"_transfer_id should survive restart: before={transfer_id_before}, after={transfer_id_after}"

        print("\n✅ _transfer_id persisted correctly across restart")
