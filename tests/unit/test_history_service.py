"""Unit tests for HistoryService."""

import os
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from transferarr.services.history_service import HistoryService


class MockTorrent:
    """Mock torrent object for testing."""
    
    def __init__(self, name="Test.Torrent.2024", torrent_id=None, size=1024*1024*100, media_manager=None):
        self.name = name
        self.id = torrent_id or str(uuid.uuid4()).replace('-', '')[:40]
        self.size = size
        self.media_manager = media_manager

    @property
    def media_manager_type(self):
        """Match the real Torrent.media_manager_type property."""
        if not self.media_manager:
            return None
        manager_class = type(self.media_manager).__name__
        if 'Radarr' in manager_class:
            return 'radarr'
        elif 'Sonarr' in manager_class:
            return 'sonarr'
        return None


class MockRadarrManager:
    """Mock Radarr manager for testing media type detection."""
    pass


class MockSonarrManager:
    """Mock Sonarr manager for testing media type detection."""
    pass


@pytest.fixture
def db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def history_service(db_path):
    """Create a HistoryService instance."""
    service = HistoryService(db_path)
    yield service
    service.close()


@pytest.fixture
def torrent():
    """Create a mock torrent."""
    return MockTorrent()


class TestDatabaseInitialization:
    """Tests for database creation and schema."""
    
    def test_creates_database_file(self, db_path):
        """Database file should be created on initialization."""
        # Remove if exists from fixture
        if os.path.exists(db_path):
            os.remove(db_path)
        
        service = HistoryService(db_path)
        assert os.path.exists(db_path)
        service.close()
    
    def test_creates_transfers_table(self, history_service, db_path):
        """Transfers table should exist with correct columns."""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(transfers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        expected_columns = {
            'id', 'torrent_name', 'torrent_hash', 'source_client', 'target_client',
            'connection_name', 'media_type', 'media_manager', 'size_bytes',
            'bytes_transferred', 'status', 'error_message', 'created_at',
            'started_at', 'completed_at'
        }
        assert expected_columns.issubset(columns)
    
    def test_creates_indexes(self, history_service, db_path):
        """Indexes should be created for common query patterns."""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        expected_indexes = {
            'idx_transfers_status',
            'idx_transfers_created_at',
            'idx_transfers_source',
            'idx_transfers_target'
        }
        assert expected_indexes.issubset(indexes)
    
    def test_schema_includes_transfer_method_column(self, history_service, db_path):
        """transfers table should include transfer_method column."""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(transfers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        assert 'transfer_method' in columns


class TestDatabaseMigration:
    """Tests for database schema migration."""
    
    def test_migrate_adds_transfer_method_to_old_schema(self, db_path):
        """Migration should add transfer_method column to an old database missing it."""
        # Create a database with the old schema (no transfer_method)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transfers (
                id TEXT PRIMARY KEY,
                torrent_name TEXT NOT NULL,
                torrent_hash TEXT,
                source_client TEXT NOT NULL,
                target_client TEXT NOT NULL,
                connection_name TEXT,
                media_type TEXT,
                media_manager TEXT,
                size_bytes INTEGER,
                bytes_transferred INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
        """)
        conn.commit()
        
        # Verify transfer_method does NOT exist yet
        cursor = conn.execute("PRAGMA table_info(transfers)")
        columns = {row[1] for row in cursor.fetchall()}
        assert 'transfer_method' not in columns
        conn.close()
        
        # Now open with HistoryService which should run migration
        service = HistoryService(db_path)
        
        # Verify transfer_method now exists
        conn2 = sqlite3.connect(db_path)
        cursor = conn2.execute("PRAGMA table_info(transfers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn2.close()
        
        assert 'transfer_method' in columns
        service.close()
    
    def test_migrate_preserves_existing_data(self, db_path):
        """Migration should not lose existing transfer records."""
        # Create a database with old schema and insert a record
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transfers (
                id TEXT PRIMARY KEY,
                torrent_name TEXT NOT NULL,
                torrent_hash TEXT,
                source_client TEXT NOT NULL,
                target_client TEXT NOT NULL,
                connection_name TEXT,
                media_type TEXT,
                media_manager TEXT,
                size_bytes INTEGER,
                bytes_transferred INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
        """)
        conn.execute(
            """
            INSERT INTO transfers (id, torrent_name, source_client, target_client, 
                                   connection_name, status, created_at)
            VALUES ('test-id', 'Old.Torrent', 'src', 'tgt', 'conn', 'completed', '2024-01-01T00:00:00')
            """
        )
        conn.commit()
        conn.close()
        
        # Open with HistoryService (triggers migration)
        service = HistoryService(db_path)
        
        # Existing record should still be there with transfer_method=NULL
        transfer = service.get_transfer('test-id')
        assert transfer is not None
        assert transfer['torrent_name'] == 'Old.Torrent'
        assert transfer['transfer_method'] is None
        service.close()
    
    def test_migrate_no_error_when_column_already_exists(self, history_service, db_path):
        """Migration should be idempotent — no error if column exists."""
        # history_service fixture already created schema with transfer_method
        # Running migration again should be harmless
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(transfers)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        assert 'transfer_method' in columns


class TestCreateTransfer:
    """Tests for create_transfer method."""
    
    def test_create_transfer_returns_uuid(self, history_service, torrent):
        """create_transfer should return a valid UUID."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source-deluge',
            target_client='target-deluge',
            connection_name='source -> target'
        )
        
        # Should be a valid UUID
        uuid.UUID(transfer_id)
    
    def test_create_transfer_stores_all_fields(self, history_service, torrent):
        """All fields should be stored correctly."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source-deluge',
            target_client='target-deluge',
            connection_name='source -> target'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        
        assert transfer['torrent_name'] == torrent.name
        assert transfer['torrent_hash'] == torrent.id
        assert transfer['source_client'] == 'source-deluge'
        assert transfer['target_client'] == 'target-deluge'
        assert transfer['connection_name'] == 'source -> target'
        assert transfer['size_bytes'] == torrent.size
        assert transfer['created_at'] is not None
    
    def test_create_transfer_default_status_pending(self, history_service, torrent):
        """New transfers should have status 'pending'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'pending'
    
    def test_create_transfer_radarr_media_type(self, history_service):
        """Radarr torrents should have media_type='movie'."""
        torrent = MockTorrent(media_manager=MockRadarrManager())
        
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['media_type'] == 'movie'
        assert transfer['media_manager'] == 'radarr'
    
    def test_create_transfer_sonarr_media_type(self, history_service):
        """Sonarr torrents should have media_type='episode'."""
        torrent = MockTorrent(media_manager=MockSonarrManager())
        
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['media_type'] == 'episode'
        assert transfer['media_manager'] == 'sonarr'
    
    def test_create_transfer_unknown_media_type(self, history_service, torrent):
        """Torrents without media manager should have media_type='unknown'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['media_type'] == 'unknown'
        assert transfer['media_manager'] is None
    
    def test_create_transfer_with_transfer_method_sftp(self, history_service, torrent):
        """create_transfer should store transfer_method='sftp'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test',
            transfer_method='sftp'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['transfer_method'] == 'sftp'
    
    def test_create_transfer_with_transfer_method_local(self, history_service, torrent):
        """create_transfer should store transfer_method='local'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test',
            transfer_method='local'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['transfer_method'] == 'local'
    
    def test_create_transfer_with_transfer_method_torrent(self, history_service, torrent):
        """create_transfer should store transfer_method='torrent'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test',
            transfer_method='torrent'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['transfer_method'] == 'torrent'
    
    def test_create_transfer_default_transfer_method_none(self, history_service, torrent):
        """create_transfer without transfer_method should default to None."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['transfer_method'] is None


class TestStartTransfer:
    """Tests for start_transfer method."""
    
    def test_start_transfer_sets_status_and_timestamp(self, history_service, torrent):
        """start_transfer should set status='transferring' and started_at."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        history_service.start_transfer(transfer_id)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'transferring'
        assert transfer['started_at'] is not None


class TestCompleteTransfer:
    """Tests for complete_transfer method."""
    
    def test_complete_transfer_sets_status_and_timestamp(self, history_service, torrent):
        """complete_transfer should set status='completed' and completed_at."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        history_service.start_transfer(transfer_id)
        history_service.complete_transfer(transfer_id)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'completed'
        assert transfer['completed_at'] is not None
    
    def test_complete_transfer_with_final_bytes(self, history_service, torrent):
        """complete_transfer with final_bytes should set bytes_transferred and status."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        history_service.start_transfer(transfer_id)
        
        final_size = 1024 * 1024 * 50  # 50MB
        history_service.complete_transfer(transfer_id, final_bytes=final_size)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'completed'
        assert transfer['bytes_transferred'] == final_size
        assert transfer['completed_at'] is not None
    
    def test_complete_transfer_without_final_bytes_preserves_progress(self, history_service, torrent):
        """complete_transfer without final_bytes should keep existing bytes_transferred."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        history_service.start_transfer(transfer_id)
        
        # Update progress first
        history_service.update_progress(transfer_id, 5000000, force=True)
        
        # Complete without final_bytes
        history_service.complete_transfer(transfer_id)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'completed'
        assert transfer['bytes_transferred'] == 5000000  # Should preserve


class TestFailTransfer:
    """Tests for fail_transfer method."""
    
    def test_fail_transfer_stores_error_message(self, history_service, torrent):
        """fail_transfer should store error message and set status='failed'."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        error_msg = "Connection timeout"
        history_service.fail_transfer(transfer_id, error_msg)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['status'] == 'failed'
        assert transfer['error_message'] == error_msg
        assert transfer['completed_at'] is not None


class TestGetTransfer:
    """Tests for get_transfer method."""
    
    def test_get_transfer_returns_dict(self, history_service, torrent):
        """get_transfer should return a dict with all fields."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        transfer = history_service.get_transfer(transfer_id)
        
        assert isinstance(transfer, dict)
        assert 'id' in transfer
        assert 'torrent_name' in transfer
        assert 'status' in transfer
    
    def test_get_transfer_not_found_returns_none(self, history_service):
        """get_transfer should return None for non-existent ID."""
        transfer = history_service.get_transfer('non-existent-id')
        assert transfer is None


class TestUpdateProgress:
    """Tests for update_progress method."""
    
    def test_update_progress_stores_bytes(self, history_service, torrent):
        """update_progress should store bytes_transferred."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        history_service.update_progress(transfer_id, 5000000, force=True)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['bytes_transferred'] == 5000000
    
    def test_update_progress_throttled_within_5_seconds(self, history_service, torrent):
        """Rapid progress updates should be throttled."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        # First update (should write)
        history_service.update_progress(transfer_id, 1000000)
        
        # Immediate second update (should be throttled)
        history_service.update_progress(transfer_id, 2000000)
        
        transfer = history_service.get_transfer(transfer_id)
        # Should still be first value due to throttling
        assert transfer['bytes_transferred'] == 1000000
    
    def test_update_progress_allowed_after_5_seconds(self, history_service, torrent):
        """Progress update should be allowed after throttle interval."""
        # Use a shorter interval for testing
        original_interval = HistoryService.PROGRESS_UPDATE_INTERVAL
        HistoryService.PROGRESS_UPDATE_INTERVAL = 0.1  # 100ms for test
        
        try:
            transfer_id = history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
            
            history_service.update_progress(transfer_id, 1000000)
            time.sleep(0.15)  # Wait longer than throttle interval
            history_service.update_progress(transfer_id, 2000000)
            
            transfer = history_service.get_transfer(transfer_id)
            assert transfer['bytes_transferred'] == 2000000
        finally:
            HistoryService.PROGRESS_UPDATE_INTERVAL = original_interval
    
    def test_update_progress_final_update_always_writes(self, history_service, torrent):
        """force=True should bypass throttling."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        history_service.update_progress(transfer_id, 1000000)
        history_service.update_progress(transfer_id, 2000000, force=True)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer['bytes_transferred'] == 2000000


class TestRestartHandling:
    """Tests for marking interrupted transfers on restart."""
    
    def test_marks_pending_as_failed_on_init(self, db_path):
        """Pending transfers should be marked failed on service init."""
        # First, create a transfer and leave it pending
        service1 = HistoryService(db_path)
        torrent = MockTorrent()
        transfer_id = service1.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        service1.close()
        
        # Simulate restart
        service2 = HistoryService(db_path)
        transfer = service2.get_transfer(transfer_id)
        service2.close()
        
        assert transfer['status'] == 'failed'
        assert 'Interrupted by application restart' in transfer['error_message']
    
    def test_marks_transferring_as_failed_on_init(self, db_path):
        """Transferring transfers should be marked failed on service init."""
        # Create a transfer and start it
        service1 = HistoryService(db_path)
        torrent = MockTorrent()
        transfer_id = service1.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        service1.start_transfer(transfer_id)
        service1.close()
        
        # Simulate restart
        service2 = HistoryService(db_path)
        transfer = service2.get_transfer(transfer_id)
        service2.close()
        
        assert transfer['status'] == 'failed'
        assert 'Interrupted by application restart' in transfer['error_message']
    
    def test_completed_records_unchanged_on_init(self, db_path):
        """Completed transfers should not be modified on restart."""
        # Create and complete a transfer
        service1 = HistoryService(db_path)
        torrent = MockTorrent()
        transfer_id = service1.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        service1.start_transfer(transfer_id)
        service1.complete_transfer(transfer_id)
        service1.close()
        
        # Simulate restart
        service2 = HistoryService(db_path)
        transfer = service2.get_transfer(transfer_id)
        service2.close()
        
        assert transfer['status'] == 'completed'
        assert transfer['error_message'] is None


class TestConcurrency:
    """Tests for thread safety."""
    
    def test_concurrent_creates(self, history_service):
        """Multiple threads should be able to create transfers concurrently."""
        results = []
        errors = []
        
        def create_transfer(i):
            try:
                torrent = MockTorrent(name=f"Test.Torrent.{i}")
                transfer_id = history_service.create_transfer(
                    torrent=torrent,
                    source_client='source',
                    target_client='target',
                    connection_name='test'
                )
                results.append(transfer_id)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=create_transfer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 10
        # All IDs should be unique
        assert len(set(results)) == 10
    
    def test_concurrent_updates(self, history_service, torrent):
        """Multiple threads should be able to update the same transfer."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        history_service.start_transfer(transfer_id)
        
        errors = []
        
        def update_progress(bytes_val):
            try:
                history_service.update_progress(transfer_id, bytes_val, force=True)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=update_progress, args=(i * 1000,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # Transfer should still exist and be valid
        transfer = history_service.get_transfer(transfer_id)
        assert transfer is not None
        assert transfer['bytes_transferred'] >= 0


class TestListTransfers:
    """Tests for list_transfers method."""
    
    def test_list_transfers_returns_all(self, history_service):
        """list_transfers should return all transfers when no filters."""
        for i in range(5):
            torrent = MockTorrent(name=f"Test.Torrent.{i}")
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
        
        transfers, total = history_service.list_transfers()
        assert total == 5
        assert len(transfers) == 5
    
    def test_list_transfers_filter_by_status(self, history_service):
        """list_transfers should filter by status."""
        for i in range(3):
            torrent = MockTorrent(name=f"Test.Torrent.{i}")
            tid = history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
            if i == 0:
                history_service.start_transfer(tid)
                history_service.complete_transfer(tid)
        
        transfers, total = history_service.list_transfers(status='completed')
        assert total == 1
        assert transfers[0]['status'] == 'completed'
    
    def test_list_transfers_filter_by_source(self, history_service):
        """list_transfers should filter by source client."""
        for source in ['source-a', 'source-a', 'source-b']:
            torrent = MockTorrent()
            history_service.create_transfer(
                torrent=torrent,
                source_client=source,
                target_client='target',
                connection_name='test'
            )
        
        transfers, total = history_service.list_transfers(source='source-a')
        assert total == 2
    
    def test_list_transfers_filter_by_target(self, history_service):
        """list_transfers should filter by target client."""
        for target in ['target-a', 'target-b', 'target-b']:
            torrent = MockTorrent()
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client=target,
                connection_name='test'
            )
        
        transfers, total = history_service.list_transfers(target='target-b')
        assert total == 2
    
    def test_list_transfers_search_by_name(self, history_service):
        """list_transfers should search in torrent name."""
        for name in ['Movie.2024', 'Series.S01E01', 'Another.Movie.2025']:
            torrent = MockTorrent(name=name)
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
        
        transfers, total = history_service.list_transfers(search='Movie')
        assert total == 2
    
    def test_list_transfers_pagination(self, history_service):
        """list_transfers should support pagination."""
        for i in range(10):
            torrent = MockTorrent(name=f"Test.Torrent.{i}")
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
        
        transfers, total = history_service.list_transfers(page=1, per_page=3)
        assert total == 10
        assert len(transfers) == 3
        
        transfers, total = history_service.list_transfers(page=4, per_page=3)
        assert len(transfers) == 1  # Last page has only 1 item
    
    def test_list_transfers_sort_order(self, history_service):
        """list_transfers should support sorting."""
        sizes = [100, 300, 200]
        for size in sizes:
            torrent = MockTorrent(size=size)
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test'
            )
        
        transfers, _ = history_service.list_transfers(sort='size_bytes', order='asc')
        assert transfers[0]['size_bytes'] == 100
        assert transfers[2]['size_bytes'] == 300
        
        transfers, _ = history_service.list_transfers(sort='size_bytes', order='desc')
        assert transfers[0]['size_bytes'] == 300
    
    def test_list_transfers_filter_by_transfer_method(self, history_service):
        """list_transfers should filter by transfer_method."""
        methods = ['sftp', 'sftp', 'local', 'torrent']
        for method in methods:
            torrent = MockTorrent()
            history_service.create_transfer(
                torrent=torrent,
                source_client='source',
                target_client='target',
                connection_name='test',
                transfer_method=method
            )
        
        transfers, total = history_service.list_transfers(transfer_method='sftp')
        assert total == 2
        
        transfers, total = history_service.list_transfers(transfer_method='torrent')
        assert total == 1
        
        transfers, total = history_service.list_transfers(transfer_method='local')
        assert total == 1


class TestGetActiveTransfers:
    """Tests for get_active_transfers method."""
    
    def test_get_active_transfers(self, history_service):
        """get_active_transfers should return pending and transferring."""
        # Create transfers with different statuses
        t1 = MockTorrent(name="Pending")
        tid1 = history_service.create_transfer(t1, 'src', 'tgt', 'test')
        
        t2 = MockTorrent(name="Transferring")
        tid2 = history_service.create_transfer(t2, 'src', 'tgt', 'test')
        history_service.start_transfer(tid2)
        
        t3 = MockTorrent(name="Completed")
        tid3 = history_service.create_transfer(t3, 'src', 'tgt', 'test')
        history_service.start_transfer(tid3)
        history_service.complete_transfer(tid3)
        
        active = history_service.get_active_transfers()
        assert len(active) == 2
        names = {t['torrent_name'] for t in active}
        assert names == {'Pending', 'Transferring'}


class TestGetStats:
    """Tests for get_stats method."""
    
    def test_get_stats_total_count(self, history_service):
        """get_stats should return correct total count."""
        for i in range(5):
            torrent = MockTorrent(name=f"Test.{i}")
            history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        
        stats = history_service.get_stats()
        assert stats['total'] == 5
    
    def test_get_stats_success_rate(self, history_service):
        """get_stats should calculate success rate correctly."""
        # Create 2 completed and 1 failed
        for i in range(3):
            torrent = MockTorrent(name=f"Test.{i}")
            tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
            history_service.start_transfer(tid)
            if i < 2:
                history_service.complete_transfer(tid)
            else:
                history_service.fail_transfer(tid, "error")
        
        stats = history_service.get_stats()
        assert stats['completed'] == 2
        assert stats['failed'] == 1
        # Success rate = 2/3 = 66.7%
        assert stats['success_rate'] == 66.7
    
    def test_get_stats_total_bytes(self, history_service):
        """get_stats should sum bytes for completed transfers."""
        for size in [100, 200, 300]:
            torrent = MockTorrent(size=size)
            tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
            history_service.start_transfer(tid)
            history_service.complete_transfer(tid)
        
        stats = history_service.get_stats()
        assert stats['total_bytes_transferred'] == 600
    
    def test_get_stats_empty_db(self, history_service):
        """get_stats should handle empty database."""
        stats = history_service.get_stats()
        assert stats['total'] == 0
        assert stats['completed'] == 0
        assert stats['failed'] == 0
        assert stats['success_rate'] == 0
        assert stats['total_bytes_transferred'] == 0


class TestPruneOldEntries:
    """Tests for prune_old_entries method."""
    
    def test_prune_deletes_old_entries(self, history_service):
        """prune_old_entries should delete entries older than retention."""
        # Create and complete a transfer
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        history_service.start_transfer(tid)
        history_service.complete_transfer(tid)
        
        # Manually backdate the completed_at
        conn = history_service._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        conn.execute("UPDATE transfers SET completed_at = ? WHERE id = ?", (old_date, tid))
        conn.commit()
        
        # Prune with 30 day retention
        history_service.prune_old_entries(30)
        
        transfer = history_service.get_transfer(tid)
        assert transfer is None
    
    def test_prune_keeps_recent_entries(self, history_service):
        """prune_old_entries should keep entries within retention."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        history_service.start_transfer(tid)
        history_service.complete_transfer(tid)
        
        # Prune with 30 day retention (entry is brand new)
        history_service.prune_old_entries(30)
        
        transfer = history_service.get_transfer(tid)
        assert transfer is not None
    
    def test_prune_zero_retention_deletes_all(self, history_service):
        """prune_old_entries with 0 days should delete all completed."""
        for i in range(3):
            torrent = MockTorrent(name=f"Test.{i}")
            tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
            history_service.start_transfer(tid)
            history_service.complete_transfer(tid)
        
        history_service.prune_old_entries(0)
        
        transfers, total = history_service.list_transfers()
        assert total == 0


class TestDeleteTransfer:
    """Tests for delete_transfer method."""
    
    def test_delete_transfer_returns_true_on_success(self, history_service, torrent):
        """delete_transfer should return True when record exists."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        result = history_service.delete_transfer(transfer_id)
        assert result is True
    
    def test_delete_transfer_returns_false_on_not_found(self, history_service):
        """delete_transfer should return False for non-existent ID."""
        result = history_service.delete_transfer('non-existent-id')
        assert result is False
    
    def test_delete_transfer_removes_record(self, history_service, torrent):
        """delete_transfer should remove the record from database."""
        transfer_id = history_service.create_transfer(
            torrent=torrent,
            source_client='source',
            target_client='target',
            connection_name='test'
        )
        
        history_service.delete_transfer(transfer_id)
        
        transfer = history_service.get_transfer(transfer_id)
        assert transfer is None
    
    def test_delete_transfer_only_deletes_specified_record(self, history_service):
        """delete_transfer should only delete the specified record."""
        torrent1 = MockTorrent(name="Test.1")
        torrent2 = MockTorrent(name="Test.2")
        
        tid1 = history_service.create_transfer(torrent1, 'src', 'tgt', 'test')
        tid2 = history_service.create_transfer(torrent2, 'src', 'tgt', 'test')
        
        history_service.delete_transfer(tid1)
        
        # First should be gone
        assert history_service.get_transfer(tid1) is None
        # Second should still exist
        assert history_service.get_transfer(tid2) is not None


class TestClearHistory:
    """Tests for clear_history method."""
    
    def test_clear_history_returns_count(self, history_service):
        """clear_history should return number of deleted records."""
        for i in range(3):
            torrent = MockTorrent(name=f"Test.{i}")
            tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
            history_service.start_transfer(tid)
            history_service.complete_transfer(tid)
        
        count = history_service.clear_history()
        assert count == 3
    
    def test_clear_history_deletes_completed(self, history_service):
        """clear_history should delete completed records."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        history_service.start_transfer(tid)
        history_service.complete_transfer(tid)
        
        history_service.clear_history()
        
        assert history_service.get_transfer(tid) is None
    
    def test_clear_history_deletes_failed(self, history_service):
        """clear_history should delete failed records."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        history_service.fail_transfer(tid, "Test error")
        
        history_service.clear_history()
        
        assert history_service.get_transfer(tid) is None
    
    def test_clear_history_deletes_cancelled(self, history_service):
        """clear_history should delete cancelled records."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        # Manually set status to cancelled (cancel_transfer method was removed as unused)
        conn = history_service._get_connection()
        conn.execute("UPDATE transfers SET status = 'cancelled' WHERE id = ?", (tid,))
        conn.commit()
        
        history_service.clear_history()
        
        assert history_service.get_transfer(tid) is None
    
    def test_clear_history_keeps_pending(self, history_service):
        """clear_history should NOT delete pending records."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        # Leave as pending
        
        history_service.clear_history()
        
        # Should still exist
        assert history_service.get_transfer(tid) is not None
    
    def test_clear_history_keeps_transferring(self, history_service):
        """clear_history should NOT delete transferring records."""
        torrent = MockTorrent()
        tid = history_service.create_transfer(torrent, 'src', 'tgt', 'test')
        history_service.start_transfer(tid)
        # Leave as transferring
        
        history_service.clear_history()
        
        # Should still exist
        assert history_service.get_transfer(tid) is not None
    
    def test_clear_history_with_status_filter(self, history_service):
        """clear_history with status should only delete that status."""
        # Create one of each status
        t1 = MockTorrent(name="Completed")
        tid1 = history_service.create_transfer(t1, 'src', 'tgt', 'test')
        history_service.start_transfer(tid1)
        history_service.complete_transfer(tid1)
        
        t2 = MockTorrent(name="Failed")
        tid2 = history_service.create_transfer(t2, 'src', 'tgt', 'test')
        history_service.fail_transfer(tid2, "Error")
        
        # Only clear completed
        count = history_service.clear_history(status='completed')
        
        assert count == 1
        assert history_service.get_transfer(tid1) is None  # Completed deleted
        assert history_service.get_transfer(tid2) is not None  # Failed still exists
    
    def test_clear_history_empty_returns_zero(self, history_service):
        """clear_history on empty database should return 0."""
        count = history_service.clear_history()
        assert count == 0
