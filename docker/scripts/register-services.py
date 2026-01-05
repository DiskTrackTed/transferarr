#!/usr/bin/env python3
"""
scripts/register-services.py
Extracts API keys, registers download clients with Radarr/Sonarr,
then generates the transferarr config.json
"""
import requests
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import time
import sys

# Constants - must match docker-compose and pre-seeded files
DELUGE_PASSWORD = "testpassword"
SFTP_USER = "testuser"
SFTP_PASS = "testpass"


def wait_for_service(url, timeout=120):
    """Wait for service to respond to health check"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/ping", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Service {url} not ready after {timeout}s")


def get_api_key(config_path, timeout=60):
    """Extract API key from Radarr/Sonarr config.xml, waiting for file to exist"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            tree = ET.parse(config_path)
            api_key = tree.find('ApiKey')
            if api_key is not None and api_key.text:
                return api_key.text
        except (ET.ParseError, FileNotFoundError):
            pass
        time.sleep(2)
    raise TimeoutError(f"Could not extract API key from {config_path} after {timeout}s")


def register_deluge_client(arr_url, api_key, client_config, arr_type):
    """Register Deluge as download client in Radarr/Sonarr"""
    headers = {"X-Api-Key": api_key}
    
    # Check if already registered
    existing = requests.get(f"{arr_url}/api/v3/downloadclient", headers=headers).json()
    if any(c['name'] == client_config['name'] for c in existing):
        print(f"  Client {client_config['name']} already registered in {arr_type}")
        return
    
    # Build fields based on arr type - not using categories since Label plugin isn't enabled
    if arr_type == "sonarr":
        category_field = {"name": "tvCategory", "value": ""}
        priority_fields = [
            {"name": "recentTvPriority", "value": 1},
            {"name": "olderTvPriority", "value": 1},
        ]
    else:
        category_field = {"name": "movieCategory", "value": ""}
        priority_fields = [
            {"name": "recentMoviePriority", "value": 1},
            {"name": "olderMoviePriority", "value": 1},
        ]
    
    payload = {
        "name": client_config['name'],
        "implementation": "Deluge",
        "configContract": "DelugeSettings",
        "protocol": "torrent",
        "priority": 1,
        "enable": True,
        "fields": [
            {"name": "host", "value": client_config['host']},
            {"name": "port", "value": client_config['port']},
            {"name": "useSsl", "value": False},
            {"name": "urlBase", "value": ""},
            {"name": "password", "value": client_config['password']},
            category_field,
            *priority_fields,
            {"name": "addPaused", "value": False},
        ]
    }
    
    r = requests.post(f"{arr_url}/api/v3/downloadclient", headers=headers, json=payload)
    if r.status_code in (200, 201):
        print(f"  Registered {client_config['name']} with {arr_type}")
    else:
        print(f"  Failed to register {client_config['name']} with {arr_type}: {r.status_code} - {r.text}")
        r.raise_for_status()


def generate_transferarr_config(radarr_key, sonarr_key):
    """Generate transferarr config.json with extracted credentials"""
    config = {
        "log_level": "DEBUG",
        "state_file": "/app/state/state.json",
        "media_managers": [
            {
                "type": "radarr",
                "host": "http://radarr",
                "port": 7878,
                "api_key": radarr_key
            },
            {
                "type": "sonarr",
                "host": "http://sonarr",
                "port": 8989,
                "api_key": sonarr_key
            }
        ],
        "download_clients": {
            "source-deluge": {
                "type": "deluge",
                "connection_type": "rpc",
                "host": "deluge-source",
                "port": 58846,
                "username": "localclient",
                "password": DELUGE_PASSWORD
            },
            "target-deluge": {
                "type": "deluge",
                "connection_type": "rpc",
                "host": "deluge-target",
                "port": 58846,
                "username": "localclient",
                "password": DELUGE_PASSWORD
            }
        },
        "connections": [
            {
                "from": "source-deluge",
                "to": "target-deluge",
                "transfer_config": {
                    "from": {
                        "type": "sftp",
                        "sftp": {
                            "host": "sftp-server",
                            "port": 2222,
                            "username": SFTP_USER,
                            "password": SFTP_PASS
                        }
                    },
                    "to": {"type": "local"}
                },
                "source_dot_torrent_path": "/home/testuser/state/",
                "source_torrent_download_path": "/home/testuser/downloads/",
                "destination_dot_torrent_tmp_dir": "/tmp/torrents/",
                "destination_torrent_download_path": "/target-downloads/"
            }
        ]
    }
    return config


def ensure_root_folder(arr_url, api_key, arr_type):
    """Ensure root folder exists in Radarr/Sonarr"""
    headers = {"X-Api-Key": api_key}
    
    # Define paths based on arr type
    if arr_type == "radarr":
        folder_path = "/downloads/movies"
    else:
        folder_path = "/downloads/tv"
    
    # Check if root folder already exists
    existing = requests.get(f"{arr_url}/api/v3/rootfolder", headers=headers).json()
    if any(rf.get('path') == folder_path for rf in existing):
        print(f"  Root folder {folder_path} already exists in {arr_type}")
        return
    
    # Create the directory (it may not exist in the container)
    # Note: This relies on the folder being writable by the arr service
    # The folder is created via the volume mount
    
    # Register the root folder
    payload = {"path": folder_path}
    r = requests.post(f"{arr_url}/api/v3/rootfolder", headers=headers, json=payload)
    if r.status_code in (200, 201):
        print(f"  Added root folder {folder_path} to {arr_type}")
    else:
        # Root folder may fail if directory doesn't exist - that's OK for initial setup
        print(f"  Note: Could not add root folder {folder_path} to {arr_type}: {r.status_code}")


def register_mock_indexer(arr_url, api_key, arr_type):
    """Register mock-indexer as Torznab indexer in Radarr/Sonarr"""
    headers = {"X-Api-Key": api_key}
    
    # Check if already registered
    existing = requests.get(f"{arr_url}/api/v3/indexer", headers=headers).json()
    if any(idx.get('name') == 'mock-indexer' for idx in existing):
        print(f"  Indexer mock-indexer already registered in {arr_type}")
        return
    
    # Different categories for Radarr vs Sonarr
    # Include all relevant subcategories to ensure test queries succeed
    if arr_type == "radarr":
        categories = [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060]  # All Movies subcategories
    else:
        categories = [5000, 5010, 5020, 5030, 5040, 5045, 5050, 5060]  # All TV subcategories
    
    payload = {
        "name": "mock-indexer",
        "implementation": "Torznab",
        "implementationName": "Torznab",
        "configContract": "TorznabSettings",
        "protocol": "torrent",
        "priority": 25,
        "enable": True,
        "enableRss": True,
        "enableAutomaticSearch": True,
        "enableInteractiveSearch": True,
        "supportsRss": True,
        "supportsSearch": True,
        "fields": [
            {"name": "baseUrl", "value": "http://mock-indexer:9696"},
            {"name": "apiPath", "value": "/api"},
            {"name": "apiKey", "value": ""},  # Mock indexer doesn't require key
            {"name": "categories", "value": categories},
            {"name": "minimumSeeders", "value": 0},
            {"name": "seedCriteria.seedRatio", "value": ""},
            {"name": "seedCriteria.seedTime", "value": ""},
        ]
    }
    
    r = requests.post(f"{arr_url}/api/v3/indexer", headers=headers, json=payload)
    if r.status_code in (200, 201):
        print(f"  Registered mock-indexer with {arr_type}")
    else:
        print(f"  Failed to register mock-indexer with {arr_type}: {r.status_code} - {r.text}")
        # Don't raise - indexer registration failures are non-fatal
        # May fail due to API differences between Radarr/Sonarr versions


def main():
    print("=" * 60)
    print("Transferarr Test Environment - Service Registration")
    print("=" * 60)
    
    print("\n[1/5] Waiting for services to be ready...")
    try:
        wait_for_service("http://radarr:7878")
        print("  Radarr is ready")
        wait_for_service("http://sonarr:8989")
        print("  Sonarr is ready")
    except TimeoutError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    print("\n[2/5] Extracting API keys...")
    try:
        radarr_key = get_api_key("/radarr-config/config.xml")
        print(f"  Radarr API key: {radarr_key[:8]}...")
        sonarr_key = get_api_key("/sonarr-config/config.xml")
        print(f"  Sonarr API key: {sonarr_key[:8]}...")
    except TimeoutError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    print("\n[3/5] Registering download clients...")
    deluge_config = {
        "name": "source-deluge",
        "host": "deluge-source",
        "port": 8112,  # Web UI port for Radarr/Sonarr
        "password": DELUGE_PASSWORD
    }
    try:
        register_deluge_client("http://radarr:7878", radarr_key, deluge_config, "radarr")
        register_deluge_client("http://sonarr:8989", sonarr_key, deluge_config, "sonarr")
    except Exception as e:
        print(f"ERROR registering download clients: {e}")
        sys.exit(1)
    
    print("\n[4/5] Registering mock indexer and root folders...")
    # Ensure root folders exist first (needed for adding movies/shows)
    try:
        ensure_root_folder("http://radarr:7878", radarr_key, "radarr")
        ensure_root_folder("http://sonarr:8989", sonarr_key, "sonarr")
    except Exception as e:
        print(f"  Note: Root folder setup issue: {e}")
    
    # Register mock indexer
    try:
        register_mock_indexer("http://radarr:7878", radarr_key, "radarr")
        register_mock_indexer("http://sonarr:8989", sonarr_key, "sonarr")
    except Exception as e:
        print(f"  NOTE: Indexer registration skipped (validation failed)")
    
    print("\n[5/5] Generating transferarr config...")
    config = generate_transferarr_config(radarr_key, sonarr_key)
    
    # Ensure output directory exists
    output_dir = Path("/shared")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    config_path = output_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    print(f"  Config written to {config_path}")
    
    print("\n" + "=" * 60)
    print("Configuration complete!")
    print("=" * 60)
    print(f"\nGenerated config.json with:")
    print(f"  - Radarr API key: {radarr_key[:8]}...")
    print(f"  - Sonarr API key: {sonarr_key[:8]}...")
    print(f"  - Download clients: source-deluge, target-deluge")
    print(f"  - Indexer: mock-indexer (Torznab)")
    print(f"  - Connection: source-deluge -> target-deluge via SFTP")


if __name__ == "__main__":
    main()
