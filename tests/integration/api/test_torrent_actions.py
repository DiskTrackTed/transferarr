"""Integration tests for torrent action endpoints (retry, remove)."""
import base64
import json

import pytest
import requests
from tests.conftest import SERVICES, TIMEOUTS
from tests.utils import (
    movie_catalog,
    make_torrent_name,
    wait_for_queue_item_by_hash,
    wait_for_torrent_in_deluge,
    wait_for_transferarr_state,
    find_torrent_in_transferarr,
)


STATE_VOLUME = "transferarr_test_transferarr-state"


def get_api_url():
    host = SERVICES['transferarr']['host']
    port = SERVICES['transferarr']['port']
    return f"http://{host}:{port}/api/v1"


def write_state_file(transferarr, state_data):
    """Write state.json directly to the transferarr Docker volume."""
    state_json = json.dumps(state_data)
    encoded = base64.b64encode(state_json.encode("utf-8")).decode("ascii")

    transferarr.docker.containers.run(
        "alpine:latest",
        f'sh -c "echo {encoded} | base64 -d > /state/state.json"',
        volumes={STATE_VOLUME: {"bind": "/state", "mode": "rw"}},
        remove=True,
    )


def build_persisted_torrent(torrent_hash: str, name: str, state: str) -> dict:
    """Build a minimal persisted torrent entry for state-file setup."""
    return {
        "name": name,
        "id": torrent_hash,
        "state": state,
        "home_client_name": "source-deluge",
        "home_client_info": {},
        "target_client_name": "target-deluge",
        "target_client_info": {},
    }


def seed_state_file_with_torrent(transferarr, torrent_hash: str, name: str, state: str):
    """Stop transferarr, seed state.json, and restart with the seeded torrent."""
    transferarr.stop()
    transferarr.clear_state()
    write_state_file(
        transferarr,
        [build_persisted_torrent(torrent_hash=torrent_hash, name=name, state=state)],
    )
    transferarr.start(wait_healthy=True)


def create_tracked_torrent_in_active_state(
    transferarr,
    create_torrent,
    radarr_client,
    deluge_source,
):
    """Create a real tracked torrent and wait for a stable non-failed state."""
    movie = movie_catalog.get_movie()
    torrent_name = make_torrent_name(movie["title"], movie["year"])

    torrent_info = create_torrent(torrent_name, size_mb=10)

    radarr_client.add_movie(
        title=movie["title"],
        tmdb_id=movie["tmdb_id"],
        year=movie["year"],
    )

    wait_for_queue_item_by_hash(radarr_client, torrent_info["hash"], timeout=60)
    wait_for_torrent_in_deluge(
        deluge_source,
        torrent_info["hash"],
        timeout=60,
        expected_state="Seeding",
    )

    transferarr.start(wait_healthy=True)
    tracked = wait_for_transferarr_state(
        transferarr,
        torrent_name,
        expected_state=["TARGET_CHECKING", "TARGET_SEEDING"],
        timeout=TIMEOUTS["torrent_transfer"],
    )
    return tracked


class TestRetryTransfer:
    """Tests for POST /api/v1/torrents/<hash>/retry endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_retry_not_found_returns_404(self, transferarr):
        """Retrying nonexistent hash returns 404."""
        transferarr.start(wait_healthy=True)
        url = f"{get_api_url()}/torrents/nonexistent123/retry"
        response = requests.post(url, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 404
        data = response.json()
        assert data['error']['code'] == 'NOT_FOUND'
        assert 'not found' in data['error']['message'].lower()

    def test_retry_wrong_state_returns_400(
        self,
        transferarr,
        create_torrent,
        radarr_client,
        deluge_source,
    ):
        """Retrying a tracked torrent in a non-failed state returns 400."""
        tracked = create_tracked_torrent_in_active_state(
            transferarr,
            create_torrent,
            radarr_client,
            deluge_source,
        )

        url = f"{get_api_url()}/torrents/{tracked['id']}/retry"
        response = requests.post(url, timeout=TIMEOUTS['api_response'])

        assert response.status_code == 400
        data = response.json()
        assert data['error']['code'] == 'INVALID_STATE'
        assert tracked['state'] in data['error']['message']
        assert 'not TRANSFER_FAILED' in data['error']['message']

    def test_retry_transfer_failed_returns_200(self, transferarr):
        """Retrying a TRANSFER_FAILED torrent returns 200 and resets state."""
        torrent_hash = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        torrent_name = "Retry.Success.Test"
        seed_state_file_with_torrent(
            transferarr,
            torrent_hash=torrent_hash,
            name=torrent_name,
            state="TRANSFER_FAILED",
        )

        url = f"{get_api_url()}/torrents/{torrent_hash}/retry"
        response = requests.post(url, timeout=TIMEOUTS['api_response'])

        assert response.status_code == 200
        data = response.json()
        assert data['data']['new_state'] == 'HOME_SEEDING'
        tracked = find_torrent_in_transferarr(transferarr, torrent_name)
        assert tracked is not None
        assert tracked['state'] == 'HOME_SEEDING'


class TestRemoveTransfer:
    """Tests for DELETE /api/v1/torrents/<hash> endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass

    def test_remove_not_found_returns_404(self, transferarr):
        """Removing nonexistent hash returns 404."""
        transferarr.start(wait_healthy=True)
        url = f"{get_api_url()}/torrents/nonexistent123"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])
        assert response.status_code == 404
        data = response.json()
        assert data['error']['code'] == 'NOT_FOUND'
        assert 'not found' in data['error']['message'].lower()

    def test_remove_wrong_state_returns_400(
        self,
        transferarr,
        create_torrent,
        radarr_client,
        deluge_source,
    ):
        """Removing a tracked torrent in a non-failed state returns 400."""
        tracked = create_tracked_torrent_in_active_state(
            transferarr,
            create_torrent,
            radarr_client,
            deluge_source,
        )

        url = f"{get_api_url()}/torrents/{tracked['id']}"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])

        assert response.status_code == 400
        data = response.json()
        assert data['error']['code'] == 'INVALID_STATE'
        assert tracked['state'] in data['error']['message']
        assert 'not TRANSFER_FAILED' in data['error']['message']

    def test_remove_transfer_failed_returns_200(self, transferarr):
        """Removing a TRANSFER_FAILED torrent returns 200 and untracks it."""
        torrent_hash = "cafebabecafebabecafebabecafebabecafebabe"
        torrent_name = "Remove.Success.Test"
        seed_state_file_with_torrent(
            transferarr,
            torrent_hash=torrent_hash,
            name=torrent_name,
            state="TRANSFER_FAILED",
        )

        url = f"{get_api_url()}/torrents/{torrent_hash}"
        response = requests.delete(url, timeout=TIMEOUTS['api_response'])

        assert response.status_code == 200
        data = response.json()
        assert torrent_name in data['data']['message']
        assert find_torrent_in_transferarr(transferarr, torrent_name) is None
