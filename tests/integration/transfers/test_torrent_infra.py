"""Integration tests for torrent-based transfer infrastructure.

Tests that the Docker environment is correctly configured for torrent transfers:
- Tracker starts and listens on configured port
- Deluge containers have BitTorrent ports exposed
- Containers can communicate over BitTorrent protocol
- Config fixtures load correctly
"""

import os
import pytest
import requests
import socket


# Environment variables for service hosts
TRACKER_HOST = os.environ.get("TRACKER_HOST", "localhost")
TRACKER_PORT = int(os.environ.get("TRACKER_PORT", "16969"))

# For RPC/API connections (use env vars set by docker-compose)
DELUGE_SOURCE_HOST = os.environ.get("DELUGE_SOURCE_HOST", "localhost")
DELUGE_TARGET_HOST = os.environ.get("DELUGE_TARGET_HOST", "localhost")

# BitTorrent ports - internal container port is always 6881
# When testing from within Docker network, we connect to container:6881
# When testing from host, we use mapped ports 16881/16882
DELUGE_SOURCE_BT_PORT = 6881  # Internal port (or 16881 when from host)
DELUGE_TARGET_BT_PORT = 6881  # Internal port (or 16882 when from host)

# Transferarr API for config tests
TRANSFERARR_HOST = os.environ.get("TRANSFERARR_HOST", "localhost")
TRANSFERARR_PORT = int(os.environ.get("TRANSFERARR_PORT", "10445"))


class TestTrackerInfrastructure:
    """Tests for the BitTorrent tracker infrastructure."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_tracker_port_accessible(self, transferarr):
        """Tracker listens on configured port."""
        # Start transferarr with torrent transfer config to enable tracker
        transferarr.start(config_type="torrent-transfer", wait_healthy=True)
        
        # The tracker should be accessible via HTTP
        # Try a basic HTTP request (tracker responds to /announce)
        try:
            response = requests.get(
                f"http://{TRACKER_HOST}:{TRACKER_PORT}/announce",
                params={
                    "info_hash": "X" * 20,  # Fake info_hash
                    "peer_id": "Y" * 20,
                    "port": "6881",
                    "uploaded": "0",
                    "downloaded": "0",
                    "left": "0",
                },
                timeout=5
            )
            # Tracker should respond (even with an error for unregistered hash)
            assert response.status_code == 200
            # Response should be bencoded
            assert response.content.startswith(b"d")
        except requests.exceptions.ConnectionError:
            pytest.fail(f"Cannot connect to tracker at {TRACKER_HOST}:{TRACKER_PORT}")

    def test_tracker_rejects_unregistered_hash(self, transferarr):
        """Tracker returns failure for unregistered info_hash."""
        transferarr.start(config_type="torrent-transfer", wait_healthy=True)
        
        response = requests.get(
            f"http://{TRACKER_HOST}:{TRACKER_PORT}/announce",
            params={
                "info_hash": "UNREGISTEREDTORRENT",  # Not in whitelist
                "peer_id": "TEST" + "-" * 16,
                "port": "6881",
                "uploaded": "0",
                "downloaded": "0",
                "left": "100",
            },
            timeout=5
        )
        
        assert response.status_code == 200
        # Should return bencoded error response
        content = response.content.decode("latin-1")
        assert "failure reason" in content or b"14:failure reason" in response.content


class TestDelugeBitTorrentPorts:
    """Tests that Deluge containers have BitTorrent ports configured."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_source_deluge_bittorrent_port_listening(self, docker_services):
        """Source Deluge has BitTorrent port 6881 listening."""
        # Try to connect to the BitTorrent port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            result = sock.connect_ex((DELUGE_SOURCE_HOST, DELUGE_SOURCE_BT_PORT))
            # 0 = success (port is open)
            assert result == 0, f"Cannot connect to source Deluge BT port {DELUGE_SOURCE_BT_PORT}"
        finally:
            sock.close()

    def test_target_deluge_bittorrent_port_listening(self, docker_services):
        """Target Deluge has BitTorrent port 6881 listening."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            result = sock.connect_ex((DELUGE_TARGET_HOST, DELUGE_TARGET_BT_PORT))
            assert result == 0, f"Cannot connect to target Deluge BT port {DELUGE_TARGET_BT_PORT}"
        finally:
            sock.close()


class TestTorrentTransferConfig:
    """Tests for torrent transfer configuration loading."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_torrent_transfer_config_loads(self, transferarr):
        """Config fixture with torrent transfer loads correctly."""
        transferarr.start(config_type="torrent-transfer", wait_healthy=True)
        
        # Check health endpoint
        response = requests.get(
            f"http://{TRANSFERARR_HOST}:{TRANSFERARR_PORT}/api/v1/health",
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json()
        # Handle data envelope
        health = data.get("data", data)
        assert health.get("status") == "healthy"

    @pytest.mark.skip(reason="Tracker config API not yet implemented - Phase 5")
    def test_config_has_tracker_settings(self, transferarr):
        """Config includes tracker configuration."""
        transferarr.start(config_type="torrent-transfer", wait_healthy=True)
        
        response = requests.get(
            f"http://{TRANSFERARR_HOST}:{TRANSFERARR_PORT}/api/v1/config",
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json().get("data", {})
        config = data.get("config", {})
        
        # Tracker config should be present
        tracker = config.get("tracker", {})
        assert tracker.get("enabled") is True
        assert tracker.get("port") == 6969
        assert "announce" in tracker.get("external_url", "")

    @pytest.mark.skip(reason="Torrent connection type not yet implemented - Phase 5")
    def test_config_has_torrent_connection(self, transferarr):
        """Config includes torrent-type connection."""
        transferarr.start(config_type="torrent-transfer", wait_healthy=True)
        
        response = requests.get(
            f"http://{TRANSFERARR_HOST}:{TRANSFERARR_PORT}/api/v1/config",
            timeout=10
        )
        assert response.status_code == 200
        
        data = response.json().get("data", {})
        config = data.get("config", {})
        
        # Check connections
        connections = config.get("connections", [])
        assert len(connections) >= 1
        
        # Find torrent connection
        torrent_conn = None
        for conn in connections:
            transfer_config = conn.get("transfer_config", {})
            if transfer_config.get("type") == "torrent":
                torrent_conn = conn
                break
        
        assert torrent_conn is not None, "No torrent-type connection found"
        assert torrent_conn.get("from") == "source-deluge"
        assert torrent_conn.get("to") == "target-deluge"


class TestDelugeContainerConnectivity:
    """Tests that Deluge containers can communicate over the network."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_deluge_containers_on_same_network(self, deluge_source, deluge_target):
        """Both Deluge containers are healthy and on the test network."""
        # If we got here, the fixtures connected successfully
        # Verify basic RPC works
        source_version = deluge_source.core.get_libtorrent_version()
        target_version = deluge_target.core.get_libtorrent_version()
        
        assert source_version is not None
        assert target_version is not None

    def test_deluge_containers_have_fixed_listen_port(self, deluge_source, deluge_target):
        """Deluge containers have fixed listen ports (not random)."""
        # Get config from each client
        source_ports = deluge_source.core.get_config_value("listen_ports")
        target_ports = deluge_target.core.get_config_value("listen_ports")
        
        # Should be fixed to [6881, 6881] based on core.conf
        # Note: Deluge may return as list or tuple
        assert list(source_ports) == [6881, 6881], f"Source ports: {source_ports}"
        assert list(target_ports) == [6881, 6881], f"Target ports: {target_ports}"

    def test_deluge_random_port_disabled(self, deluge_source, deluge_target):
        """Random port selection is disabled."""
        source_random = deluge_source.core.get_config_value("random_port")
        target_random = deluge_target.core.get_config_value("random_port")
        
        assert source_random is False
        assert target_random is False
