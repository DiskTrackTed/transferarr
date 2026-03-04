#!/usr/bin/env python3
"""
Add a random test movie to the Docker test environment.

Picks a movie from the test catalog, creates a torrent on the source Deluge,
registers it with the mock indexer, and adds it to Radarr (without searching).

This lets you manually trigger a search in Radarr when you're ready to test.

Usage:
    # Add a random movie
    python scripts/add_test_movie.py

    # Add a specific movie by key
    python scripts/add_test_movie.py --movie jurassic_park

    # Add a movie and trigger Radarr search immediately
    python scripts/add_test_movie.py --search

    # List available movies
    python scripts/add_test_movie.py --list

    # Custom torrent size
    python scripts/add_test_movie.py --size 50

Prerequisites:
    Docker test environment must be running:
        docker compose -f docker/docker-compose.test.yml up -d
"""
import argparse
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import docker
    import requests
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install docker requests")
    sys.exit(1)

# Add project root to path so we can import from tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.utils import MovieCatalog, make_torrent_name

# Docker volume/network names (compose project: transferarr_test)
VOLUME_SOURCE_DOWNLOADS = "transferarr_test_source-downloads"
VOLUME_TEST_TORRENTS = "transferarr_test_test-torrents"
DOCKER_NETWORK = "transferarr_test_test-network"
TORRENT_CREATOR_IMAGE = "transferarr_test-torrent-creator"

# Host-accessible service ports
RADARR_HOST = "localhost"
RADARR_PORT = 17878


def extract_radarr_api_key(docker_client):
    """Extract Radarr API key from the running container's config.xml."""
    try:
        container = docker_client.containers.get("test-radarr")
    except docker.errors.NotFound:
        print("ERROR: test-radarr container not found. Is the test environment running?")
        sys.exit(1)

    result = container.exec_run("cat /config/config.xml")
    if result.exit_code != 0:
        print("ERROR: Failed to read Radarr config.xml")
        sys.exit(1)

    root = ET.fromstring(result.output.decode())
    api_key = root.find("ApiKey")
    if api_key is None or not api_key.text:
        print("ERROR: Could not find ApiKey in Radarr config")
        sys.exit(1)

    return api_key.text


def create_torrent(docker_client, name, size_mb=10, multi_file=False):
    """Create a test torrent via the torrent-creator Docker container.

    Returns dict with 'name', 'hash', 'size_mb'.
    """
    cmd = ["--name", name, "--size", str(size_mb), "--force"]
    if multi_file:
        cmd.extend(["--files", "5"])

    try:
        output = docker_client.containers.run(
            image=TORRENT_CREATOR_IMAGE,
            command=cmd,
            environment={
                "TRACKER_URL": "http://tracker:6969/announce",
                "CONTENT_DIR": "/downloads",
                "TORRENT_DIR": "/torrents",
            },
            volumes={
                VOLUME_SOURCE_DOWNLOADS: {"bind": "/downloads", "mode": "rw"},
                VOLUME_TEST_TORRENTS: {"bind": "/torrents", "mode": "rw"},
            },
            network=DOCKER_NETWORK,
            remove=True,
            stdout=True,
            stderr=True,
        )
        output = output.decode() if isinstance(output, bytes) else str(output)
    except docker.errors.ImageNotFound:
        print(
            "ERROR: Torrent creator image not found. Build with:\n"
            "  docker compose -f docker/docker-compose.test.yml --profile tools build torrent-creator"
        )
        sys.exit(1)

    # Parse hash from output
    info_hash = None
    for line in output.split("\n"):
        if "Hash:" in line:
            info_hash = line.split("Hash:")[1].strip()
            break

    if not info_hash:
        print(f"ERROR: Could not parse torrent hash from output:\n{output}")
        sys.exit(1)

    return {"name": name, "hash": info_hash, "size_mb": size_mb}


def add_movie_to_radarr(api_key, title, tmdb_id, year, search=False):
    """Add a movie to Radarr via API.

    Returns the Radarr movie object on success, or None on failure.
    """
    base_url = f"http://{RADARR_HOST}:{RADARR_PORT}/api/v3"
    headers = {"X-Api-Key": api_key}

    # Check if movie already exists
    resp = requests.get(f"{base_url}/movie", headers=headers, timeout=30)
    resp.raise_for_status()
    existing = resp.json()
    for movie in existing:
        if movie.get("tmdbId") == tmdb_id:
            print(f"  Movie already in Radarr (id={movie['id']}), skipping add")
            return movie

    payload = {
        "title": title,
        "qualityProfileId": 1,
        "tmdbId": tmdb_id,
        "year": year,
        "rootFolderPath": "/downloads/movies",
        "monitored": True,
        "addOptions": {"searchForMovie": search},
    }
    resp = requests.post(
        f"{base_url}/movie",
        headers=headers,
        json=payload,
        timeout=120,  # Adding movies fetches TMDB metadata
    )
    if resp.status_code == 400 and "already been added" in resp.text.lower():
        print(f"  Movie already exists in Radarr")
        return None
    resp.raise_for_status()
    return resp.json()


def search_movie_in_radarr(api_key, movie_id):
    """Trigger a movie search in Radarr."""
    base_url = f"http://{RADARR_HOST}:{RADARR_PORT}/api/v3"
    headers = {"X-Api-Key": api_key}
    payload = {"name": "MoviesSearch", "movieIds": [movie_id]}
    resp = requests.post(
        f"{base_url}/command", headers=headers, json=payload, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def list_movies(catalog):
    """Print all available movies in the catalog."""
    print(f"Available movies ({len(catalog.MOVIES)}):\n")
    for key, movie in sorted(catalog.MOVIES.items()):
        print(f"  {key:45s}  {movie['title']} ({movie['year']})  [tmdb:{movie['tmdb_id']}]")


def main():
    parser = argparse.ArgumentParser(
        description="Add a random test movie to the Docker test environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                         # Random movie, no search
  %(prog)s --movie jurassic_park   # Specific movie
  %(prog)s --search                # Add and trigger Radarr search
  %(prog)s --list                  # Show available movies
  %(prog)s --size 50               # 50MB torrent
  %(prog)s --multi-file            # Multi-file (directory) torrent
        """,
    )
    parser.add_argument(
        "--movie",
        help="Specific movie key from catalog (use --list to see keys)",
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="Trigger a Radarr search after adding (default: no search)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=10,
        help="Torrent size in MB (default: 10)",
    )
    parser.add_argument(
        "--multi-file",
        action="store_true",
        help="Create a multi-file (directory) torrent",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available movies and exit",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        default=True,
        help="Pick a random movie (default behavior)",
    )

    args = parser.parse_args()

    # Create a fresh catalog instance (not the global singleton)
    catalog = MovieCatalog()

    if args.list:
        list_movies(catalog)
        return

    # Pick a movie
    if args.movie:
        try:
            movie = catalog.get_movie(key=args.movie)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        # Shuffle so it's truly random (catalog is ordered)
        keys = list(catalog.MOVIES.keys())
        random.shuffle(keys)
        movie = catalog.get_movie(key=keys[0])

    torrent_name = make_torrent_name(movie["title"], movie["year"])

    print(f"{'=' * 60}")
    print(f"  Movie:   {movie['title']} ({movie['year']})")
    print(f"  TMDB:    {movie['tmdb_id']}")
    print(f"  Torrent: {torrent_name}")
    print(f"  Size:    {args.size}MB {'(multi-file)' if args.multi_file else ''}")
    print(f"{'=' * 60}")
    print()

    # Connect to Docker
    print("Connecting to Docker...")
    docker_client = docker.from_env()

    # Step 1: Extract Radarr API key
    print("Extracting Radarr API key...")
    api_key = extract_radarr_api_key(docker_client)
    print(f"  Key: {api_key[:8]}...")

    # Step 2: Create torrent
    print(f"Creating torrent ({args.size}MB)...")
    torrent_info = create_torrent(
        docker_client, torrent_name, size_mb=args.size, multi_file=args.multi_file
    )
    print(f"  Hash: {torrent_info['hash']}")

    # Step 3: Add movie to Radarr
    print(f"Adding '{movie['title']}' to Radarr...")
    radarr_movie = add_movie_to_radarr(
        api_key,
        title=movie["title"],
        tmdb_id=movie["tmdb_id"],
        year=movie["year"],
        search=args.search,
    )

    # Step 4: Optionally trigger search
    if args.search and radarr_movie:
        movie_id = radarr_movie.get("id")
        if movie_id:
            print(f"Triggering Radarr search for movie id={movie_id}...")
            search_movie_in_radarr(api_key, movie_id)
            print("  Search command sent")

    print()
    print(f"{'=' * 60}")
    print(f"  DONE!")
    print(f"  Movie:   {movie['title']} ({movie['year']})")
    print(f"  Torrent: {torrent_name}")
    print(f"  Hash:    {torrent_info['hash']}")
    if not args.search:
        print()
        print(f"  To trigger search, either:")
        print(f"    - Search in Radarr UI: http://localhost:{RADARR_PORT}")
        print(f"    - Run again with: python {sys.argv[0]} --movie {movie['key']} --search")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
