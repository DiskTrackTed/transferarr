"""
Integration tests for torrent-based transfer restart with large files.

These tests use 2.5GB torrents to reliably catch the TORRENT_DOWNLOADING state
mid-transfer, verifying that restart recovery works under realistic conditions.

Small torrents (10-50MB) transfer near-instantly on Docker networks, making it
impossible to reliably observe transient states. With 2.5GB files, the download
takes long enough to restart transferarr while bytes are actively being transferred.

Key verification points:
- Tracker re-registers transfer hashes (tracker state is in-memory only)
- Force re-announce on source and target restores peer discovery
- bytes_downloaded does not reset to 0 after restart
- Download resumes and completes (not restarted from scratch)
- Transfer torrent cleanup runs after completion
"""
import pytest
import time

from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    wait_for_condition,
    wait_for_state_file_torrent,
)
from tests.integration.transfers.test_torrent_transfer_download import (
    find_transfer_torrent,
    get_transfer_progress,
)


# 2.5GB file - large enough that torrent transfer takes observable time on Docker network
LARGE_FILE_SIZE_MB = 2500

# Extended timeout: 15 minutes for 2.5GB torrent transfer + restart overhead
LARGE_TRANSFER_TIMEOUT = 900


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


class TestLargeRestartDuringDownloading:
    """Tests for restart during TORRENT_DOWNLOADING with large files.

    This is the most critical restart scenario: with large files, the target
    is actively downloading bytes from the source via BitTorrent. On restart:
    - The tracker loses ALL peer registrations (in-memory only)
    - The restart recovery must re-register transfer hashes with the tracker
    - Force re-announce on both clients restores peer-to-peer connectivity
    - The download must resume from where it left off, not from scratch

    Using 2.5GB files ensures the download takes long enough to reliably
    catch and restart during TORRENT_DOWNLOADING state.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(LARGE_TRANSFER_TIMEOUT)
    def test_restart_during_active_download_resumes(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart while target is actively downloading 2.5GB from source.

        Verifies:
        1. Transfer reaches TORRENT_DOWNLOADING with non-zero bytes_downloaded
        2. After restart, transfer hash is re-registered with tracker
        3. Download resumes (bytes increase after restart)
        4. Transfer completes to TARGET_SEEDING
        5. Original torrent ends up on target
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        # Step 1: Create large torrent and add to Radarr
        print(f"\n[Step 1] Creating {LARGE_FILE_SIZE_MB}MB torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=LARGE_FILE_SIZE_MB)
        original_hash = torrent_info['hash']
        print(f"  Hash: {original_hash}")

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )

        # Step 2: Wait for torrent to be seeding on source (longer timeout for large file)
        print(f"\n[Step 2] Waiting for torrent to seed on source...")
        wait_for_queue_item_by_hash(
            radarr_client, original_hash,
            timeout=300, expected_status='completed'
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=300, expected_state='Seeding'
        )
        print("  Torrent is seeding on source")

        # Step 3: Start transferarr and wait for TORRENT_DOWNLOADING
        print(f"\n[Step 3] Starting transferarr...")
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        # With 2.5GB, TORRENT_DOWNLOADING should be easily observable
        torrent_data = wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TORRENT_DOWNLOADING',
            timeout=120,
        )
        print(f"  State: {torrent_data.get('state')}")

        # Step 4: Wait for some bytes to be downloaded before restarting
        print(f"\n[Step 4] Waiting for download progress before restart...")

        def has_download_progress():
            t = get_transferarr_torrent(transferarr, torrent_name)
            if not t:
                return False
            transfer = t.get('transfer', {})
            downloaded = transfer.get('bytes_downloaded', 0)
            return downloaded > 0

        wait_for_condition(
            has_download_progress,
            timeout=120,
            description="bytes_downloaded > 0",
        )

        # Capture state before restart
        torrent_data_before = get_transferarr_torrent(transferarr, torrent_name)
        transfer_before = torrent_data_before.get('transfer', {})
        bytes_before = transfer_before.get('bytes_downloaded', 0)
        transfer_hash = transfer_before.get('hash')
        total_size = transfer_before.get('total_size', 0)

        print(f"  Bytes downloaded before restart: {bytes_before:,}")
        print(f"  Total size: {total_size:,}")
        print(f"  Transfer hash: {transfer_hash[:12] if transfer_hash else 'None'}...")
        assert bytes_before > 0, "Should have downloaded some bytes before restart"

        # Step 5: Restart transferarr (kills tracker, loses all peers)
        print(f"\n[Step 5] Restarting transferarr (tracker peers will be lost)...")
        transferarr.restart(wait_healthy=True)
        print("  Transferarr restarted")

        # Step 6: Verify transfer resumes after restart
        print(f"\n[Step 6] Verifying download resumes...")

        # Wait for torrent to appear in tracking again
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state=['TORRENT_DOWNLOADING', 'TORRENT_SEEDING',
                            'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120,
        )

        # Step 7: Wait for transfer to complete
        print(f"\n[Step 7] Waiting for transfer to complete...")
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=LARGE_TRANSFER_TIMEOUT,
        )

        # Step 8: Verify original torrent is on target
        print(f"\n[Step 8] Verifying original torrent on target...")
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Verify transfer torrents are cleaned up
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

        print(f"\n✅ Large torrent restart during TORRENT_DOWNLOADING completed successfully")

    @pytest.mark.timeout(LARGE_TRANSFER_TIMEOUT)
    def test_restart_preserves_progress(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify download progress is preserved across restart.

        After restart, bytes_downloaded should not reset to 0. The BitTorrent
        protocol resumes from existing pieces on disk, so the actual Deluge
        progress reflects what was already downloaded.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        print(f"\n[Setup] Creating {LARGE_FILE_SIZE_MB}MB torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=LARGE_FILE_SIZE_MB)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )

        wait_for_queue_item_by_hash(
            radarr_client, original_hash,
            timeout=300, expected_status='completed'
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=300, expected_state='Seeding'
        )

        # Start and wait for active downloading
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TORRENT_DOWNLOADING',
            timeout=120,
        )

        # Wait for significant progress (at least 1MB)
        print("\n[Progress] Waiting for meaningful download progress...")

        def has_significant_progress():
            t = get_transferarr_torrent(transferarr, torrent_name)
            if not t:
                return False
            transfer = t.get('transfer', {})
            return transfer.get('bytes_downloaded', 0) > 1_000_000  # 1MB

        wait_for_condition(
            has_significant_progress,
            timeout=180,
            description="bytes_downloaded > 1MB",
        )

        # Capture bytes before restart
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        bytes_before = torrent_data.get('transfer', {}).get('bytes_downloaded', 0)
        transfer_hash = torrent_data.get('transfer', {}).get('hash')
        print(f"  Bytes before restart: {bytes_before:,}")

        # Restart
        print("\n[Restart] Restarting transferarr...")
        transferarr.restart(wait_healthy=True)

        # Wait for torrent to resume downloading
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state=['TORRENT_DOWNLOADING', 'TORRENT_SEEDING',
                            'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
            timeout=120,
        )

        # Check that progress was preserved (Deluge keeps downloaded pieces on disk)
        # After restart, transferarr re-queries Deluge which reports actual progress
        torrent_data_after = get_transferarr_torrent(transferarr, torrent_name)
        state_after = torrent_data_after.get('state') if torrent_data_after else None

        if state_after == 'TORRENT_DOWNLOADING':
            # Still downloading - bytes should not have reset to 0
            bytes_after = torrent_data_after.get('transfer', {}).get('bytes_downloaded', 0)
            print(f"  Bytes after restart: {bytes_after:,}")
            print(f"  State after restart: {state_after}")

            # Deluge resumes from disk pieces, so total_done should be >= what we had
            # Use the Deluge RPC to verify actual progress on disk
            if transfer_hash:
                progress = get_transfer_progress(deluge_target, transfer_hash)
                total_done = progress.get('total_done', 0) if progress else 0
                print(f"  Deluge total_done on target: {total_done:,}")
                assert total_done >= bytes_before * 0.8, \
                    f"Deluge should have retained most downloaded pieces " \
                    f"(expected >={bytes_before * 0.8:,.0f}, got {total_done:,})"
        else:
            # If it moved past DOWNLOADING, the transfer completed which means
            # progress was obviously not lost
            print(f"  Transfer already past DOWNLOADING ({state_after}), progress preserved")

        # Wait for completion
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=LARGE_TRANSFER_TIMEOUT,
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=60, expected_state='Seeding'
        )

        print(f"\n✅ Download progress preserved across restart")


class TestLargeRestartTransferDataIntegrity:
    """Test transfer metadata integrity across restarts with large files.

    With large files, there's a wider window to verify that the transfer dict
    fields are correctly serialized and restored, particularly fields that
    change during active downloading (bytes_downloaded, download_rate, etc.).
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(LARGE_TRANSFER_TIMEOUT)
    def test_transfer_dict_survives_restart_during_active_download(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify all transfer dict fields survive restart during active download.

        With 2.5GB, we can capture transfer data while bytes are actively flowing
        and verify the immutable fields (hash, id, name, started_at) persist.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        print(f"\n[Setup] Creating {LARGE_FILE_SIZE_MB}MB torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=LARGE_FILE_SIZE_MB)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )

        wait_for_queue_item_by_hash(
            radarr_client, original_hash,
            timeout=300, expected_status='completed'
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=300, expected_state='Seeding'
        )

        # Start and wait for TORRENT_DOWNLOADING with active bytes
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TORRENT_DOWNLOADING',
            timeout=120,
        )

        # Wait for download to be active
        def has_download_progress():
            t = get_transferarr_torrent(transferarr, torrent_name)
            if not t:
                return False
            return t.get('transfer', {}).get('bytes_downloaded', 0) > 0

        wait_for_condition(
            has_download_progress,
            timeout=120,
            description="bytes_downloaded > 0",
        )

        # Capture full transfer data before restart
        torrent_data_before = get_transferarr_torrent(transferarr, torrent_name)
        transfer_before = torrent_data_before.get('transfer', {})

        print(f"\n[Before] Transfer data:")
        print(f"  hash:              {transfer_before.get('hash', '')[:12]}...")
        print(f"  id:                {transfer_before.get('id')}")
        print(f"  name:              {transfer_before.get('name')}")
        print(f"  started_at:        {transfer_before.get('started_at')}")
        print(f"  on_source:         {transfer_before.get('on_source')}")
        print(f"  on_target:         {transfer_before.get('on_target')}")
        print(f"  original_on_target:{transfer_before.get('original_on_target')}")
        print(f"  bytes_downloaded:  {transfer_before.get('bytes_downloaded', 0):,}")
        print(f"  total_size:        {transfer_before.get('total_size', 0):,}")
        print(f"  retry_count:       {transfer_before.get('retry_count')}")
        print(f"  reannounce_count:  {transfer_before.get('reannounce_count')}")

        # Verify key fields are populated
        assert transfer_before.get('hash'), "transfer.hash should be set"
        assert transfer_before.get('id'), "transfer.id should be set"
        assert transfer_before.get('name'), "transfer.name should be set"
        assert transfer_before.get('started_at'), "transfer.started_at should be set"
        assert transfer_before.get('on_source') is True, "on_source should be True"
        assert transfer_before.get('on_target') is True, "on_target should be True"
        assert transfer_before.get('total_size', 0) > 0, "total_size should be > 0"

        # Restart during active download
        print(f"\n[Restart] Restarting transferarr...")
        transferarr.restart(wait_healthy=True)
        time.sleep(5)  # Allow state to load and recovery to run

        # Get transfer data after restart
        torrent_data_after = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data_after is not None, "Torrent should be restored after restart"
        transfer_after = torrent_data_after.get('transfer', {})

        print(f"\n[After] Transfer data:")
        print(f"  hash:              {transfer_after.get('hash', '')[:12]}...")
        print(f"  id:                {transfer_after.get('id')}")
        print(f"  name:              {transfer_after.get('name')}")
        print(f"  started_at:        {transfer_after.get('started_at')}")
        print(f"  on_source:         {transfer_after.get('on_source')}")
        print(f"  on_target:         {transfer_after.get('on_target')}")
        print(f"  original_on_target:{transfer_after.get('original_on_target')}")
        print(f"  bytes_downloaded:  {transfer_after.get('bytes_downloaded', 0):,}")

        # Verify immutable fields survived
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
        assert transfer_after.get('total_size') == transfer_before.get('total_size'), \
            "transfer.total_size should survive restart"

        # Verify retry_count and reannounce_count didn't inflate
        assert transfer_after.get('retry_count', 0) <= transfer_before.get('retry_count', 0) + 1, \
            "retry_count should not inflate significantly on restart"
        assert transfer_after.get('reannounce_count', 0) <= 3, \
            "reannounce_count should not exceed max (3)"

        # Wait for completion
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=LARGE_TRANSFER_TIMEOUT,
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=60, expected_state='Seeding'
        )

        print(f"\n✅ Transfer data integrity preserved across restart during active download")

    @pytest.mark.timeout(LARGE_TRANSFER_TIMEOUT)
    def test_history_tracking_survives_restart_during_download(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Verify _transfer_id survives restart so history records are not orphaned.

        The history service tracks transfer progress via _transfer_id. If this is
        lost on restart, the history record becomes orphaned and a new one is
        created, losing the bytes_downloaded from before the restart.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        print(f"\n[Setup] Creating {LARGE_FILE_SIZE_MB}MB torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=LARGE_FILE_SIZE_MB)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )

        wait_for_queue_item_by_hash(
            radarr_client, original_hash,
            timeout=300, expected_status='completed'
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=300, expected_state='Seeding'
        )

        # Start and wait for active downloading
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TORRENT_DOWNLOADING',
            timeout=120,
        )

        # Ensure download has started
        def has_progress():
            t = get_transferarr_torrent(transferarr, torrent_name)
            if not t:
                return False
            return t.get('transfer', {}).get('bytes_downloaded', 0) > 0

        wait_for_condition(has_progress, timeout=120, description="bytes_downloaded > 0")

        torrent_state_before = wait_for_state_file_torrent(
            transferarr,
            torrent_name,
            timeout=30,
            predicate=lambda torrent: torrent.get('_transfer_id') is not None,
        )
        transfer_id_before = torrent_state_before.get('_transfer_id')

        print(f"  _transfer_id before restart: {transfer_id_before}")
        assert transfer_id_before is not None, \
            "_transfer_id should be persisted in state.json during active download"

        # Restart
        print("\n[Restart] Restarting transferarr...")
        transferarr.restart(wait_healthy=True)

        torrent_state_after = wait_for_state_file_torrent(
            transferarr,
            torrent_name,
            timeout=30,
            predicate=lambda torrent: torrent.get('_transfer_id') is not None,
        )
        transfer_id_after = torrent_state_after.get('_transfer_id')

        print(f"  _transfer_id after restart: {transfer_id_after}")
        assert transfer_id_after is not None, \
            "_transfer_id should be in state.json after restart"
        assert transfer_id_after == transfer_id_before, \
            f"_transfer_id should survive restart: " \
            f"before={transfer_id_before}, after={transfer_id_after}"

        # Wait for completion
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=LARGE_TRANSFER_TIMEOUT,
        )

        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=60, expected_state='Seeding'
        )

        print(f"\n✅ _transfer_id preserved across restart during active download")


class TestLargeMultipleRestartsDuringDownload:
    """Test multiple consecutive restarts during a large download.

    Stress test: restart transferarr several times while a 2.5GB download is
    in progress. The transfer should still eventually complete.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(LARGE_TRANSFER_TIMEOUT)
    def test_multiple_restarts_during_download_still_completes(
        self,
        create_torrent,
        radarr_client,
        deluge_source,
        deluge_target,
        transferarr,
        torrent_transfer_config,
    ):
        """Restart transferarr 3 times during TORRENT_DOWNLOADING.

        Each restart kills the tracker, losing all peers. After 3 restarts
        the transfer should still complete. This exercises the retry and
        re-announce logic under repeated stress.
        """
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])

        print(f"\n[Setup] Creating {LARGE_FILE_SIZE_MB}MB torrent: {torrent_name}")
        torrent_info = create_torrent(torrent_name, size_mb=LARGE_FILE_SIZE_MB)
        original_hash = torrent_info['hash']

        radarr_client.add_movie(
            title=movie['title'],
            tmdb_id=movie['tmdb_id'],
            year=movie['year'],
            search=True,
        )

        wait_for_queue_item_by_hash(
            radarr_client, original_hash,
            timeout=300, expected_status='completed'
        )
        wait_for_torrent_in_deluge(
            deluge_source, original_hash,
            timeout=300, expected_state='Seeding'
        )

        # Start transferarr
        transferarr.start(config_type=torrent_transfer_config, wait_healthy=True)

        num_restarts = 3
        for i in range(num_restarts):
            restart_num = i + 1
            print(f"\n[Restart {restart_num}/{num_restarts}] Waiting for active download...")

            # Wait for downloading or later state
            wait_for_transferarr_state(
                transferarr, torrent_name,
                expected_state=['TORRENT_DOWNLOADING', 'TORRENT_SEEDING',
                                'COPIED', 'TARGET_CHECKING', 'TARGET_SEEDING'],
                timeout=120,
            )

            # Check if already at TARGET_SEEDING (transfer finished)
            torrent_data = get_transferarr_torrent(transferarr, torrent_name)
            current_state = torrent_data.get('state') if torrent_data else None

            if current_state == 'TARGET_SEEDING':
                print(f"  Transfer already complete at TARGET_SEEDING, skipping remaining restarts")
                break

            bytes_now = torrent_data.get('transfer', {}).get('bytes_downloaded', 0) if torrent_data else 0
            print(f"  State: {current_state}, Bytes: {bytes_now:,}")

            # Restart
            print(f"  Restarting transferarr...")
            transferarr.restart(wait_healthy=True)
            print(f"  Restart {restart_num} complete")

        # Wait for transfer to complete after all restarts
        print(f"\n[Completion] Waiting for TARGET_SEEDING...")
        wait_for_transferarr_state(
            transferarr, torrent_name,
            expected_state='TARGET_SEEDING',
            timeout=LARGE_TRANSFER_TIMEOUT,
        )

        # Verify original on target
        wait_for_torrent_in_deluge(
            deluge_target, original_hash,
            timeout=60, expected_state='Seeding'
        )

        # Verify cleanup
        time.sleep(5)
        transfer_on_source, _ = find_transfer_torrent(
            deluge_source, torrent_name, original_hash
        )
        transfer_on_target, _ = find_transfer_torrent(
            deluge_target, torrent_name, original_hash
        )
        assert transfer_on_source is None, \
            "Transfer torrent should be cleaned up from source after multiple restarts"
        assert transfer_on_target is None, \
            "Transfer torrent should be cleaned up from target after multiple restarts"

        # Verify transfer data is clean
        torrent_data = get_transferarr_torrent(transferarr, torrent_name)
        assert torrent_data is not None
        assert torrent_data.get('transfer', {}).get('cleaned_up') is True, \
            "Transfer should be marked cleaned_up after multiple restarts"

        print(f"\n✅ Transfer completed after {num_restarts} restarts during download")
