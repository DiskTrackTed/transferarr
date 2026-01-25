"""Integration tests for secret key generation and persistence."""
import os
import time

import pytest

from tests.utils import wait_for_condition


class TestSecretKey:
    """Tests for secret key generation and persistence in Docker environment."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    @pytest.mark.timeout(120)
    def test_secret_key_created_on_first_start(self, transferarr, docker_services):
        """Secret key file is created in state_dir on first start."""
        # Start transferarr (this will create the secret key)
        transferarr.start(wait_healthy=True)
        
        # Check that secret_key file exists in the container's state directory
        result = transferarr.exec_in_container(["ls", "-la", "/state/secret_key"])
        assert "secret_key" in result, "secret_key file should exist in /state"
        
        # Verify file has content (32 bytes) - use stat to get file size
        result = transferarr.exec_in_container(["stat", "-c", "%s", "/state/secret_key"])
        size = int(result.strip())
        assert size == 32, f"secret_key should be 32 bytes, got {size}"

    @pytest.mark.timeout(180)
    def test_secret_key_persists_across_restarts(self, transferarr, docker_services):
        """Same secret key is used after container restart."""
        # Start transferarr
        transferarr.start(wait_healthy=True)
        
        # Get the secret key content as hex using od (more portable than xxd)
        key1 = transferarr.exec_in_container(["od", "-A", "n", "-t", "x1", "/state/secret_key"])
        key1 = key1.strip().replace(" ", "").replace("\n", "")
        
        # Restart the container
        transferarr.restart()
        
        # Get the secret key again
        key2 = transferarr.exec_in_container(["od", "-A", "n", "-t", "x1", "/state/secret_key"])
        key2 = key2.strip().replace(" ", "").replace("\n", "")
        
        # Keys should be identical
        assert key1 == key2, "Secret key should persist across restarts"

    @pytest.mark.timeout(180)
    def test_secret_key_deletion_generates_new(self, transferarr, docker_services):
        """New secret key is generated if file is deleted."""
        # Start transferarr
        transferarr.start(wait_healthy=True)
        
        # Get the original secret key as hex
        key1 = transferarr.exec_in_container(["od", "-A", "n", "-t", "x1", "/state/secret_key"])
        key1 = key1.strip().replace(" ", "").replace("\n", "")
        
        # Stop container, delete secret key, restart
        transferarr.stop()
        transferarr.exec_in_container(["rm", "/state/secret_key"], running=False)
        transferarr.start(wait_healthy=True)
        
        # Get the new secret key
        key2 = transferarr.exec_in_container(["od", "-A", "n", "-t", "x1", "/state/secret_key"])
        key2 = key2.strip().replace(" ", "").replace("\n", "")
        
        # Keys should be different (new random key generated)
        assert key1 != key2, "New secret key should be generated after deletion"
        
        # New key should still be 32 bytes
        result = transferarr.exec_in_container(["stat", "-c", "%s", "/state/secret_key"])
        size = int(result.strip())
        assert size == 32, f"New secret_key should be 32 bytes, got {size}"

    @pytest.mark.timeout(180)
    def test_session_invalid_after_key_change(self, transferarr, docker_services):
        """Sessions are invalidated when secret key changes.
        
        Note: This test requires auth to be fully implemented.
        It will be enabled after Phase 3 (auth routes) is complete.
        """
        pytest.skip("Requires auth routes to be implemented (Phase 3)")
