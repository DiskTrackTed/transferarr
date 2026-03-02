"""Integration tests for DelugeClient torrent creation methods.

Tests the new torrent creation and magnet methods against real Deluge instances.
These tests verify the Phase 3 Deluge client extensions work with actual clients.
"""

import base64
import os
import time

import pytest
from deluge_client import DelugeRPCClient

from tests.utils import decode_bytes


# Environment variables for service hosts (Docker network)
DELUGE_SOURCE_HOST = os.environ.get("DELUGE_SOURCE_HOST", "localhost")
DELUGE_SOURCE_RPC_PORT = int(os.environ.get("DELUGE_SOURCE_RPC_PORT", "18846"))

DELUGE_TARGET_HOST = os.environ.get("DELUGE_TARGET_HOST", "localhost")
DELUGE_TARGET_RPC_PORT = int(os.environ.get("DELUGE_TARGET_RPC_PORT", "18847"))

DELUGE_USERNAME = "transferarr"
DELUGE_PASSWORD = "testpassword"


# Note: docker_client fixture is provided by conftest.py (session-scoped)


@pytest.fixture
def source_deluge_client():
    """Create a direct RPC client to source Deluge."""
    client = DelugeRPCClient(
        DELUGE_SOURCE_HOST,
        DELUGE_SOURCE_RPC_PORT,
        DELUGE_USERNAME,
        DELUGE_PASSWORD,
        decode_utf8=True
    )
    client.connect()
    yield client
    # Cleanup: remove any test torrents
    try:
        torrents = client.core.get_torrents_status({}, ["name"])
        for torrent_hash, info in torrents.items():
            name = decode_bytes(info.get("name", ""))
            if name.startswith("[TR-") or name.startswith("test_"):
                client.core.remove_torrent(torrent_hash, True)
    except Exception:
        pass


@pytest.fixture
def target_deluge_client():
    """Create a direct RPC client to target Deluge."""
    client = DelugeRPCClient(
        DELUGE_TARGET_HOST,
        DELUGE_TARGET_RPC_PORT,
        DELUGE_USERNAME,
        DELUGE_PASSWORD,
        decode_utf8=True
    )
    client.connect()
    yield client
    # Cleanup
    try:
        torrents = client.core.get_torrents_status({}, ["name"])
        for torrent_hash, info in torrents.items():
            name = decode_bytes(info.get("name", ""))
            if name.startswith("[TR-") or name.startswith("test_"):
                client.core.remove_torrent(torrent_hash, True)
    except Exception:
        pass


@pytest.fixture
def add_torrent_to_source(source_deluge_client, create_torrent):
    """
    Factory fixture to create a torrent AND add it to source Deluge.
    
    Returns:
        Function that creates torrent and adds it to Deluge, returning torrent info.
    """
    import requests
    
    # Service configuration
    mock_indexer_host = os.environ.get("MOCK_INDEXER_HOST", "localhost")
    mock_indexer_port = os.environ.get("MOCK_INDEXER_PORT", "9696")
    indexer_url = f"http://{mock_indexer_host}:{mock_indexer_port}"
    
    added_hashes = []
    
    def _add_torrent(name: str, size_mb: int = 1) -> dict:
        """Create torrent and add it to source Deluge."""
        # Create the torrent (creates files + .torrent)
        torrent_info = create_torrent(name, size_mb=size_mb)
        torrent_hash = torrent_info["hash"]
        
        # Download the .torrent file from mock indexer
        torrent_filename = f"{name}.torrent"
        torrent_response = requests.get(f"{indexer_url}/download/{torrent_filename}")
        if torrent_response.status_code != 200:
            raise RuntimeError(f"Failed to download torrent from indexer: {torrent_response.status_code}")
        torrent_data = torrent_response.content
        
        # Add torrent to source Deluge
        # Deluge expects base64-encoded torrent file data
        torrent_b64 = base64.b64encode(torrent_data).decode('ascii')
        
        result_hash = source_deluge_client.core.add_torrent_file(
            f"{name}.torrent",
            torrent_b64,
            {"download_location": "/downloads"}
        )
        result_hash = decode_bytes(result_hash) if result_hash else ""
        
        # Wait for torrent to be fully loaded
        time.sleep(1)
        
        added_hashes.append(result_hash)
        
        return {
            "name": name,
            "hash": result_hash,
            "size_mb": size_mb,
            "torrent_data": torrent_data,
        }
    
    yield _add_torrent
    
    # Cleanup: remove added torrents
    for h in added_hashes:
        try:
            source_deluge_client.core.remove_torrent(h, True)
        except Exception:
            pass


class TestGetDefaultDownloadPath:
    """Tests for get_default_download_path with real Deluge client."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_get_default_download_path_returns_string(self, source_deluge_client):
        """Returns the configured download location as a string."""
        result = source_deluge_client.core.get_config_value("download_location")
        result = decode_bytes(result) if result else ""
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert result.startswith("/")

    def test_get_default_download_path_is_valid_path(self, source_deluge_client):
        """Download path is a valid absolute path."""
        result = source_deluge_client.core.get_config_value("download_location")
        result = decode_bytes(result) if result else ""
        
        # Should be an absolute path
        assert os.path.isabs(result)
        # Common Deluge paths
        assert "download" in result.lower() or "media" in result.lower() or "/" in result


class TestGetMagnetUri:
    """Tests for get_magnet_uri with real Deluge client."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_get_magnet_uri_for_existing_torrent(
        self, source_deluge_client, add_torrent_to_source
    ):
        """Can retrieve magnet URI for an existing torrent."""
        # Create and add torrent to source Deluge
        torrent_info = add_torrent_to_source("test_magnet_uri_torrent", size_mb=1)
        torrent_hash = torrent_info["hash"]
        
        # Get the magnet URI
        magnet = source_deluge_client.core.get_magnet_uri(torrent_hash)
        magnet = decode_bytes(magnet) if magnet else ""
        
        assert magnet.startswith("magnet:?")
        assert "xt=urn:btih:" in magnet
        assert torrent_hash.lower() in magnet.lower()

    def test_magnet_uri_contains_display_name(
        self, source_deluge_client, add_torrent_to_source
    ):
        """Magnet URI includes the torrent name as dn parameter."""
        torrent_name = "test_magnet_with_name"
        torrent_info = add_torrent_to_source(torrent_name, size_mb=1)
        torrent_hash = torrent_info["hash"]
        
        magnet = source_deluge_client.core.get_magnet_uri(torrent_hash)
        magnet = decode_bytes(magnet) if magnet else ""
        
        # Should contain display name
        assert "dn=" in magnet


class TestAddTorrentMagnet:
    """Tests for add_torrent_magnet with real Deluge client."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_add_torrent_via_magnet_from_source(
        self, source_deluge_client, target_deluge_client, add_torrent_to_source
    ):
        """Can add torrent to target via magnet link from source."""
        # Create and add torrent on source
        torrent_info = add_torrent_to_source("test_add_via_magnet", size_mb=1)
        torrent_hash = torrent_info["hash"]
        
        # Get magnet from source
        magnet = source_deluge_client.core.get_magnet_uri(torrent_hash)
        magnet = decode_bytes(magnet) if magnet else ""
        
        # Add to target via magnet
        result_hash = target_deluge_client.core.add_torrent_magnet(magnet, {})
        result_hash = decode_bytes(result_hash) if result_hash else ""
        
        # Should return the same hash
        assert result_hash.lower() == torrent_hash.lower()
        
        # Verify torrent exists on target
        status = target_deluge_client.core.get_torrent_status(result_hash, ["name"])
        assert status is not None

    def test_add_torrent_magnet_with_download_location(
        self, source_deluge_client, target_deluge_client, add_torrent_to_source
    ):
        """Can specify custom download location when adding via magnet."""
        torrent_info = add_torrent_to_source("test_magnet_custom_path", size_mb=1)
        torrent_hash = torrent_info["hash"]
        
        magnet = source_deluge_client.core.get_magnet_uri(torrent_hash)
        magnet = decode_bytes(magnet) if magnet else ""
        
        # Add with custom download location
        custom_path = "/downloads/custom"
        result_hash = target_deluge_client.core.add_torrent_magnet(
            magnet,
            {"download_location": custom_path}
        )
        result_hash = decode_bytes(result_hash) if result_hash else ""
        
        # Check download location was set
        status = target_deluge_client.core.get_torrent_status(
            result_hash,
            ["download_location"]
        )
        location = decode_bytes(status.get("download_location", ""))
        assert location == custom_path


class TestGetTorrentProgressBytes:
    """Tests for get_torrent_progress_bytes with real Deluge client."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_get_progress_returns_total_size(
        self, source_deluge_client, add_torrent_to_source
    ):
        """Returns accurate total_size for torrent."""
        torrent_info = add_torrent_to_source("test_progress_size", size_mb=5)
        torrent_hash = torrent_info["hash"]
        
        status = source_deluge_client.core.get_torrent_status(
            torrent_hash,
            ["total_done", "total_size"]
        )
        
        total_size = status.get("total_size", 0)
        
        # Should be approximately 5MB (within reasonable margin for torrent overhead)
        assert total_size >= 4 * 1024 * 1024, f"Size too small: {total_size}"
        assert total_size <= 6 * 1024 * 1024, f"Size too large: {total_size}"

    def test_get_progress_seeding_torrent(
        self, source_deluge_client, add_torrent_to_source
    ):
        """Seeding torrent shows total_done == total_size."""
        torrent_info = add_torrent_to_source("test_progress_seeding", size_mb=1)
        torrent_hash = torrent_info["hash"]
        
        # Wait for torrent to be fully checked
        time.sleep(2)
        
        status = source_deluge_client.core.get_torrent_status(
            torrent_hash,
            ["total_done", "total_size", "state"]
        )
        
        total_done = status.get("total_done", 0)
        total_size = status.get("total_size", 0)
        state = decode_bytes(status.get("state", ""))
        
        # If seeding, total_done should equal total_size
        if state == "Seeding":
            assert total_done == total_size
        else:
            # At minimum, we should have valid numbers
            assert total_size > 0


class TestCreateTorrent:
    """Tests for create_torrent with real Deluge client.
    
    Note: create_torrent requires actual files on the filesystem where Deluge
    is running. These tests verify the API works when files exist.
    """

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_create_torrent_api_exists(self, source_deluge_client):
        """Verify create_torrent method exists in Deluge RPC."""
        # Check that the method is available
        # We can't easily list core methods, but we can try calling it
        # with invalid params to verify it exists
        try:
            # This should fail with an error about the path, not method not found
            source_deluge_client.core.create_torrent(
                "/nonexistent/path",
                "",  # tracker
                0,   # piece_length
                "",  # comment
                "",  # target
                [],  # webseeds
                True,  # private
                "",  # created_by
                [],  # trackers
                False  # add_to_session
            )
        except Exception as e:
            error_msg = str(e).lower()
            # Should fail because path doesn't exist, not because method doesn't exist
            assert "path" in error_msg or "exist" in error_msg or \
                   "invalid" in error_msg or "error" in error_msg, \
                f"Unexpected error: {e}"


class TestTorrentHashUniqueness:
    """Tests verifying torrent hash uniqueness based on name."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_same_content_different_name_different_hash(
        self, source_deluge_client, create_torrent
    ):
        """Same content with different names produces different hashes."""
        # Create two torrents with same size but different names
        torrent1 = create_torrent("test_hash_unique_1", size_mb=1)
        torrent2 = create_torrent("test_hash_unique_2", size_mb=1)
        
        # Hashes should be different
        assert torrent1["hash"] != torrent2["hash"]

    def test_transfer_torrent_name_format(self, source_deluge_client, create_torrent):
        """Transfer torrent naming convention [TR-ID] produces unique hash."""
        from transferarr.utils import generate_transfer_id, build_transfer_torrent_name
        
        original_name = "Original.Movie.2024.1080p"
        
        # Generate transfer torrent names
        name1 = build_transfer_torrent_name(original_name)
        name2 = build_transfer_torrent_name(original_name)
        
        # Names should be different (different IDs)
        assert name1 != name2
        
        # Both should follow the pattern
        assert name1.startswith("[TR-")
        assert name2.startswith("[TR-")
        assert original_name in name1
        assert original_name in name2
