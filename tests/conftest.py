"""
Pytest configuration and fixtures for Transferarr integration tests.

Run tests using the test runner:
    ./run_tests.sh tests/integration/ -v
"""
import os
import pytest
import docker
import requests
import time
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from deluge_client import DelugeRPCClient

# ==============================================================================
# Constants
# ==============================================================================

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DOCKER_DIR = PROJECT_ROOT / "docker"
COMPOSE_FILE = DOCKER_DIR / "docker-compose.test.yml"
FIXTURES_DIR = DOCKER_DIR / "fixtures"

# Transfer type config files (base configs)
TRANSFER_TYPE_CONFIGS = {
    'sftp-to-local': FIXTURES_DIR / "config.sftp-to-local.json",
    'local-to-sftp': FIXTURES_DIR / "config.local-to-sftp.json",
    'sftp-to-sftp': FIXTURES_DIR / "config.sftp-to-sftp.json",
    'local-to-local': FIXTURES_DIR / "config.local-to-local.json",
    'multi-target': FIXTURES_DIR / "config.multi-target.json",
}

# History config overrides (merged with base config)
HISTORY_CONFIGS = {
    'disabled': FIXTURES_DIR / "history.disabled.json",
    'no-progress': FIXTURES_DIR / "history.no-progress.json",
}

# Timeouts (seconds)
TIMEOUTS = {
    'service_startup': 120,      # 2 minutes for all services to be healthy
    'torrent_transfer': 300,     # 5 minutes for file transfer
    'state_transition': 120,     # 2 minutes for state machine transitions
    'api_response': 30,          # 30 seconds for API calls
    'api_response_slow': 90,     # 90 seconds for slow API calls (adding series/movies fetches metadata)
    'torrent_seeding': 60,       # 1 minute for torrent to start seeding
}

# Service URLs - Docker container hostnames (tests run inside Docker network)
SERVICES = {
    'radarr': {
        'host': os.environ.get('RADARR_HOST', 'radarr'),
        'port': int(os.environ.get('RADARR_PORT', '7878')),
    },
    'sonarr': {
        'host': os.environ.get('SONARR_HOST', 'sonarr'),
        'port': int(os.environ.get('SONARR_PORT', '8989')),
    },
    'mock_indexer': {
        'host': os.environ.get('MOCK_INDEXER_HOST', 'mock-indexer'),
        'port': int(os.environ.get('MOCK_INDEXER_PORT', '9696')),
    },
    'deluge_source': {
        'host': os.environ.get('DELUGE_SOURCE_HOST', 'deluge-source'),
        'rpc_port': int(os.environ.get('DELUGE_SOURCE_RPC_PORT', '58846')),
        'web_port': int(os.environ.get('DELUGE_SOURCE_WEB_PORT', '8112')),
    },
    'deluge_target': {
        'host': os.environ.get('DELUGE_TARGET_HOST', 'deluge-target'),
        'rpc_port': int(os.environ.get('DELUGE_TARGET_RPC_PORT', '58846')),
        'web_port': int(os.environ.get('DELUGE_TARGET_WEB_PORT', '8112')),
    },
    'deluge_target_2': {
        'host': os.environ.get('DELUGE_TARGET_2_HOST', 'deluge-target-2'),
        'rpc_port': int(os.environ.get('DELUGE_TARGET_2_RPC_PORT', '58846')),
        'web_port': int(os.environ.get('DELUGE_TARGET_2_WEB_PORT', '8112')),
    },
    'transferarr': {
        'host': os.environ.get('TRANSFERARR_HOST', 'transferarr'),
        'port': int(os.environ.get('TRANSFERARR_PORT', '10444')),
    },
}

# Config files are mounted directly in the Docker test container
RADARR_CONFIG_PATH = Path('/radarr-config/config.xml')
SONARR_CONFIG_PATH = Path('/sonarr-config/config.xml')

# Credentials
DELUGE_PASSWORD = "testpassword"
DELUGE_USERNAME = "localclient"
DELUGE_RPC_USERNAME = "transferarr"  # Separate RPC user (used by UI tests)


# ==============================================================================
# Helper Functions
# ==============================================================================

def _extract_api_key(docker_client, container_name: str, config_path: Path | None, service_name: str) -> str:
    """
    Extract API key from a *arr service's config.xml.
    
    Args:
        docker_client: Docker client instance
        container_name: Name of the container (e.g., 'test-radarr')
        config_path: Path to config.xml when running in Docker
        service_name: Human-readable service name for error messages
    
    Returns:
        The API key string
    
    Raises:
        pytest.fail: If config cannot be read or API key not found
    """
    if config_path and config_path.exists():
        # Read from mounted volume
        config_content = config_path.read_text()
    else:
        # Fall back to docker exec if path not mounted
        container = docker_client.containers.get(container_name)
        result = container.exec_run("cat /config/config.xml")
        if result.exit_code != 0:
            pytest.fail(f"Failed to read {service_name} config.xml")
        config_content = result.output.decode()
    
    root = ET.fromstring(config_content)
    api_key = root.find('ApiKey')
    if api_key is None or not api_key.text:
        pytest.fail(f"Could not find ApiKey in {service_name} config")
    
    return api_key.text


def _register_mock_indexer(api_key: str, host: str, port: int, categories: list, service_name: str) -> bool:
    """
    Register the mock indexer with a *arr service.
    
    Args:
        api_key: API key for the service
        host: Service hostname
        port: Service port
        categories: List of Torznab category IDs (2xxx for movies, 5xxx for TV)
        service_name: Human-readable service name for error messages
    
    Returns:
        True if indexer is registered (or was already registered)
    """
    base_url = f"http://{host}:{port}/api/v3"
    headers = {"X-Api-Key": api_key}
    
    # Check if indexer already exists
    resp = requests.get(f"{base_url}/indexer", headers=headers, timeout=30)
    resp.raise_for_status()
    indexers = resp.json()
    
    for indexer in indexers:
        if indexer.get('name') == 'mock-indexer':
            return True  # Already registered
    
    # Register the mock indexer
    indexer_config = {
        "enableRss": True,
        "enableAutomaticSearch": True,
        "enableInteractiveSearch": True,
        "priority": 25,
        "name": "mock-indexer",
        "fields": [
            {"name": "baseUrl", "value": "http://mock-indexer:9696"},
            {"name": "apiPath", "value": "/api"},
            {"name": "apiKey", "value": ""},
            {"name": "categories", "value": categories},
            {"name": "minimumSeeders", "value": 0},
        ],
        "implementationName": "Torznab",
        "implementation": "Torznab",
        "configContract": "TorznabSettings",
        "tags": [],
    }
    
    resp = requests.post(
        f"{base_url}/indexer",
        headers={**headers, "Content-Type": "application/json"},
        json=indexer_config,
        timeout=30
    )
    
    if resp.status_code not in (200, 201):
        print(f"Warning: Could not register {service_name} indexer: {resp.status_code} {resp.text}")
    
    return True


# ==============================================================================
# Docker Client Fixture
# ==============================================================================

@pytest.fixture(scope="session")
def docker_client():
    """Provide a Docker client for container management."""
    client = docker.from_env()
    yield client
    client.close()


# ==============================================================================
# Movie Catalog Fixture
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def reset_movie_catalog_session():
    """
    Reset the movie catalog once at the start of the test session.
    
    This ensures each test gets a unique movie and prevents
    collision issues where Radarr already has a movie added.
    The catalog is NOT reset between tests - each test gets 
    the next available movie.
    """
    from tests.utils import movie_catalog
    movie_catalog.reset()
    yield
    # Log how many movies were used
    print(f"\nMovies used in test session: {len(movie_catalog.used_movies)}")
    print(f"  Used: {movie_catalog.used_movies}")


# ==============================================================================
# Show Catalog Fixture
# ==============================================================================

@pytest.fixture(scope="session", autouse=True)
def reset_show_catalog_session():
    """
    Reset the show catalog once at the start of the test session.
    """
    from tests.utils import show_catalog
    show_catalog.reset()
    yield
    # Log how many shows were used
    print(f"\nShows used in test session: {len(show_catalog.used_keys)}")
    print(f"  Used: {show_catalog.used_keys}")


# ==============================================================================
# Service Health Check Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def docker_services(docker_client):
    """
    Ensure Docker test services are running and healthy.
    
    This fixture checks that all required services are up before tests run.
    It does NOT start the services - they should be started manually or via CI.
    """
    required_containers = [
        'test-tracker',
        'test-sftp',
        'test-deluge-source',
        'test-deluge-target',
        'test-radarr',
        'test-sonarr',
        'test-mock-indexer',
    ]
    
    # Check all containers are running
    running_containers = {c.name for c in docker_client.containers.list()}
    missing = set(required_containers) - running_containers
    
    if missing:
        pytest.skip(
            f"Required containers not running: {missing}. "
            f"Start with: docker compose -f docker/docker-compose.test.yml up -d"
        )
    
    # Wait for services to be healthy
    deadline = time.time() + TIMEOUTS['service_startup']
    while time.time() < deadline:
        all_healthy = True
        for name in required_containers:
            container = docker_client.containers.get(name)
            health = container.attrs.get('State', {}).get('Health', {})
            status = health.get('Status', 'none')
            if status not in ('healthy', 'none'):  # 'none' means no healthcheck defined
                all_healthy = False
                break
        if all_healthy:
            break
        time.sleep(2)
    else:
        pytest.fail("Services did not become healthy in time")
    
    return docker_client


# ==============================================================================
# API Key Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def radarr_api_key(docker_client, docker_services):
    """Extract Radarr API key from config.xml."""
    return _extract_api_key(docker_client, 'test-radarr', RADARR_CONFIG_PATH, 'Radarr')


@pytest.fixture(scope="session")
def ensure_indexer_registered(radarr_api_key, docker_client, docker_services):
    """
    Ensure the mock indexer is registered in Radarr before tests run.
    """
    # Create a dummy movie torrent to ensure indexer validation passes
    try:
        docker_client.containers.run(
            image="transferarr_test-torrent-creator",
            command=["--name", "Indexer.Validation.Movie", "--size", "1", "--force"],
            environment={
                "TRACKER_URL": "http://tracker:6969/announce",
                "CONTENT_DIR": "/downloads",
                "TORRENT_DIR": "/torrents",
            },
            volumes={
                "transferarr_test_source-downloads": {"bind": "/downloads", "mode": "rw"},
                "transferarr_test_test-torrents": {"bind": "/torrents", "mode": "rw"},
            },
            network="transferarr_test_test-network",
            remove=True,
        )
    except Exception as e:
        print(f"Warning: Failed to create dummy movie torrent: {e}")

    return _register_mock_indexer(
        radarr_api_key,
        SERVICES['radarr']['host'],
        SERVICES['radarr']['port'],
        categories=[2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060],
        service_name="Radarr"
    )


@pytest.fixture(scope="session")
def ensure_sonarr_indexer_registered(sonarr_api_key, docker_client, docker_services):
    """
    Ensure the mock indexer is registered in Sonarr before tests run.
    """
    # Create a dummy TV torrent to ensure indexer validation passes
    try:
        docker_client.containers.run(
            image="transferarr_test-torrent-creator",
            command=["--name", "Indexer.Validation.S01E01", "--size", "1", "--force"],
            environment={
                "TRACKER_URL": "http://tracker:6969/announce",
                "CONTENT_DIR": "/downloads",
                "TORRENT_DIR": "/torrents",
            },
            volumes={
                "transferarr_test_source-downloads": {"bind": "/downloads", "mode": "rw"},
                "transferarr_test_test-torrents": {"bind": "/torrents", "mode": "rw"},
            },
            network="transferarr_test_test-network",
            remove=True,
        )
    except Exception as e:
        print(f"Warning: Failed to create dummy TV torrent: {e}")

    return _register_mock_indexer(
        sonarr_api_key,
        SERVICES['sonarr']['host'],
        SERVICES['sonarr']['port'],
        categories=[5000, 5010, 5020, 5030, 5040, 5045, 5050, 5060],
        service_name="Sonarr"
    )


@pytest.fixture(scope="session")
def sonarr_api_key(docker_client, docker_services):
    """Extract Sonarr API key from config.xml."""
    return _extract_api_key(docker_client, 'test-sonarr', SONARR_CONFIG_PATH, 'Sonarr')


# ==============================================================================
# API Client Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def radarr_client(radarr_api_key, ensure_indexer_registered):
    """Provide a requests-based Radarr API client."""
    class RadarrClient:
        def __init__(self, host, port, api_key):
            self.base_url = f"http://{host}:{port}/api/v3"
            self.headers = {"X-Api-Key": api_key}
        
        def get(self, endpoint, **kwargs):
            return requests.get(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def post(self, endpoint, **kwargs):
            return requests.post(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def delete(self, endpoint, **kwargs):
            return requests.delete(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def get_queue(self):
            """Get current download queue."""
            resp = self.get("queue")
            resp.raise_for_status()
            return resp.json()
        
        def get_movies(self):
            """Get all movies in library."""
            resp = self.get("movie")
            resp.raise_for_status()
            return resp.json()
        
        def add_movie(self, title, tmdb_id, year, search=True):
            """Add a movie to the library."""
            payload = {
                "title": title,
                "qualityProfileId": 1,
                "tmdbId": tmdb_id,
                "year": year,
                "rootFolderPath": "/downloads/movies",
                "monitored": True,
                "addOptions": {"searchForMovie": search}
            }
            # Use slow timeout - adding movies fetches metadata from TMDB
            resp = requests.post(
                f"{self.base_url}/movie",
                headers=self.headers,
                json=payload,
                timeout=TIMEOUTS['api_response_slow']
            )
            resp.raise_for_status()
            return resp.json()
        
        def search_movie(self, movie_id):
            """Trigger a search for a movie."""
            payload = {"name": "MoviesSearch", "movieIds": [movie_id]}
            resp = self.post("command", json=payload)
            resp.raise_for_status()
            return resp.json()
        
        def delete_movie(self, movie_id, delete_files=False):
            """Delete a movie from the library."""
            resp = self.delete(f"movie/{movie_id}", params={"deleteFiles": delete_files})
            resp.raise_for_status()
        
        def remove_from_queue(self, queue_id, blocklist=False):
            """Remove an item from the download queue."""
            params = {
                "removeFromClient": False,
                "blocklist": blocklist,
                "skipRedownload": False,
                "changeCategory": False,
            }
            resp = self.delete(f"queue/{queue_id}", params=params)
            resp.raise_for_status()
    
    return RadarrClient(
        SERVICES['radarr']['host'],
        SERVICES['radarr']['port'],
        radarr_api_key
    )


@pytest.fixture(scope="session")
def sonarr_client(sonarr_api_key, ensure_sonarr_indexer_registered):
    """Provide a requests-based Sonarr API client."""
    class SonarrClient:
        def __init__(self, host, port, api_key):
            self.base_url = f"http://{host}:{port}/api/v3"
            self.headers = {"X-Api-Key": api_key}
        
        def get(self, endpoint, **kwargs):
            return requests.get(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def post(self, endpoint, **kwargs):
            return requests.post(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def delete(self, endpoint, **kwargs):
            return requests.delete(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                timeout=TIMEOUTS['api_response'],
                **kwargs
            )
        
        def get_queue(self):
            """Get current download queue."""
            resp = self.get("queue")
            resp.raise_for_status()
            return resp.json()
        
        def get_series(self):
            """Get all series in library."""
            resp = self.get("series")
            resp.raise_for_status()
            return resp.json()
        
        def get_episodes(self, series_id):
            """Get all episodes for a series."""
            resp = self.get("episode", params={"seriesId": series_id})
            resp.raise_for_status()
            return resp.json()
        
        def add_series(self, title, tvdb_id, search=True):
            """Add a series to the library."""
            payload = {
                "title": title,
                "qualityProfileId": 1,
                "tvdbId": tvdb_id,
                "rootFolderPath": "/downloads/tv",
                "monitored": True,
                "addOptions": {"searchForMissingEpisodes": search}
            }
            # Use slow timeout - adding series fetches metadata from TVDB
            resp = requests.post(
                f"{self.base_url}/series",
                headers=self.headers,
                json=payload,
                timeout=TIMEOUTS['api_response_slow']
            )
            resp.raise_for_status()
            return resp.json()
        
        def search_series(self, series_id):
            """Trigger a search for a series."""
            payload = {"name": "SeriesSearch", "seriesId": series_id}
            resp = self.post("command", json=payload)
            resp.raise_for_status()
            return resp.json()
        
        def search_season(self, series_id, season_number):
            """Trigger a search for a season."""
            payload = {"name": "SeasonSearch", "seriesId": series_id, "seasonNumber": season_number}
            resp = self.post("command", json=payload)
            resp.raise_for_status()
            return resp.json()
        
        def delete_series(self, series_id, delete_files=False):
            """Delete a series from the library."""
            resp = self.delete(f"series/{series_id}", params={"deleteFiles": delete_files})
            resp.raise_for_status()
        
        def remove_from_queue(self, queue_id, blocklist=False):
            """Remove an item from the download queue."""
            params = {
                "removeFromClient": False,
                "blocklist": blocklist,
                "skipRedownload": False,
                "changeCategory": False,
            }
            resp = self.delete(f"queue/{queue_id}", params=params)
            resp.raise_for_status()
    
    return SonarrClient(
        SERVICES['sonarr']['host'],
        SERVICES['sonarr']['port'],
        sonarr_api_key
    )


@pytest.fixture(scope="session")
def deluge_source(docker_services):
    """Provide a Deluge RPC client for the source instance."""
    client = DelugeRPCClient(
        host=SERVICES['deluge_source']['host'],
        port=SERVICES['deluge_source']['rpc_port'],
        username=DELUGE_USERNAME,
        password=DELUGE_PASSWORD,
        decode_utf8=True,
    )
    client.connect()
    yield client
    # Don't disconnect - may cause issues with connection reuse


@pytest.fixture(scope="session")
def deluge_target(docker_services):
    """Provide a Deluge RPC client for the target instance."""
    client = DelugeRPCClient(
        host=SERVICES['deluge_target']['host'],
        port=SERVICES['deluge_target']['rpc_port'],
        username=DELUGE_USERNAME,
        password=DELUGE_PASSWORD,
        decode_utf8=True,
    )
    client.connect()
    yield client


@pytest.fixture(scope="function")
def deluge_target_2(docker_client, docker_services):
    """
    Provide a Deluge RPC client for the second target instance.
    
    This fixture requires the multi-target profile to be started:
    docker compose -f docker/docker-compose.test.yml --profile multi-target up -d deluge-target-2
    
    The fixture is function-scoped and will skip if the container isn't running.
    """
    # Check if deluge-target-2 is running
    try:
        container = docker_client.containers.get('test-deluge-target-2')
        if container.status != 'running':
            pytest.skip("deluge-target-2 not running. Start with: docker compose -f docker/docker-compose.test.yml --profile multi-target up -d deluge-target-2")
    except docker.errors.NotFound:
        pytest.skip("deluge-target-2 not found. Start with: docker compose -f docker/docker-compose.test.yml --profile multi-target up -d deluge-target-2")
    
    client = DelugeRPCClient(
        host=SERVICES['deluge_target_2']['host'],
        port=SERVICES['deluge_target_2']['rpc_port'],
        username=DELUGE_USERNAME,
        password=DELUGE_PASSWORD,
        decode_utf8=True,
    )
    client.connect()
    yield client

# ==============================================================================
# Torrent Creation Fixture
# ==============================================================================

@pytest.fixture(scope="session")
def create_torrent(docker_client, docker_services):
    """
    Factory fixture to create test torrents.
    
    Usage:
        torrent_info = create_torrent("Test.Movie.2024.1080p", size_mb=10)
        torrent_info = create_torrent("Test.Movie", size_mb=10, multi_file=True)
    """
    created_torrents = []
    
    def _create_torrent(name: str, size_mb: int = 10, multi_file: bool = False) -> dict:
        """Create a test torrent and return its info."""
        # Run torrent-creator via Docker API directly
        # This works from both local and Docker environments
        
        # Build command with optional multi-file support
        cmd = ["--name", name, "--size", str(size_mb), "--force"]
        if multi_file:
            cmd.extend(["--files", "5"])  # Create 5 files for multi-file torrents
        
        try:
            output = docker_client.containers.run(
                image="transferarr_test-torrent-creator",
                command=cmd,
                environment={
                    "TRACKER_URL": "http://tracker:6969/announce",
                    "CONTENT_DIR": "/downloads",
                    "TORRENT_DIR": "/torrents",
                },
                volumes={
                    "transferarr_test_source-downloads": {"bind": "/downloads", "mode": "rw"},
                    "transferarr_test_test-torrents": {"bind": "/torrents", "mode": "rw"},
                },
                network="transferarr_test_test-network",
                remove=True,
                stdout=True,
                stderr=True,
            )
            output = output.decode() if isinstance(output, bytes) else str(output)
        except docker.errors.ImageNotFound:
            # Image not built - fail with instructions
            pytest.fail(
                "Torrent creator image not found. Build with: "
                "docker compose -f docker/docker-compose.test.yml --profile tools build torrent-creator"
            )
        
        # Parse output to get hash
        info_hash = None
        for line in output.split('\n'):
            if 'Hash:' in line:
                info_hash = line.split('Hash:')[1].strip()
                break
        
        if not info_hash:
            pytest.fail(f"Could not parse torrent hash from output: {output}")
        
        torrent_info = {
            'name': name,
            'hash': info_hash,
            'size_mb': size_mb,
        }
        created_torrents.append(torrent_info)
        return torrent_info
    
    yield _create_torrent
    
    # Cleanup: Remove created content (optional - volumes get reset anyway)
    # We don't clean up here as tests may want to inspect state


# ==============================================================================
# Transferarr Management Fixture
# ==============================================================================

@pytest.fixture
def transferarr(docker_client, docker_services, radarr_api_key, sonarr_api_key):
    """
    Manage the transferarr container for tests.
    
    Provides methods to start, stop, restart, and check logs.
    """
    class TransferarrManager:
        def __init__(self, docker_client, radarr_key, sonarr_key):
            self.docker = docker_client
            self.container_name = "test-transferarr"
            self.radarr_api_key = radarr_key
            self.sonarr_api_key = sonarr_key
            self._current_config_type = None
        
        def is_running(self) -> bool:
            """Check if transferarr container is running."""
            try:
                container = self.docker.containers.get(self.container_name)
                return container.status == "running"
            except docker.errors.NotFound:
                return False
        
        def start(self, wait_healthy=True, config_type=None, history_config=None):
            """
            Start the transferarr container.
            
            Args:
                wait_healthy: Wait for container to be healthy before returning
                config_type: Config type to use (e.g., 'sftp-to-local', 'multi-target').
                            If None, uses the default sftp-to-sftp config.
                            If specified, copies the config file to shared-config volume.
                history_config: History config override (e.g., 'disabled', 'no-progress').
                            If specified, merges history settings with base config.
            """
            # Determine config key for caching
            config_key = (config_type or 'default', history_config)
            
            # If config changed from current, update config
            if config_key != self._current_config_type:
                base_config = config_type or 'sftp-to-sftp'
                if base_config not in TRANSFER_TYPE_CONFIGS:
                    pytest.fail(f"Unknown config type: {base_config}. Available: {list(TRANSFER_TYPE_CONFIGS.keys())}")
                
                # Load history override if specified
                history_override = None
                if history_config:
                    if history_config not in HISTORY_CONFIGS:
                        pytest.fail(f"Unknown history config: {history_config}. Available: {list(HISTORY_CONFIGS.keys())}")
                    import json
                    with open(HISTORY_CONFIGS[history_config]) as f:
                        history_override = json.load(f)
                
                self.set_config(
                    TRANSFER_TYPE_CONFIGS[base_config],
                    self.radarr_api_key,
                    self.sonarr_api_key,
                    history_override=history_override
                )
                self._current_config_type = config_key
            
            try:
                container = self.docker.containers.get(self.container_name)
                if container.status != "running":
                    container.start()
            except docker.errors.NotFound:
                # Container doesn't exist
                pytest.fail(
                    "Transferarr container not found. "
                    "Start it with: docker compose --profile app up -d transferarr"
                )
            
            if wait_healthy:
                self.wait_healthy()
        
        def stop(self):
            """Stop the transferarr container."""
            try:
                container = self.docker.containers.get(self.container_name)
                container.stop()
            except docker.errors.NotFound:
                pass  # Already stopped or doesn't exist
        
        def restart(self, wait_healthy=True):
            """Restart the transferarr container."""
            try:
                container = self.docker.containers.get(self.container_name)
                container.restart()
            except docker.errors.NotFound:
                # Start if doesn't exist
                self.start(wait_healthy=False)
            
            if wait_healthy:
                self.wait_healthy()
        
        def wait_healthy(self, timeout=60):
            """Wait for transferarr to be healthy."""
            deadline = time.time() + timeout
            url = f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/health"
            
            while time.time() < deadline:
                try:
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        return True
                except requests.exceptions.RequestException:
                    pass
                time.sleep(2)
            
            pytest.fail("Transferarr did not become healthy in time")
        
        def get_logs(self, tail=100) -> str:
            """Get recent logs from the container."""
            try:
                container = self.docker.containers.get(self.container_name)
                return container.logs(tail=tail).decode()
            except docker.errors.NotFound:
                return ""
        
        def get_torrents(self) -> list:
            """Get tracked torrents from the API.
            
            Returns:
                List of torrent dicts from the API
                
            Raises:
                requests.exceptions.RequestException: If API call fails
            """
            url = f"http://{SERVICES['transferarr']['host']}:{SERVICES['transferarr']['port']}/api/v1/torrents"
            resp = requests.get(url, timeout=TIMEOUTS['api_response'])
            resp.raise_for_status()
            data = resp.json()
            # Unwrap data envelope (supports both old and new format)
            return data.get('data', data) if isinstance(data, dict) else data
        
        def clear_state(self):
            """Clear the state file and history database in the container."""
            try:
                container = self.docker.containers.get(self.container_name)
                if container.status == "running":
                    container.exec_run("rm -f /app/state/state.json")
                    container.exec_run("rm -f /app/state/history.db")
            except docker.errors.NotFound:
                pass
            except docker.errors.APIError:
                pass  # Container may not be running
        
        def set_config(self, config_path: Path, radarr_api_key: str, sonarr_api_key: str, history_override: dict = None):
            """
            Copy a config file to the shared-config volume with API keys injected.
            
            Args:
                config_path: Path to the config template file
                radarr_api_key: Radarr API key to inject
                sonarr_api_key: Sonarr API key to inject
                history_override: Optional dict to merge into config['history']
            """
            import json
            import tarfile
            import io
            
            # Read and process the config file
            with open(config_path) as f:
                config = json.load(f)
            
            # Inject API keys
            for manager in config.get('media_managers', []):
                if manager.get('type') == 'radarr':
                    manager['api_key'] = radarr_api_key
                elif manager.get('type') == 'sonarr':
                    manager['api_key'] = sonarr_api_key
            
            # Merge history override if provided
            if history_override:
                if 'history' not in config:
                    config['history'] = {}
                config['history'].update(history_override)
            
            config_content = json.dumps(config, indent=4)
            
            # Create a tar archive with the config file
            # Set uid/gid to 1000 (appuser) and mode to 666 for CRUD test compatibility
            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                config_bytes = config_content.encode('utf-8')
                tarinfo = tarfile.TarInfo(name='config.json')
                tarinfo.size = len(config_bytes)
                tarinfo.uid = 1000  # appuser
                tarinfo.gid = 1000  # appuser
                tarinfo.mode = 0o666  # World-writable for CRUD tests
                tar.addfile(tarinfo, io.BytesIO(config_bytes))
            tar_buffer.seek(0)
            
            # Always use a temporary container to write to the shared-config volume
            # (transferarr mounts it read-only, so we need a writable mount)
            temp_container = self.docker.containers.run(
                image="alpine:latest",
                command="sleep 30",
                volumes={
                    "transferarr_test_shared-config": {"bind": "/config", "mode": "rw"},
                },
                network="transferarr_test_test-network",
                detach=True,
            )
            try:
                temp_container.put_archive('/config', tar_buffer.getvalue())
            finally:
                temp_container.stop()
                temp_container.remove()
    
    return TransferarrManager(docker_client, radarr_api_key, sonarr_api_key)


# ==============================================================================
# Cleanup Fixtures
# ==============================================================================

@pytest.fixture
def cleanup_radarr(radarr_client):
    """Clean up Radarr state after test."""
    yield
    
    # Delete all movies
    movies = radarr_client.get_movies()
    for movie in movies:
        try:
            radarr_client.delete_movie(movie['id'], delete_files=True)
        except Exception:
            pass
    
    # Clear queue
    queue = radarr_client.get_queue()
    for item in queue.get('records', []):
        try:
            radarr_client.remove_from_queue(item['id'])
        except Exception:
            pass


@pytest.fixture
def cleanup_deluge(deluge_source, deluge_target):
    """Clean up Deluge torrents after test."""
    yield
    
    # Remove all torrents from source
    try:
        torrents = deluge_source.core.get_torrents_status({}, ['name'])
        for torrent_id in torrents.keys():
            deluge_source.core.remove_torrent(torrent_id, True)
    except Exception:
        pass
    
    # Remove all torrents from target
    try:
        torrents = deluge_target.core.get_torrents_status({}, ['name'])
        for torrent_id in torrents.keys():
            deluge_target.core.remove_torrent(torrent_id, True)
    except Exception:
        pass


@pytest.fixture
def clean_state(cleanup_radarr, cleanup_deluge, transferarr):
    """
    Combined cleanup fixture that runs before AND after tests.
    
    Use this fixture to ensure clean state for each test.
    """
    # Pre-test cleanup
    transferarr.clear_state()
    
    yield
    
    # Post-test cleanup is handled by the dependent fixtures


# ==============================================================================
# Shared Test Setup Fixture
# ==============================================================================

@pytest.fixture
def clean_test_environment(radarr_client, sonarr_client, deluge_source, deluge_target, transferarr):
    """
    Standard setup and teardown for integration tests.
    
    This fixture:
    - Clears all state before the test
    - Stops transferarr if running
    - Yields control to the test
    - Cleans up after the test
    
    Use this instead of duplicating setup_and_teardown in each test class.
    
    Usage:
        def test_something(self, clean_test_environment, create_torrent, ...):
            # Test code here - environment is already clean
    """
    from tests.utils import clear_radarr_state, clear_sonarr_state, clear_deluge_torrents, clear_mock_indexer_torrents
    
    # Pre-test cleanup
    clear_radarr_state(radarr_client)
    clear_sonarr_state(sonarr_client)
    clear_deluge_torrents(deluge_source)
    clear_deluge_torrents(deluge_target)
    clear_mock_indexer_torrents()
    transferarr.clear_state()
    
    # Stop transferarr if running (tests will start it when needed)
    if transferarr.is_running():
        transferarr.stop()
    
    yield

@pytest.fixture
def lifecycle_runner(create_torrent, deluge_source, deluge_target, transferarr, radarr_client, sonarr_client):
    """Fixture providing a LifecycleRunner for standardized migration tests."""
    from tests.integration.helpers import LifecycleRunner
    return LifecycleRunner(create_torrent, deluge_source, deluge_target, transferarr, radarr_client, sonarr_client)


# ==============================================================================
# Transfer Type Testing Fixtures
# ==============================================================================

@pytest.fixture
def configure_transfer_type(transferarr, radarr_api_key, sonarr_api_key):
    """
    Factory fixture for configuring transferarr with a specific transfer type.
    
    Usage:
        def test_sftp_to_local(configure_transfer_type):
            configure_transfer_type('sftp-to-local')
            # ... test code
    
    Available transfer types:
        - 'sftp-to-local': SFTP source, local destination
        - 'local-to-sftp': Local source, SFTP destination
        - 'sftp-to-sftp': Both SFTP (default test config)
        - 'local-to-local': Both local volumes
    """
    def _configure(transfer_type: str):
        if transfer_type not in TRANSFER_TYPE_CONFIGS:
            raise ValueError(f"Unknown transfer type: {transfer_type}. "
                           f"Available: {list(TRANSFER_TYPE_CONFIGS.keys())}")
        
        config_path = TRANSFER_TYPE_CONFIGS[transfer_type]
        transferarr.set_config(config_path, radarr_api_key, sonarr_api_key)
        return transfer_type
    
    return _configure
