"""
Fixtures for tests/ui/fast/ — lightweight UI tests that assume transferarr
is already running.

Most test files in this directory are passive: they only interact via the
browser and don't manage the Docker container themselves.  A prior test
suite (e.g. tests/ui/e2e/) may leave the container stopped after its
teardown, so we provide a package-level fixture that ensures the container
is healthy before any fast test runs.
"""
import time

import docker
import pytest
import requests

from tests.ui.helpers import TRANSFERARR_BASE_URL


@pytest.fixture(scope="session", autouse=True)
def _ensure_transferarr_running():
    """Start the transferarr container if it isn't already running.

    Session-scoped and autouse so it fires once before any test in
    tests/ui/fast/.  The fixture is intentionally light: it only starts
    the container and waits for the health endpoint — it does NOT stop
    it on teardown so that later test modules can keep using it.
    """
    # Quick check — if the health endpoint responds we're done.
    try:
        resp = requests.get(f"{TRANSFERARR_BASE_URL}/api/v1/health", timeout=5)
        if resp.status_code == 200:
            return
    except requests.RequestException:
        pass

    # Container is unreachable — start it via Docker SDK.
    client = docker.from_env()
    container_name = "test-transferarr"
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            container.start()
    except docker.errors.NotFound:
        pytest.fail(
            f"Container '{container_name}' does not exist. "
            "Start the test environment first: docker compose up -d"
        )

    # Wait for the health endpoint.
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            resp = requests.get(
                f"{TRANSFERARR_BASE_URL}/api/v1/health", timeout=5
            )
            if resp.status_code == 200:
                # Disable auth so passive UI tests can reach all pages.
                try:
                    requests.put(
                        f"{TRANSFERARR_BASE_URL}/api/v1/auth/settings",
                        json={"enabled": False, "session_timeout_minutes": 60},
                        timeout=10,
                    )
                except requests.RequestException:
                    pass
                return
        except requests.RequestException:
            pass
        time.sleep(2)

    pytest.fail("Transferarr did not become healthy within 60 seconds")
