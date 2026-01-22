"""Transfer history service using SQLite for persistence."""

import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class HistoryService:
    """Service for tracking transfer history in SQLite.
    
    Thread-safe implementation using connection-per-thread pattern.
    On initialization, marks any pending/transferring records as failed
    (interrupted by application restart).
    """
    
    PROGRESS_UPDATE_INTERVAL = 5  # seconds between progress updates
    THROTTLE_CLEANUP_INTERVAL = 300  # 5 minutes between cleanup of stale throttle entries
    THROTTLE_ENTRY_TTL = 3600  # 1 hour TTL for throttle entries (stale if no updates)
    
    def __init__(self, db_path: str):
        """Initialize the history service.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._last_progress_update: dict[str, float] = {}  # transfer_id -> timestamp
        self._last_throttle_cleanup: float = 0
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_db()
        
        # Mark interrupted transfers as failed
        self._mark_interrupted_transfers()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transfers (
                id TEXT PRIMARY KEY,
                torrent_name TEXT NOT NULL,
                torrent_hash TEXT NOT NULL,
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
            
            CREATE INDEX IF NOT EXISTS idx_transfers_status ON transfers(status);
            CREATE INDEX IF NOT EXISTS idx_transfers_created_at ON transfers(created_at);
            CREATE INDEX IF NOT EXISTS idx_transfers_source ON transfers(source_client);
            CREATE INDEX IF NOT EXISTS idx_transfers_target ON transfers(target_client);
            CREATE INDEX IF NOT EXISTS idx_transfers_hash ON transfers(torrent_hash);
        """)
        conn.commit()
    
    def _mark_interrupted_transfers(self):
        """Mark any pending/transferring records as failed on startup."""
        conn = self._get_connection()
        now = _utc_now().isoformat()
        conn.execute(
            """
            UPDATE transfers 
            SET status = 'failed', 
                error_message = 'Interrupted by application restart',
                completed_at = ?
            WHERE status IN ('pending', 'transferring')
            """,
            (now,)
        )
        conn.commit()
    
    def create_transfer(
        self,
        torrent,
        source_client: str,
        target_client: str,
        connection_name: str
    ) -> str:
        """Create a new transfer record.
        
        Args:
            torrent: Torrent object with name, id (hash), size, media_manager
            source_client: Name of source download client
            target_client: Name of target download client
            connection_name: Name of the transfer connection
            
        Returns:
            Generated UUID for the transfer record
        """
        transfer_id = str(uuid.uuid4())
        
        # Extract media info from torrent
        media_manager = None
        media_type = 'unknown'
        if torrent.media_manager:
            manager_type = type(torrent.media_manager).__name__
            if 'Radarr' in manager_type:
                media_manager = 'radarr'
                media_type = 'movie'
            elif 'Sonarr' in manager_type:
                media_manager = 'sonarr'
                media_type = 'episode'
        
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO transfers (
                id, torrent_name, torrent_hash, source_client, target_client,
                connection_name, media_type, media_manager, size_bytes,
                bytes_transferred, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?)
            """,
            (
                transfer_id,
                torrent.name,
                torrent.id,
                source_client,
                target_client,
                connection_name,
                media_type,
                media_manager,
                getattr(torrent, 'size', None),
                _utc_now().isoformat()
            )
        )
        conn.commit()
        
        return transfer_id
    
    def start_transfer(self, transfer_id: str):
        """Mark transfer as started.
        
        Args:
            transfer_id: UUID of the transfer
        """
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE transfers 
            SET status = 'transferring', started_at = ?
            WHERE id = ?
            """,
            (_utc_now().isoformat(), transfer_id)
        )
        conn.commit()
    
    def update_progress(self, transfer_id: str, bytes_transferred: int, force: bool = False):
        """Update bytes transferred for a transfer.
        
        Throttled to max once per PROGRESS_UPDATE_INTERVAL seconds per transfer
        to avoid excessive database writes. Periodically cleans up stale entries
        from the throttle tracking dict to prevent memory leaks.
        
        Args:
            transfer_id: UUID of the transfer
            bytes_transferred: Total bytes transferred so far
            force: If True, bypass throttling (use for final update)
        """
        now = time.time()
        
        with self._lock:
            last_update = self._last_progress_update.get(transfer_id, 0)
            
            if not force and (now - last_update) < self.PROGRESS_UPDATE_INTERVAL:
                return  # Throttled
            
            self._last_progress_update[transfer_id] = now
            
            # Periodic cleanup of stale throttle entries (entries older than TTL)
            if now - self._last_throttle_cleanup > self.THROTTLE_CLEANUP_INTERVAL:
                cutoff = now - self.THROTTLE_ENTRY_TTL
                stale_ids = [
                    tid for tid, ts in self._last_progress_update.items()
                    if ts < cutoff
                ]
                for tid in stale_ids:
                    del self._last_progress_update[tid]
                self._last_throttle_cleanup = now
        
        conn = self._get_connection()
        conn.execute(
            "UPDATE transfers SET bytes_transferred = ? WHERE id = ?",
            (bytes_transferred, transfer_id)
        )
        conn.commit()
    
    def complete_transfer(self, transfer_id: str):
        """Mark transfer as completed.
        
        Args:
            transfer_id: UUID of the transfer
        """
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE transfers 
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (_utc_now().isoformat(), transfer_id)
        )
        conn.commit()
        
        # Clean up throttle tracking
        with self._lock:
            self._last_progress_update.pop(transfer_id, None)
    
    def fail_transfer(self, transfer_id: str, error_message: str):
        """Mark transfer as failed.
        
        Args:
            transfer_id: UUID of the transfer
            error_message: Error description
        """
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE transfers 
            SET status = 'failed', error_message = ?, completed_at = ?
            WHERE id = ?
            """,
            (error_message, _utc_now().isoformat(), transfer_id)
        )
        conn.commit()
        
        # Clean up throttle tracking
        with self._lock:
            self._last_progress_update.pop(transfer_id, None)
    
    def get_transfer(self, transfer_id: str) -> Optional[dict]:
        """Get a single transfer by ID.
        
        Args:
            transfer_id: UUID of the transfer
            
        Returns:
            Transfer dict or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM transfers WHERE id = ?",
            (transfer_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def list_transfers(
        self,
        status: Optional[str] = None,
        source: Optional[str] = None,
        target: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 25,
        sort: str = 'created_at',
        order: str = 'desc'
    ) -> tuple[list[dict], int]:
        """List transfers with filtering and pagination.
        
        Args:
            status: Filter by status
            source: Filter by source client
            target: Filter by target client
            search: Search in torrent name
            start_date: Filter by created_at >= date (ISO format)
            end_date: Filter by created_at <= date (ISO format)
            page: Page number (1-indexed)
            per_page: Items per page
            sort: Sort field (created_at, completed_at, size_bytes)
            order: Sort order (asc, desc)
            
        Returns:
            Tuple of (list of transfer dicts, total count)
        """
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if source:
            conditions.append("source_client = ?")
            params.append(source)
        
        if target:
            conditions.append("target_client = ?")
            params.append(target)
        
        if search:
            conditions.append("torrent_name LIKE ?")
            params.append(f"%{search}%")
        
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)
        
        if end_date:
            # Append time to include full day (dates come as YYYY-MM-DD)
            if len(end_date) == 10:  # YYYY-MM-DD format
                end_date = f"{end_date}T23:59:59.999999Z"
            conditions.append("created_at <= ?")
            params.append(end_date)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Validate sort field
        allowed_sorts = {'created_at', 'completed_at', 'size_bytes', 'bytes_transferred', 'torrent_name'}
        if sort not in allowed_sorts:
            sort = 'created_at'
        
        # Validate order
        order = 'DESC' if order.lower() == 'desc' else 'ASC'
        
        conn = self._get_connection()
        
        # Get total count
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM transfers WHERE {where_clause}",
            params
        )
        total = cursor.fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor = conn.execute(
            f"""
            SELECT * FROM transfers 
            WHERE {where_clause}
            ORDER BY {sort} {order}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        
        transfers = [dict(row) for row in cursor.fetchall()]
        
        return transfers, total
    
    def get_active_transfers(self) -> list[dict]:
        """Get all pending and transferring transfers.
        
        Returns:
            List of active transfer dicts
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM transfers 
            WHERE status IN ('pending', 'transferring')
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> dict:
        """Get aggregate statistics.
        
        Returns:
            Dict with total, completed, failed, success_rate, total_bytes
        """
        conn = self._get_connection()
        
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'transferring' THEN 1 ELSE 0 END) as transferring,
                SUM(CASE WHEN status = 'completed' THEN size_bytes ELSE 0 END) as total_bytes_transferred
            FROM transfers
        """)
        row = cursor.fetchone()
        
        total = row['total'] or 0
        completed = row['completed'] or 0
        failed = row['failed'] or 0
        
        # Calculate success rate (only count completed + failed, not pending/transferring)
        finished = completed + failed
        success_rate = (completed / finished * 100) if finished > 0 else 0
        
        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'pending': row['pending'] or 0,
            'transferring': row['transferring'] or 0,
            'success_rate': round(success_rate, 1),
            'total_bytes_transferred': row['total_bytes_transferred'] or 0
        }
    
    def prune_old_entries(self, retention_days: int):
        """Delete entries older than retention period.
        
        Args:
            retention_days: Number of days to retain records
        """
        if retention_days <= 0:
            # Delete all completed/failed transfers
            conn = self._get_connection()
            conn.execute(
                "DELETE FROM transfers WHERE status IN ('completed', 'failed', 'cancelled')"
            )
            conn.commit()
            return
        
        from datetime import timedelta
        cutoff = (_utc_now() - timedelta(days=retention_days)).isoformat()
        
        conn = self._get_connection()
        conn.execute(
            """
            DELETE FROM transfers 
            WHERE completed_at < ? 
            AND status IN ('completed', 'failed', 'cancelled')
            """,
            (cutoff,)
        )
        conn.commit()
    
    def delete_transfer(self, transfer_id: str) -> bool:
        """Delete a single transfer record.
        
        Args:
            transfer_id: UUID of the transfer to delete
            
        Returns:
            True if a record was deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "DELETE FROM transfers WHERE id = ?",
            (transfer_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    
    def clear_history(self, status: Optional[str] = None) -> int:
        """Clear transfer history records.
        
        Args:
            status: If provided, only delete records with this status.
                   If None, deletes all completed/failed/cancelled records.
                   
        Returns:
            Number of records deleted
        """
        conn = self._get_connection()
        
        if status:
            cursor = conn.execute(
                "DELETE FROM transfers WHERE status = ?",
                (status,)
            )
        else:
            # Don't delete pending/transferring - only finished records
            cursor = conn.execute(
                "DELETE FROM transfers WHERE status IN ('completed', 'failed', 'cancelled')"
            )
        
        conn.commit()
        return cursor.rowcount
    
    def close(self):
        """Close database connection for current thread."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
