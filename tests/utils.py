"""
Test utilities for Transferarr integration tests.

Provides helper functions for common test operations like waiting for
state transitions, polling for conditions, and decoding Deluge responses.
"""
import time
import re
from typing import Callable, Any, Optional, List


# ==============================================================================
# Torrent Name Utilities
# ==============================================================================

def sanitize_title_for_torrent(title: str) -> str:
    """
    Sanitize a movie/show title for use in torrent filenames.
    
    Removes characters that are problematic in filenames (colons, slashes, etc.)
    and replaces spaces with dots.
    
    Args:
        title: Movie or show title (e.g., "Star Wars: The Force Awakens")
        
    Returns:
        Sanitized string suitable for torrent names (e.g., "Star.Wars.The.Force.Awakens")
    """
    # Remove colons, slashes, and other problematic characters
    sanitized = re.sub(r'[:/\\?*"<>|]', '', title)
    # Replace en dash and ampersand with spaces
    sanitized = sanitized.replace('–', ' ').replace('&', 'and')
    # Replace spaces with dots
    sanitized = sanitized.replace(' ', '.')
    # Collapse multiple dots into single dot
    sanitized = re.sub(r'\.+', '.', sanitized)
    # Remove leading/trailing dots
    sanitized = sanitized.strip('.')
    return sanitized


def make_torrent_name(title: str, year: int, quality: str = "1080p.BluRay.x264") -> str:
    """
    Create a standard torrent name from movie/show info.
    
    Args:
        title: Movie or show title
        year: Release year
        quality: Quality string (default: "1080p.BluRay.x264")
        
    Returns:
        Standard torrent name (e.g., "Star.Wars.The.Force.Awakens.2015.1080p.BluRay.x264")
    """
    sanitized_title = sanitize_title_for_torrent(title)
    return f"{sanitized_title}.{year}.{quality}"


def make_episode_name(title: str, season: int, episode: int, quality: str = "1080p.BluRay.x264") -> str:
    """
    Create a standard episode torrent name.
    
    Args:
        title: Show title
        season: Season number
        episode: Episode number
        quality: Quality string
        
    Returns:
        Standard episode name (e.g., "Breaking.Bad.S01E01.1080p.BluRay.x264")
    """
    sanitized_title = sanitize_title_for_torrent(title)
    return f"{sanitized_title}.S{season:02d}E{episode:02d}.{quality}"


def make_season_pack_name(title: str, season: int, quality: str = "1080p.BluRay.x264") -> str:
    """
    Create a standard season pack torrent name.
    
    Args:
        title: Show title
        season: Season number
        quality: Quality string
        
    Returns:
        Standard season pack name (e.g., "Breaking.Bad.S01.1080p.BluRay.x264")
    """
    sanitized_title = sanitize_title_for_torrent(title)
    return f"{sanitized_title}.S{season:02d}.{quality}"


def make_multi_episode_name(title: str, season: int, start_ep: int, end_ep: int, quality: str = "1080p.BluRay.x264") -> str:
    """
    Create a standard multi-episode torrent name.
    
    Args:
        title: Show title
        season: Season number
        start_ep: Starting episode number
        end_ep: Ending episode number
        quality: Quality string
        
    Returns:
        Standard multi-episode name (e.g., "Breaking.Bad.S01E01-E02.1080p.BluRay.x264")
    """
    sanitized_title = sanitize_title_for_torrent(title)
    return f"{sanitized_title}.S{season:02d}E{start_ep:02d}-E{end_ep:02d}.{quality}"


# ==============================================================================
# Byte Decoding Utilities
# ==============================================================================

def decode_bytes(obj):
    """
    Recursively decode bytes to strings in nested data structures.
    
    Deluge RPC returns bytes for strings, this helper converts them.
    """
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    elif isinstance(obj, dict):
        return {decode_bytes(k): decode_bytes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decode_bytes(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(decode_bytes(item) for item in obj)
    return obj


# ==============================================================================
# Generic Wait Utilities
# ==============================================================================

def wait_for_condition(
    condition: Callable[[], bool],
    timeout: int,
    poll_interval: float = 2.0,
    description: str = "condition"
) -> bool:
    """
    Wait for a condition to become true.
    
    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum seconds to wait
        poll_interval: Seconds between condition checks
        description: Human-readable description for error messages
    
    Returns:
        True if condition was met
        
    Raises:
        TimeoutError: If condition not met within timeout
    """
    deadline = time.time() + timeout
    last_error = None
    
    while time.time() < deadline:
        try:
            if condition():
                return True
        except Exception as e:
            last_error = e
        time.sleep(poll_interval)
    
    error_msg = f"Timeout waiting for {description} after {timeout}s"
    if last_error:
        error_msg += f" (last error: {last_error})"
    raise TimeoutError(error_msg)


# ==============================================================================
# Queue Error Detection
# ==============================================================================

class QueueItemError(Exception):
    """Raised when a queue item has an error status."""
    def __init__(self, message: str, queue_item: dict):
        super().__init__(message)
        self.queue_item = queue_item
        self.status = queue_item.get('status', '')
        self.tracked_status = queue_item.get('trackedDownloadStatus', '')
        self.error_message = queue_item.get('errorMessage', '')


def check_queue_item_for_errors(queue_item: dict) -> tuple:
    """
    Check if a queue item has errors that indicate a failed download.
    
    Args:
        queue_item: Queue item dict from Radarr/Sonarr API
        
    Returns:
        Tuple of (has_error: bool, error_message: str)
    """
    tracked_status = queue_item.get('trackedDownloadStatus', 'ok')
    status = queue_item.get('status', '')
    error_msg = queue_item.get('errorMessage', '')
    
    # Check for error status
    if tracked_status == 'error':
        status_messages = queue_item.get('statusMessages', [])
        msgs = [m.get('title', '') for m in status_messages if m.get('title')]
        detail = error_msg or '; '.join(msgs) or 'Unknown error'
        return True, f"trackedDownloadStatus=error: {detail}"
    
    # Check for failed/warning statuses
    if status == 'failed':
        return True, f"status=failed: {error_msg or 'Download failed'}"
    
    if status == 'warning' and tracked_status != 'ok':
        return True, f"status=warning: {error_msg or 'Download warning'}"
    
    if status == 'downloadClientUnavailable':
        return True, f"status=downloadClientUnavailable: {error_msg or 'Download client unavailable'}"
    
    return False, ""


# ==============================================================================
# Queue Utilities (Radarr/Sonarr)
# ==============================================================================

def _wait_for_queue_item_by_hash(
    client,
    torrent_hash: str,
    timeout: int = 60,
    expected_status: Optional[str] = None,
    check_for_errors: bool = True,
    client_name: str = "queue"
) -> dict:
    """
    Generic wait for a torrent to appear in a media manager queue by its hash.
    
    Args:
        client: RadarrClient or SonarrClient instance
        torrent_hash: Info hash of the torrent (case insensitive)
        timeout: Maximum seconds to wait
        expected_status: Optional status to wait for (e.g., 'completed')
        check_for_errors: If True, raise QueueItemError when queue item has error status
        client_name: Name for error messages (e.g., 'Radarr', 'Sonarr')
    
    Returns:
        The queue item dict
        
    Raises:
        TimeoutError: If torrent not found in queue within timeout
        QueueItemError: If check_for_errors=True and queue item has error status
    """
    hash_upper = torrent_hash.upper()
    last_queue_info = []
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        queue = client.get_queue()
        for item in queue.get('records', []):
            if item.get('downloadId', '').upper() == hash_upper:
                # Check for errors if enabled
                if check_for_errors:
                    has_error, error_detail = check_queue_item_for_errors(item)
                    if has_error:
                        raise QueueItemError(
                            f"Queue item has error: {error_detail}",
                            item
                        )
                
                if expected_status is None or item.get('status') == expected_status:
                    return item
        
        # Track queue state for debugging
        last_queue_info = [
            f"{item.get('downloadId', 'NO_ID')[:8]}...={item.get('title', 'NO_TITLE')}[{item.get('status')}]"
            for item in queue.get('records', [])
        ]
        time.sleep(2)
    
    raise TimeoutError(
        f"Torrent hash '{torrent_hash}' not found in {client_name} queue after {timeout}s. "
        f"Expected status: {expected_status}. Queue contained: {last_queue_info}"
    )


def wait_for_queue_item_by_hash(
    radarr_client,
    torrent_hash: str,
    timeout: int = 60,
    expected_status: Optional[str] = None,
    check_for_errors: bool = True
) -> dict:
    """Wait for a torrent to appear in the Radarr queue by its hash."""
    return _wait_for_queue_item_by_hash(
        radarr_client, torrent_hash, timeout, expected_status, check_for_errors, "Radarr"
    )


def wait_for_sonarr_queue_item_by_hash(
    sonarr_client,
    torrent_hash: str,
    timeout: int = 60,
    expected_status: Optional[str] = None,
    check_for_errors: bool = True
) -> dict:
    """Wait for a torrent to appear in the Sonarr queue by its hash."""
    return _wait_for_queue_item_by_hash(
        sonarr_client, torrent_hash, timeout, expected_status, check_for_errors, "Sonarr"
    )


def _find_queue_item_by_name(client, name_substring: str) -> Optional[dict]:
    """Generic find queue item by name substring (case-insensitive)."""
    queue = client.get_queue()
    name_lower = name_substring.lower()
    
    for item in queue.get('records', []):
        if name_lower in item.get('title', '').lower():
            return item
    return None


def find_queue_item_by_name(radarr_client, name_substring: str) -> Optional[dict]:
    """Find a Radarr queue item by name substring (case-insensitive)."""
    return _find_queue_item_by_name(radarr_client, name_substring)


def find_sonarr_queue_item_by_name(sonarr_client, name_substring: str) -> Optional[dict]:
    """Find a Sonarr queue item by name substring (case-insensitive)."""
    return _find_queue_item_by_name(sonarr_client, name_substring)


def remove_from_queue_by_name(radarr_client, name_substring: str) -> bool:
    """Find and remove a Radarr queue item by name substring."""
    item = find_queue_item_by_name(radarr_client, name_substring)
    if item:
        radarr_client.remove_from_queue(item['id'])
        return True
    return False


def remove_from_sonarr_queue_by_name(sonarr_client, name_substring: str) -> bool:
    """Find and remove a Sonarr queue item by name substring."""
    item = find_sonarr_queue_item_by_name(sonarr_client, name_substring)
    if item:
        sonarr_client.remove_from_queue(item['id'])
        return True
    return False


# ==============================================================================
# Deluge Utilities
# ==============================================================================

def wait_for_torrent_in_deluge(
    deluge_client,
    torrent_hash: str,
    timeout: int = 60,
    expected_state: Optional[str] = None
) -> dict:
    """
    Wait for a torrent to appear in Deluge with optional state check.
    
    Args:
        deluge_client: DelugeRPCClient instance
        torrent_hash: Info hash of the torrent
        timeout: Maximum seconds to wait
        expected_state: Optional state to wait for (e.g., 'Seeding')
    
    Returns:
        The torrent status dict
        
    Raises:
        TimeoutError: If torrent not found or doesn't reach expected state
    """
    last_state = None
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            torrents = deluge_client.core.get_torrents_status(
                {}, ['name', 'state', 'progress']
            )
            torrents = decode_bytes(torrents)
            
            if torrent_hash in torrents:
                torrent = torrents[torrent_hash]
                last_state = torrent.get('state')
                if expected_state is None or last_state == expected_state:
                    return torrent
        except Exception:
            pass
        time.sleep(2)
    
    error_msg = f"Torrent {torrent_hash[:8]}... not found in Deluge after {timeout}s"
    if expected_state:
        error_msg += f" (expected state: {expected_state}, last seen: {last_state})"
    raise TimeoutError(error_msg)


def wait_for_torrent_removed(
    deluge_client,
    torrent_hash: str,
    timeout: int = 120
) -> bool:
    """
    Wait for a torrent to be removed from Deluge.
    
    Args:
        deluge_client: DelugeRPCClient instance
        torrent_hash: Info hash of the torrent
        timeout: Maximum seconds to wait
    
    Returns:
        True if torrent was removed
        
    Raises:
        TimeoutError: If torrent still exists after timeout
    """
    def check():
        try:
            torrents = deluge_client.core.get_torrents_status({}, ['name'])
            torrents = decode_bytes(torrents)
            return torrent_hash not in torrents
        except Exception:
            return False
    
    return wait_for_condition(
        check,
        timeout=timeout,
        description=f"torrent {torrent_hash[:8]}... to be removed"
    )


def get_deluge_torrent_count(deluge_client) -> int:
    """Get the number of torrents in a Deluge client."""
    try:
        torrents = deluge_client.core.get_torrents_status({}, ['name'])
        return len(torrents)
    except Exception:
        return 0


def clear_deluge_torrents(deluge_client, remove_data: bool = True) -> int:
    """
    Remove all torrents from a Deluge client.
    
    Args:
        deluge_client: DelugeRPCClient instance
        remove_data: Whether to also delete downloaded data
        
    Returns:
        Number of torrents removed
    """
    removed = 0
    try:
        torrents = deluge_client.core.get_torrents_status({}, ['name'])
        for torrent_id in torrents.keys():
            try:
                deluge_client.core.remove_torrent(torrent_id, remove_data)
                removed += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to clear Deluge torrents: {e}")
    return removed


# ==============================================================================
# Transferarr Utilities
# ==============================================================================

def wait_for_transferarr_state(
    transferarr,
    torrent_name: str,
    expected_state: str,
    timeout: int = 120
) -> dict:
    """
    Wait for a torrent to reach a specific state in Transferarr.
    
    Args:
        transferarr: TransferarrManager instance
        torrent_name: Name (or substring) of the torrent
        expected_state: State to wait for (e.g., 'TARGET_SEEDING', 'HOME_SEEDING', 'COPYING')
        timeout: Maximum seconds to wait
    
    Returns:
        The torrent dict from Transferarr API
        
    Raises:
        TimeoutError: If torrent doesn't reach expected state
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        torrents = transferarr.get_torrents()
        for torrent in torrents:
            if torrent_name in torrent.get('name', ''):
                if torrent.get('state') == expected_state:
                    return torrent
        time.sleep(2)
    
    # Get current state for debugging
    torrents = transferarr.get_torrents()
    current_states = {t.get('name', 'UNKNOWN'): t.get('state', 'UNKNOWN') for t in torrents}
    
    raise TimeoutError(
        f"Torrent '{torrent_name}' did not reach state '{expected_state}' "
        f"after {timeout}s. Current tracked torrents: {current_states}"
    )


def find_torrent_in_transferarr(transferarr, torrent_name: str) -> Optional[dict]:
    """
    Find a tracked torrent by name substring.
    
    Args:
        transferarr: TransferarrManager instance
        torrent_name: Name or substring to search for
        
    Returns:
        Torrent dict if found, None otherwise
    """
    torrents = transferarr.get_torrents()
    for torrent in torrents:
        if torrent_name in torrent.get('name', ''):
            return torrent
    return None


# ==============================================================================
# Radarr Cleanup Utilities  
# ==============================================================================

def clear_radarr_state(radarr_client) -> dict:
    """
    Clear all movies and queue items from Radarr.
    
    Args:
        radarr_client: RadarrClient instance
        
    Returns:
        dict with 'queue_cleared' and 'movies_deleted' counts
    """
    result = {'queue_cleared': 0, 'movies_deleted': 0}
    
    # Clear queue first
    try:
        queue = radarr_client.get_queue()
        for item in queue.get('records', []):
            try:
                radarr_client.remove_from_queue(item['id'])
                result['queue_cleared'] += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to clear Radarr queue: {e}")
    
    # Delete all movies
    try:
        movies = radarr_client.get_movies()
        for movie in movies:
            try:
                radarr_client.delete_movie(movie['id'], delete_files=True)
                result['movies_deleted'] += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to clear Radarr movies: {e}")
    
    return result


def clear_sonarr_state(sonarr_client) -> dict:
    """
    Clear all series and queue items from Sonarr.
    
    Args:
        sonarr_client: SonarrClient instance
        
    Returns:
        dict with 'queue_cleared' and 'series_deleted' counts
    """
    result = {'queue_cleared': 0, 'series_deleted': 0}
    
    # Clear queue first
    try:
        queue = sonarr_client.get_queue()
        for item in queue.get('records', []):
            try:
                sonarr_client.remove_from_queue(item['id'])
                result['queue_cleared'] += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to clear Sonarr queue: {e}")
    
    # Delete all series
    try:
        series = sonarr_client.get_series()
        for s in series:
            try:
                sonarr_client.delete_series(s['id'], delete_files=True)
                result['series_deleted'] += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to clear Sonarr series: {e}")
        
    return result


def clear_mock_indexer_torrents() -> int:
    """
    Clear all torrents from the mock indexer (except validation torrents).
    
    This function uses docker exec to clear the torrents directory in the
    mock-indexer container, excluding the validation torrents needed for
    Radarr/Sonarr to maintain their indexer connection.
    
    Returns:
        Number of torrents removed
    """
    import subprocess
    
    try:
        # Count torrents before cleanup (excluding validation torrents)
        result = subprocess.run(
            ['docker', 'exec', 'test-mock-indexer', 'find', '/torrents', '-name', '*.torrent', '-type', 'f'],
            capture_output=True,
            text=True,
            timeout=10
        )
        all_torrents = [t for t in result.stdout.strip().split('\n') if t]
        # Keep validation torrents
        torrents_to_delete = [t for t in all_torrents if 'Validation' not in t]
        
        if not torrents_to_delete:
            return 0
        
        # Delete non-validation torrents
        for torrent_path in torrents_to_delete:
            subprocess.run(
                ['docker', 'exec', 'test-mock-indexer', 'rm', '-f', torrent_path],
                capture_output=True,
                timeout=5
            )
        
        return len(torrents_to_delete)
    except Exception as e:
        print(f"Warning: Failed to clear mock indexer: {e}")
        return 0


# ==============================================================================
# Movie Catalog for Tests
# ==============================================================================

class MovieCatalog:
    """
    A catalog of test movies that tracks usage to prevent collisions.
    
    Each test can request a movie, and the catalog ensures the same movie
    isn't used by multiple tests in the same session.
    
    Usage:
        movie = movie_catalog.get_movie()  # Get any available movie
        movie = movie_catalog.get_movie(key='inception')  # Get specific movie
        movie_catalog.reset()  # Reset for new test run (done automatically by fixture)
    """
    
    # Auto-generated from Wikidata - top box office movies 1985-2024
    # Generated by: python scripts/generate_movie_catalog.py
    # 
    # NOTE: Movies with years in their titles (like "Blade Runner 2049") are filtered out.
    # Radarr's release title parser gets confused when the torrent name includes
    # both the title year AND a release year (e.g., "Blade.Runner.2049.2017.1080p").
    # 
    # NOTE: Movies with "Episode" or "Part" in titles are also filtered out.
    # Radarr's clean title parser strips these, causing matching failures.
    MOVIES = {
        'avengers_endgame': {'title': 'Avengers: Endgame', 'tmdb_id': 299534, 'year': 2019},
        'avatar_the_way_of_water': {'title': 'Avatar: The Way of Water', 'tmdb_id': 76600, 'year': 2022},
        'avengers_infinity_war': {'title': 'Avengers: Infinity War', 'tmdb_id': 299536, 'year': 2018},
        'spiderman_no_way_home': {'title': 'Spider-Man: No Way Home', 'tmdb_id': 634649, 'year': 2021},
        'jurassic_world': {'title': 'Jurassic World', 'tmdb_id': 135397, 'year': 2015},
        'the_lion_king': {'title': 'The Lion King', 'tmdb_id': 420818, 'year': 2019},
        'the_avengers': {'title': 'The Avengers', 'tmdb_id': 24428, 'year': 2012},
        'furious_7': {'title': 'Furious 7', 'tmdb_id': 168259, 'year': 2015},
        'top_gun_maverick': {'title': 'Top Gun: Maverick', 'tmdb_id': 361743, 'year': 2022},
        'avengers_age_of_ultron': {'title': 'Avengers: Age of Ultron', 'tmdb_id': 99861, 'year': 2015},
        'black_panther': {'title': 'Black Panther', 'tmdb_id': 284054, 'year': 2018},
        'deadpool_wolverine': {'title': 'Deadpool & Wolverine', 'tmdb_id': 533535, 'year': 2024},
        'jurassic_world_fallen_kingdom': {'title': 'Jurassic World: Fallen Kingdom', 'tmdb_id': 351286, 'year': 2018},
        'beauty_and_the_beast': {'title': 'Beauty and the Beast', 'tmdb_id': 321612, 'year': 2017},
        'the_fate_of_the_furious': {'title': 'The Fate of the Furious', 'tmdb_id': 337339, 'year': 2017},
        'iron_man_3': {'title': 'Iron Man 3', 'tmdb_id': 68721, 'year': 2013},
        'captain_america_civil_war': {'title': 'Captain America: Civil War', 'tmdb_id': 271110, 'year': 2016},
        'the_lord_of_the_rings_the_return_of_the_king': {'title': 'The Lord of the Rings: The Return of the King', 'tmdb_id': 122, 'year': 2003},
        'spiderman_far_from_home': {'title': 'Spider-Man: Far From Home', 'tmdb_id': 429617, 'year': 2019},
        'captain_marvel': {'title': 'Captain Marvel', 'tmdb_id': 299537, 'year': 2019},
        #'transformers_dark_of_the_moon': {'title': 'Transformers: Dark of the Moon', 'tmdb_id': 38356, 'year': 2011},
        'transformers_age_of_extinction': {'title': 'Transformers: Age of Extinction', 'tmdb_id': 91314, 'year': 2014},
        'the_dark_knight_rises': {'title': 'The Dark Knight Rises', 'tmdb_id': 49026, 'year': 2012},
        'pirates_of_the_caribbean_dead_mans_chest': {'title': 'Pirates of the Caribbean: Dead Man\'s Chest', 'tmdb_id': 58, 'year': 2006},
        'rogue_one_a_star_wars_story': {'title': 'Rogue One: A Star Wars Story', 'tmdb_id': 330459, 'year': 2016},
        'pirates_of_the_caribbean_on_stranger_tides': {'title': 'Pirates of the Caribbean: On Stranger Tides', 'tmdb_id': 1865, 'year': 2011},
        'jurassic_park': {'title': 'Jurassic Park', 'tmdb_id': 329, 'year': 1993},
        'alice_in_wonderland': {'title': 'Alice in Wonderland', 'tmdb_id': 12155, 'year': 2010},
        'the_hobbit_an_unexpected_journey': {'title': 'The Hobbit: An Unexpected Journey', 'tmdb_id': 49051, 'year': 2012},
        'the_dark_knight': {'title': 'The Dark Knight', 'tmdb_id': 155, 'year': 2008},
        'jurassic_world_dominion': {'title': 'Jurassic World Dominion', 'tmdb_id': 507086, 'year': 2022},
        'harry_potter_and_the_philosophers_stone': {'title': 'Harry Potter and the Philosopher\'s Stone', 'tmdb_id': 671, 'year': 2001},
        'the_blind_side': {'title': 'The Blind Side', 'tmdb_id': 22881, 'year': 2009},
        'despicable_me_2': {'title': 'Despicable Me 2', 'tmdb_id': 93456, 'year': 2013},
        'the_jungle_book': {'title': 'The Jungle Book', 'tmdb_id': 278927, 'year': 2016},
        'jumanji_welcome_to_the_jungle': {'title': 'Jumanji: Welcome to the Jungle', 'tmdb_id': 353486, 'year': 2017},
        'pirates_of_the_caribbean_at_worlds_end': {'title': 'Pirates of the Caribbean: At World\'s End', 'tmdb_id': 285, 'year': 2007},
        'the_hobbit_the_desolation_of_smaug': {'title': 'The Hobbit: The Desolation of Smaug', 'tmdb_id': 57158, 'year': 2013},
        'the_hobbit_the_battle_of_the_five_armies': {'title': 'The Hobbit: The Battle of the Five Armies', 'tmdb_id': 122917, 'year': 2014},
        'doctor_strange_in_the_multiverse_of_madness': {'title': 'Doctor Strange in the Multiverse of Madness', 'tmdb_id': 453395, 'year': 2022},
        'harry_potter_and_the_order_of_the_phoenix': {'title': 'Harry Potter and the Order of the Phoenix', 'tmdb_id': 675, 'year': 2007},
        'the_lord_of_the_rings_the_two_towers': {'title': 'The Lord of the Rings: The Two Towers', 'tmdb_id': 121, 'year': 2002},
        'harry_potter_and_the_halfblood_prince': {'title': 'Harry Potter and the Half-Blood Prince', 'tmdb_id': 767, 'year': 2009},
        'bohemian_rhapsody': {'title': 'Bohemian Rhapsody', 'tmdb_id': 424694, 'year': 2018},
        'harry_potter_and_the_goblet_of_fire': {'title': 'Harry Potter and the Goblet of Fire', 'tmdb_id': 674, 'year': 2005},
        'spiderman_3': {'title': 'Spider-Man 3', 'tmdb_id': 559, 'year': 2007},
        'the_lord_of_the_rings_the_fellowship_of_the_ring': {'title': 'The Lord of the Rings: The Fellowship of the Ring', 'tmdb_id': 120, 'year': 2001},
        'ice_age_dawn_of_the_dinosaurs': {'title': 'Ice Age: Dawn of the Dinosaurs', 'tmdb_id': 8355, 'year': 2009},
        'spiderman_homecoming': {'title': 'Spider-Man: Homecoming', 'tmdb_id': 315635, 'year': 2017},
        'harry_potter_and_the_chamber_of_secrets': {'title': 'Harry Potter and the Chamber of Secrets', 'tmdb_id': 672, 'year': 2002},
        'ice_age_continental_drift': {'title': 'Ice Age: Continental Drift', 'tmdb_id': 57800, 'year': 2012},
        'the_secret_life_of_pets': {'title': 'The Secret Life of Pets', 'tmdb_id': 328111, 'year': 2016},
        'batman_v_superman_dawn_of_justice': {'title': 'Batman v Superman: Dawn of Justice', 'tmdb_id': 209112, 'year': 2016},
        'the_hunger_games_catching_fire': {'title': 'The Hunger Games: Catching Fire', 'tmdb_id': 101299, 'year': 2013},
        'guardians_of_the_galaxy_vol_2': {'title': 'Guardians of the Galaxy Vol. 2', 'tmdb_id': 283995, 'year': 2017},
        'black_panther_wakanda_forever': {'title': 'Black Panther: Wakanda Forever', 'tmdb_id': 505642, 'year': 2022},
        'thor_ragnarok': {'title': 'Thor: Ragnarok', 'tmdb_id': 284053, 'year': 2017},
        'guardians_of_the_galaxy_vol_3': {'title': 'Guardians of the Galaxy Vol. 3', 'tmdb_id': 447365, 'year': 2023},
        'transformers_revenge_of_the_fallen': {'title': 'Transformers: Revenge of the Fallen', 'tmdb_id': 8373, 'year': 2009},
        'inside_out_2': {'title': 'Inside Out 2', 'tmdb_id': 1022789, 'year': 2024},
        'wonder_woman': {'title': 'Wonder Woman', 'tmdb_id': 297762, 'year': 2017},
        'independence_day': {'title': 'Independence Day', 'tmdb_id': 602, 'year': 1996},
        'fantastic_beasts_and_where_to_find_them': {'title': 'Fantastic Beasts and Where to Find Them', 'tmdb_id': 259316, 'year': 2016},
        'jumanji_the_next_level': {'title': 'Jumanji: The Next Level', 'tmdb_id': 512200, 'year': 2019},
        'harry_potter_and_the_prisoner_of_azkaban': {'title': 'Harry Potter and the Prisoner of Azkaban', 'tmdb_id': 673, 'year': 2004},
        'pirates_of_the_caribbean_dead_men_tell_no_tales': {'title': 'Pirates of the Caribbean: Dead Men Tell no Tales', 'tmdb_id': 166426, 'year': 2017},
        'mission_impossible_fallout': {'title': 'Mission: Impossible – Fallout', 'tmdb_id': 353081, 'year': 2018},
        'indiana_jones_and_the_kingdom_of_the_crystal_skull': {'title': 'Indiana Jones and the Kingdom of the Crystal Skull', 'tmdb_id': 217, 'year': 2008},
        'spiderman_2': {'title': 'Spider-Man 2', 'tmdb_id': 558, 'year': 2004},
        'fast_furious_6': {'title': 'Fast & Furious 6', 'tmdb_id': 82992, 'year': 2013},
        'deadpool_2': {'title': 'Deadpool 2', 'tmdb_id': 383498, 'year': 2018},
        'guardians_of_the_galaxy': {'title': 'Guardians of the Galaxy', 'tmdb_id': 118340, 'year': 2014},
        'the_batman': {'title': 'The Batman', 'tmdb_id': 414906, 'year': 2022},
        'thor_love_and_thunder': {'title': 'Thor: Love and Thunder', 'tmdb_id': 616037, 'year': 2022},
        'minions_the_rise_of_gru': {'title': 'Minions: The Rise of Gru', 'tmdb_id': 438148, 'year': 2022},
        'the_da_vinci_code': {'title': 'The Da Vinci Code', 'tmdb_id': 591, 'year': 2006},
        'hobbs_shaw': {'title': 'Hobbs & Shaw', 'tmdb_id': 384018, 'year': 2019},
        'the_amazing_spiderman': {'title': 'The Amazing Spider-Man', 'tmdb_id': 1930, 'year': 2012},
        'suicide_squad': {'title': 'Suicide Squad', 'tmdb_id': 297761, 'year': 2016},
        'xmen_days_of_future_past': {'title': 'X-Men: Days of Future Past', 'tmdb_id': 127585, 'year': 2014},
        'the_chronicles_of_narnia_the_lion_the_witch_and_the_wardrobe': {'title': 'The Chronicles of Narnia: The Lion, the Witch and the Wardrobe', 'tmdb_id': 411, 'year': 2005},
        'monsters_university': {'title': 'Monsters University', 'tmdb_id': 62211, 'year': 2013},
        'the_matrix_reloaded': {'title': 'The Matrix Reloaded', 'tmdb_id': 604, 'year': 2003},
        'captain_america_the_winter_soldier': {'title': 'Captain America: The Winter Soldier', 'tmdb_id': 100402, 'year': 2014},
        'the_twilight_saga_new_moon': {'title': 'The Twilight Saga: New Moon', 'tmdb_id': 18239, 'year': 2009},
        'dawn_of_the_planet_of_the_apes': {'title': 'Dawn of the Planet of the Apes', 'tmdb_id': 119450, 'year': 2014},
        'the_amazing_spiderman_2': {'title': 'The Amazing Spider-Man 2', 'tmdb_id': 102382, 'year': 2014},
        'the_twilight_saga_eclipse': {'title': 'The Twilight Saga: Eclipse', 'tmdb_id': 24021, 'year': 2010},
        'the_hunger_games': {'title': 'The Hunger Games', 'tmdb_id': 70160, 'year': 2012},
        'mission_impossible_ghost_protocol': {'title': 'Mission: Impossible – Ghost Protocol', 'tmdb_id': 56292, 'year': 2011},
        'mission_impossible_rogue_nation': {'title': 'Mission: Impossible – Rogue Nation', 'tmdb_id': 177677, 'year': 2015},
        'forrest_gump': {'title': 'Forrest Gump', 'tmdb_id': 13, 'year': 1994},
        'doctor_strange': {'title': 'Doctor Strange', 'tmdb_id': 284052, 'year': 2016},
        'the_sixth_sense': {'title': 'The Sixth Sense', 'tmdb_id': 745, 'year': 1999},
        'man_of_steel': {'title': 'Man of Steel', 'tmdb_id': 49521, 'year': 2013},
        'ice_age_the_meltdown': {'title': 'Ice Age: The Meltdown', 'tmdb_id': 950, 'year': 2006},
        'justice_league': {'title': 'Justice League', 'tmdb_id': 141052, 'year': 2017},
        'fantastic_beasts_the_crimes_of_grindelwald': {'title': 'Fantastic Beasts: The Crimes of Grindelwald', 'tmdb_id': 338952, 'year': 2018},
        'pirates_of_the_caribbean_the_curse_of_the_black_pearl': {'title': 'Pirates of the Caribbean: The Curse of the Black Pearl', 'tmdb_id': 22, 'year': 2003},
        'thor_the_dark_world': {'title': 'Thor: The Dark World', 'tmdb_id': 76338, 'year': 2013},
        'the_martian': {'title': 'The Martian', 'tmdb_id': 286217, 'year': 2015},
        'fast_five': {'title': 'Fast Five', 'tmdb_id': 51497, 'year': 2011},
        'men_in_black_3': {'title': 'Men in Black 3', 'tmdb_id': 41154, 'year': 2012},
        'iron_man_2': {'title': 'Iron Man 2', 'tmdb_id': 10138, 'year': 2010},
        'antman_and_the_wasp': {'title': 'Ant-Man and the Wasp', 'tmdb_id': 363088, 'year': 2018},
        'the_lost_world_jurassic_park': {'title': 'The Lost World: Jurassic Park', 'tmdb_id': 330, 'year': 1997},
        'the_passion_of_the_christ': {'title': 'The Passion of the Christ', 'tmdb_id': 615, 'year': 2004},
        'mamma_mia': {'title': 'Mamma Mia!', 'tmdb_id': 11631, 'year': 2008},
        'casino_royale': {'title': 'Casino Royale', 'tmdb_id': 36557, 'year': 2006},
        'life_of_pi': {'title': 'Life of Pi', 'tmdb_id': 87827, 'year': 2012},
        'transformers_the_last_knight': {'title': 'Transformers: The Last Knight', 'tmdb_id': 335988, 'year': 2017},
        'war_of_the_worlds': {'title': 'War of the Worlds', 'tmdb_id': 74, 'year': 2005},
        'quantum_of_solace': {'title': 'Quantum of Solace', 'tmdb_id': 10764, 'year': 2008},
        'men_in_black': {'title': 'Men in Black', 'tmdb_id': 607, 'year': 1997},
        'iron_man': {'title': 'Iron Man', 'tmdb_id': 1726, 'year': 2008},
        'i_am_legend': {'title': 'I Am Legend', 'tmdb_id': 6479, 'year': 2007},
        'ready_player_one': {'title': 'Ready Player One', 'tmdb_id': 333339, 'year': 2018},
        'night_at_the_museum': {'title': 'Night at the Museum', 'tmdb_id': 1593, 'year': 2006},
        'fifty_shades_of_grey': {'title': 'Fifty Shades of Grey', 'tmdb_id': 216015, 'year': 2015},
        'the_little_mermaid': {'title': 'The Little Mermaid', 'tmdb_id': 447277, 'year': 2023},
        'kong_skull_island': {'title': 'Kong: Skull Island', 'tmdb_id': 293167, 'year': 2017},
        'the_smurfs': {'title': 'The Smurfs', 'tmdb_id': 41513, 'year': 2011},
        'cars_2': {'title': 'Cars 2', 'tmdb_id': 49013, 'year': 2011},
        'king_kong': {'title': 'King Kong', 'tmdb_id': 254, 'year': 2005},
        'american_sniper': {'title': 'American Sniper', 'tmdb_id': 190859, 'year': 2014},
        'mission_impossible_2': {'title': 'Mission: Impossible 2', 'tmdb_id': 955, 'year': 2000},
        'xmen_apocalypse': {'title': 'X-Men: Apocalypse', 'tmdb_id': 246655, 'year': 2016},
        'sherlock_holmes_a_game_of_shadows': {'title': 'Sherlock Holmes: A Game of Shadows', 'tmdb_id': 58574, 'year': 2011},
        'the_day_after_tomorrow': {'title': 'The Day After Tomorrow', 'tmdb_id': 435, 'year': 2004},
        'world_war_z': {'title': 'World War Z', 'tmdb_id': 72190, 'year': 2013},
        'the_revenant': {'title': 'The Revenant', 'tmdb_id': 281957, 'year': 2015},
        'the_meg': {'title': 'The Meg', 'tmdb_id': 345940, 'year': 2018},
        'sherlock_holmes': {'title': 'Sherlock Holmes', 'tmdb_id': 10528, 'year': 2009},
        'terminator_2_judgment_day': {'title': 'Terminator 2: Judgment Day', 'tmdb_id': 280, 'year': 1991},
        'meet_the_fockers': {'title': 'Meet the Fockers', 'tmdb_id': 693, 'year': 2004},
        'the_grinch': {'title': 'The Grinch', 'tmdb_id': 360920, 'year': 2018},
        'rio_2': {'title': 'Rio 2', 'tmdb_id': 172385, 'year': 2014},
        'venom_let_there_be_carnage': {'title': 'Venom: Let There Be Carnage', 'tmdb_id': 580489, 'year': 2021},
        'teenage_mutant_ninja_turtles': {'title': 'Teenage Mutant Ninja Turtles', 'tmdb_id': 98566, 'year': 2014},
        'oz_the_great_and_powerful': {'title': 'Oz the Great and Powerful', 'tmdb_id': 68728, 'year': 2013},
        'clash_of_the_titans': {'title': 'Clash of the Titans', 'tmdb_id': 18823, 'year': 2010},
        'war_for_the_planet_of_the_apes': {'title': 'War for the Planet of the Apes', 'tmdb_id': 281338, 'year': 2017},
        'angels_demons': {'title': 'Angels & Demons', 'tmdb_id': 13448, 'year': 2009},
        'bruce_almighty': {'title': 'Bruce Almighty', 'tmdb_id': 310, 'year': 2003},
        'saving_private_ryan': {'title': 'Saving Private Ryan', 'tmdb_id': 857, 'year': 1998},
        'rise_of_the_planet_of_the_apes': {'title': 'Rise of the Planet of the Apes', 'tmdb_id': 61791, 'year': 2011},
        'mr_mrs_smith': {'title': 'Mr. & Mrs. Smith', 'tmdb_id': 787, 'year': 2005},
        'home_alone': {'title': 'Home Alone', 'tmdb_id': 771, 'year': 1990},
        'antman_and_the_wasp_quantumania': {'title': 'Ant-Man and the Wasp: Quantumania', 'tmdb_id': 640146, 'year': 2023},
        'charlie_and_the_chocolate_factory': {'title': 'Charlie and the Chocolate Factory', 'tmdb_id': 118, 'year': 2005},
        'indiana_jones_and_the_last_crusade': {'title': 'Indiana Jones and the Last Crusade', 'tmdb_id': 89, 'year': 1989},
        'san_andreas': {'title': 'San Andreas', 'tmdb_id': 254128, 'year': 2015},
        'it_chapter_two': {'title': 'It: Chapter Two', 'tmdb_id': 474350, 'year': 2019},
        'la_la_land': {'title': 'La La Land', 'tmdb_id': 313369, 'year': 2016},
        'wreckit_ralph': {'title': 'Wreck-It Ralph', 'tmdb_id': 82690, 'year': 2012},
        'the_lego_movie': {'title': 'The LEGO Movie', 'tmdb_id': 137106, 'year': 2014},
        'godzilla_vs_kong': {'title': 'Godzilla vs. Kong', 'tmdb_id': 399566, 'year': 2021},
        'the_hangover': {'title': 'The Hangover', 'tmdb_id': 18785, 'year': 2009},
        'star_trek_into_darkness': {'title': 'Star Trek Into Darkness', 'tmdb_id': 54138, 'year': 2013},
        'the_matrix': {'title': 'The Matrix', 'tmdb_id': 603, 'year': 1999},
        'pretty_woman': {'title': 'Pretty Woman', 'tmdb_id': 114, 'year': 1990},
        'xmen_the_last_stand': {'title': 'X-Men: The Last Stand', 'tmdb_id': 36668, 'year': 2006},
        'mission_impossible': {'title': 'Mission: Impossible', 'tmdb_id': 954, 'year': 1996},
        'national_treasure_book_of_secrets': {'title': 'National Treasure: Book of Secrets', 'tmdb_id': 6637, 'year': 2007},
        'the_last_samurai': {'title': 'The Last Samurai', 'tmdb_id': 616, 'year': 2003},
        'oceans_eleven': {'title': 'Ocean\'s Eleven', 'tmdb_id': 161, 'year': 2001},
        'detective_pikachu': {'title': 'Detective Pikachu', 'tmdb_id': 447404, 'year': 2019},
        'pearl_harbor': {'title': 'Pearl Harbor', 'tmdb_id': 676, 'year': 2001},
        'men_in_black_ii': {'title': 'Men in Black II', 'tmdb_id': 608, 'year': 2002},
        'the_bourne_ultimatum': {'title': 'The Bourne Ultimatum', 'tmdb_id': 2503, 'year': 2007},
        'alvin_and_the_chipmunks_the_squeakquel': {'title': 'Alvin and the Chipmunks: The Squeakquel', 'tmdb_id': 23398, 'year': 2009},
        'les_misérables': {'title': 'Les Misérables', 'tmdb_id': 82695, 'year': 2012},
        'mrs_doubtfire': {'title': 'Mrs. Doubtfire', 'tmdb_id': 788, 'year': 1993},
        'terminator_genisys': {'title': 'Terminator Genisys', 'tmdb_id': 87101, 'year': 2015},
        'the_greatest_showman': {'title': 'The Greatest Showman', 'tmdb_id': 316029, 'year': 2017},
        'terminator_3_rise_of_the_machines': {'title': 'Terminator 3: Rise of the Machines', 'tmdb_id': 296, 'year': 2003},
        'the_mummy_returns': {'title': 'The Mummy Returns', 'tmdb_id': 1734, 'year': 2001},
        'shangchi_and_the_legend_of_the_ten_rings': {'title': 'Shang-Chi and the Legend of the Ten Rings', 'tmdb_id': 566525, 'year': 2021},
        'die_another_day': {'title': 'Die Another Day', 'tmdb_id': 36669, 'year': 2002},
        'a_star_is_born': {'title': 'A Star Is Born', 'tmdb_id': 332562, 'year': 2018},
        'cast_away': {'title': 'Cast Away', 'tmdb_id': 8358, 'year': 2000},
        'the_matrix_revolutions': {'title': 'The Matrix Revolutions', 'tmdb_id': 605, 'year': 2003},
        'django_unchained': {'title': 'Django Unchained', 'tmdb_id': 68718, 'year': 2012},
        'beetlejuice_beetlejuice': {'title': 'Beetlejuice Beetlejuice', 'tmdb_id': 917496, 'year': 2024},
        'dances_with_wolves': {'title': 'Dances with Wolves', 'tmdb_id': 581, 'year': 1990},
        'the_chronicles_of_narnia_prince_caspian': {'title': 'The Chronicles of Narnia: Prince Caspian', 'tmdb_id': 2454, 'year': 2008},
        'bad_boys_for_life': {'title': 'Bad Boys for Life', 'tmdb_id': 38700, 'year': 2020},
        'the_mummy': {'title': 'The Mummy', 'tmdb_id': 564, 'year': 1999},
        'the_chronicles_of_narnia_the_voyage_of_the_dawn_treader': {'title': 'The Chronicles of Narnia: The Voyage of the Dawn Treader', 'tmdb_id': 10140, 'year': 2010},
        'jason_bourne': {'title': 'Jason Bourne', 'tmdb_id': 324668, 'year': 2016},
        'sex_and_the_city': {'title': 'Sex and the City', 'tmdb_id': 4564, 'year': 2008},
        'the_wolverine': {'title': 'The Wolverine', 'tmdb_id': 76170, 'year': 2013},
        'kingsman_the_secret_service': {'title': 'Kingsman: The Secret Service', 'tmdb_id': 207703, 'year': 2014},
        'night_at_the_museum_battle_of_the_smithsonian': {'title': 'Night at the Museum: Battle of the Smithsonian', 'tmdb_id': 18360, 'year': 2009},
        'the_bodyguard': {'title': 'The Bodyguard', 'tmdb_id': 619, 'year': 1992},
        'pacific_rim': {'title': 'Pacific Rim', 'tmdb_id': 68726, 'year': 2013},
        'kingsman_the_golden_circle': {'title': 'Kingsman: The Golden Circle', 'tmdb_id': 343668, 'year': 2017},
        'the_mummy_2017': {'title': 'The Mummy', 'tmdb_id': 282035, 'year': 2017},
        'ice_age_collision_course': {'title': 'Ice Age: Collision Course', 'tmdb_id': 278154, 'year': 2016},
        'fantastic_beasts_the_secrets_of_dumbledore': {'title': 'Fantastic Beasts: The Secrets of Dumbledore', 'tmdb_id': 338953, 'year': 2022},
        'the_mummy_tomb_of_the_dragon_emperor': {'title': 'The Mummy: Tomb of the Dragon Emperor', 'tmdb_id': 1735, 'year': 2008},
        'sonic_the_hedgehog_2': {'title': 'Sonic the Hedgehog 2', 'tmdb_id': 675353, 'year': 2022},
        'tron_legacy': {'title': 'Tron: Legacy', 'tmdb_id': 20526, 'year': 2010},
        'mission_impossible_iii': {'title': 'Mission: Impossible III', 'tmdb_id': 956, 'year': 2006},
        'snow_white_and_the_huntsman': {'title': 'Snow White and the Huntsman', 'tmdb_id': 58595, 'year': 2012},
        'mamma_mia_here_we_go_again': {'title': 'Mamma Mia! Here We Go Again', 'tmdb_id': 458423, 'year': 2018},
        'black_adam': {'title': 'Black Adam', 'tmdb_id': 436270, 'year': 2022},
        'solo_a_star_wars_story': {'title': 'Solo: A Star Wars Story', 'tmdb_id': 348350, 'year': 2018},
        'the_wolf_of_wall_street': {'title': 'The Wolf of Wall Street', 'tmdb_id': 106646, 'year': 2013},
        'superman_returns': {'title': 'Superman Returns', 'tmdb_id': 1452, 'year': 2006},
        'robin_hood_prince_of_thieves': {'title': 'Robin Hood: Prince of Thieves', 'tmdb_id': 8367, 'year': 1991},
        'independence_day_resurgence': {'title': 'Independence Day: Resurgence', 'tmdb_id': 47933, 'year': 2016},
        'live_free_or_die_hard': {'title': 'Live Free or Die Hard', 'tmdb_id': 1571, 'year': 2007},
        'godzilla_king_of_the_monsters': {'title': 'Godzilla: King of the Monsters', 'tmdb_id': 373571, 'year': 2019},
        'star_trek': {'title': 'Star Trek', 'tmdb_id': 13475, 'year': 2009},
        'happy_feet': {'title': 'Happy Feet', 'tmdb_id': 9836, 'year': 2006},
        'cars_3': {'title': 'Cars 3', 'tmdb_id': 260514, 'year': 2017},
        'back_to_the_future': {'title': 'Back to the Future', 'tmdb_id': 105, 'year': 1985},
        'fifty_shades_darker': {'title': 'Fifty Shades Darker', 'tmdb_id': 341174, 'year': 2017},
        'black_widow': {'title': 'Black Widow', 'tmdb_id': 497698, 'year': 2021},
        'true_lies': {'title': 'True Lies', 'tmdb_id': 36955, 'year': 1994},
        'mad_max_fury_road': {'title': 'Mad Max: Fury Road', 'tmdb_id': 76341, 'year': 2015},
        'gi_joe_retaliation': {'title': 'G.I. Joe: Retaliation', 'tmdb_id': 72559, 'year': 2013},
        'once_upon_a_time_in_hollywood': {'title': 'Once Upon a Time in Hollywood', 'tmdb_id': 466272, 'year': 2019},
        'what_women_want': {'title': 'What Women Want', 'tmdb_id': 3981, 'year': 2000},
        'batman_begins': {'title': 'Batman Begins', 'tmdb_id': 272, 'year': 2005},
        'xmen_origins_wolverine': {'title': 'X-Men Origins: Wolverine', 'tmdb_id': 2080, 'year': 2009},
        'penguins_of_madagascar': {'title': 'Penguins of Madagascar', 'tmdb_id': 270946, 'year': 2014},
        'the_golden_compass': {'title': 'The Golden Compass', 'tmdb_id': 2268, 'year': 2007},
        'fifty_shades_freed': {'title': 'Fifty Shades Freed', 'tmdb_id': 337167, 'year': 2018},
        'terminator_salvation': {'title': 'Terminator Salvation', 'tmdb_id': 534, 'year': 2009},
        'captain_america_the_first_avenger': {'title': 'Captain America: The First Avenger', 'tmdb_id': 1771, 'year': 2011},
        'edge_of_tomorrow': {'title': 'Edge of Tomorrow', 'tmdb_id': 137113, 'year': 2014},
        'theres_something_about_mary': {'title': 'There\'s Something About Mary', 'tmdb_id': 544, 'year': 1998},
        'gone_girl': {'title': 'Gone Girl', 'tmdb_id': 210577, 'year': 2014},
        'the_fugitive': {'title': 'The Fugitive', 'tmdb_id': 5503, 'year': 1993},
        'jurassic_park_iii': {'title': 'Jurassic Park III', 'tmdb_id': 331, 'year': 2001},
        'my_big_fat_greek_wedding': {'title': 'My Big Fat Greek Wedding', 'tmdb_id': 8346, 'year': 2002},
        'die_hard_with_a_vengeance': {'title': 'Die Hard with a Vengeance', 'tmdb_id': 1572, 'year': 1995},
        'the_nun': {'title': 'The Nun', 'tmdb_id': 439079, 'year': 2018},
        'notting_hill': {'title': 'Notting Hill', 'tmdb_id': 509, 'year': 1999},
        'spiderman_into_the_spiderverse': {'title': 'Spider-Man: Into the Spider-Verse', 'tmdb_id': 324857, 'year': 2018},
        'night_at_the_museum_secret_of_the_tomb': {'title': 'Night at the Museum: Secret of the Tomb', 'tmdb_id': 181533, 'year': 2014},
        'fast_furious': {'title': 'Fast & Furious', 'tmdb_id': 13804, 'year': 2009},
        'oceans_twelve': {'title': 'Ocean\'s Twelve', 'tmdb_id': 163, 'year': 2004},
        'planet_of_the_apes': {'title': 'Planet of the Apes', 'tmdb_id': 869, 'year': 2001},
        'the_world_is_not_enough': {'title': 'The World Is Not Enough', 'tmdb_id': 36643, 'year': 1999},
        'alvin_and_the_chipmunks': {'title': 'Alvin and the Chipmunks', 'tmdb_id': 6477, 'year': 2007},
        'the_karate_kid': {'title': 'The Karate Kid', 'tmdb_id': 38575, 'year': 2010},
        'home_alone_2_lost_in_new_york': {'title': 'Home Alone 2: Lost in New York', 'tmdb_id': 772, 'year': 1992},
    }
    
    def __init__(self):
        self._used_movies: set = set()
        self._movie_keys = list(self.MOVIES.keys())
        self._next_index = 0
    
    def reset(self):
        """Reset the catalog for a new test run."""
        self._used_movies.clear()
        self._next_index = 0
    
    def get_movie(self, key: str = None) -> dict:
        """
        Get a movie from the catalog.
        
        Args:
            key: Optional specific movie key. If not provided, returns next available movie.
        
        Returns:
            dict with 'title', 'tmdb_id', 'year', and 'key' fields
        
        Raises:
            ValueError: If specific key is already used or no movies available
        """
        if key is not None:
            # Specific movie requested
            if key not in self.MOVIES:
                raise ValueError(f"Unknown movie key: {key}. Available: {list(self.MOVIES.keys())}")
            if key in self._used_movies:
                raise ValueError(
                    f"Movie '{key}' already used in this test session. "
                    f"Used movies: {self._used_movies}. "
                    f"Use get_movie() without a key to get the next available movie."
                )
            self._used_movies.add(key)
            movie = self.MOVIES[key].copy()
            movie['key'] = key
            return movie
        
        # Get next available movie
        while self._next_index < len(self._movie_keys):
            key = self._movie_keys[self._next_index]
            self._next_index += 1
            if key not in self._used_movies:
                self._used_movies.add(key)
                movie = self.MOVIES[key].copy()
                movie['key'] = key
                return movie
        
        raise ValueError(
            f"No more movies available! All {len(self.MOVIES)} movies have been used. "
            f"Add more movies to MovieCatalog.MOVIES or reset the catalog."
        )
    
    def get_movies(self, count: int) -> list:
        """
        Get multiple movies at once.
        
        Args:
            count: Number of movies needed
        
        Returns:
            List of movie dicts
        """
        return [self.get_movie() for _ in range(count)]
    
    @property
    def available_count(self) -> int:
        """Number of movies still available."""
        return len(self.MOVIES) - len(self._used_movies)
    
    @property 
    def used_movies(self) -> set:
        """Set of movie keys that have been used."""
        return self._used_movies.copy()


class ShowCatalog:
    """
    A catalog of TV shows for testing Sonarr integration.
    
    This class manages a list of shows and ensures each test gets a unique show
    to avoid collisions in Sonarr.
    """
    
    def __init__(self, shows_dict: dict):
        self.SHOWS = shows_dict
        self._used_keys: set = set()
        self._show_keys = list(self.SHOWS.keys())
        self._next_index = 0
    
    def reset(self):
        """Reset the catalog for a new test run."""
        self._used_keys.clear()
        self._next_index = 0
        
    def get_show(self, key: str = None) -> dict:
        """
        Get a show from the catalog.
        
        Args:
            key: Optional key of the show to get. If not provided, gets the next available.
            
        Returns:
            A dictionary with show metadata (title, tvdb_id, etc.)
            
        Raises:
            IndexError: If all shows have been used or key not found
        """
        if key:
            if key not in self.SHOWS:
                raise IndexError(f"Show key '{key}' not found in catalog")
            show_key = key
        else:
            if self._next_index >= len(self._show_keys):
                raise IndexError("All shows in catalog have been used")
            show_key = self._show_keys[self._next_index]
            self._next_index += 1
            
        self._used_keys.add(show_key)
        
        show = self.SHOWS[show_key].copy()
        show['key'] = show_key
        return show
    
    @property 
    def used_keys(self) -> set:
        """Set of show keys that have been used."""
        return self._used_keys.copy()


# Global singleton instance
movie_catalog = MovieCatalog()

SHOWS = {
    'washington_week_with_the_atlantic': {
        'title': 'Washington Week with The Atlantic',
        'tvdb_id': 316836,
        'year': 2023,
        'num_seasons': 50,
        'num_episodes': 2000
    },
    'wwe_raw': {
        'title': 'WWE Raw',
        'tvdb_id': 76779,
        'year': 1993,
        'num_seasons': 31,
        'num_episodes': 1671
    },
    'the_tonight_show_starring_jimmy_fallon': {
        'title': 'The Tonight Show Starring Jimmy Fallon',
        'tvdb_id': 270261,
        'year': 2014,
        'num_seasons': 8,
        'num_episodes': 1598
    },
    'firing_line': {
        'title': 'Firing Line',
        'tvdb_id': 283183,
        'year': 2018,
        'num_seasons': 34,
        'num_episodes': 1504
    },
    'wwe_smackdown': {
        'title': 'WWE SmackDown',
        'tvdb_id': 75640,
        'year': 1999,
        'num_seasons': 25,
        'num_episodes': 1347
    },
    'wwe_nxt': {
        'title': 'WWE NXT',
        'tvdb_id': 144541,
        'year': 2010,
        'num_seasons': 12,
        'num_episodes': 777
    },
    'house_hunters': {
        'title': 'House Hunters',
        'tvdb_id': 73182,
        'year': 1999,
        'num_seasons': 13,
        'num_episodes': 538
    },
    'californias_gold': {
        'title': 'California\'s Gold',
        'tvdb_id': 279999,
        'year': 1991,
        'num_seasons': 24,
        'num_episodes': 443
    },
    'wwe_main_event': {
        'title': 'WWE Main Event',
        'tvdb_id': 374470,
        'year': 2012,
        'num_seasons': 12,
        'num_episodes': 439
    },
    'ecw_hardcore_tv': {
        'title': 'ECW Hardcore TV',
        'tvdb_id': 76781,
        'year': 1993,
        'num_seasons': 8,
        'num_episodes': 401
    },
    'historys_mysteries': {
        'title': 'History\'s Mysteries',
        'tvdb_id': 83330,
        'year': 1998,
        'num_seasons': 15,
        'num_episodes': 317
    },
    'the_hoobs': {
        'title': 'The Hoobs',
        'tvdb_id': 82032,
        'year': 2001,
        'num_seasons': 5,
        'num_episodes': 250
    },
    'behind_the_music': {
        'title': 'Behind the Music',
        'tvdb_id': 75644,
        'year': 1997,
        'num_seasons': 0,
        'num_episodes': 208
    },
    'the_flash': {
        'title': 'The Flash',
        'tvdb_id': 279121,
        'year': 2015,
        'num_seasons': 9,
        'num_episodes': 184
    },
    'graveyard_carz': {
        'title': 'Graveyard Carz',
        'tvdb_id': 260259,
        'year': 2012,
        'num_seasons': 14,
        'num_episodes': 175
    },
    'love_it_or_list_it': {
        'title': 'Love It or List It',
        'tvdb_id': 262419,
        'year': 2008,
        'num_seasons': 10,
        'num_episodes': 130
    },
    'my_crazy_ex': {
        'title': 'My Crazy Ex',
        'tvdb_id': 283194,
        'year': 2014,
        'num_seasons': 5,
        'num_episodes': 111
    },
    'legends_of_tomorrow': {
        'title': 'Legends of Tomorrow',
        'tvdb_id': 295760,
        'year': 2016,
        'num_seasons': 7,
        'num_episodes': 110
    },
    'teen_wolf': {
        'title': 'Teen Wolf',
        'tvdb_id': 175001,
        'year': 2022,
        'num_seasons': 6,
        'num_episodes': 100
    },
    'adventures_in_wonderland': {
        'title': 'Adventures in Wonderland',
        'tvdb_id': 70676,
        'year': 1992,
        'num_seasons': 3,
        'num_episodes': 100
    },
    'hannah_montana': {
        'title': 'Hannah Montana',
        'tvdb_id': 79317,
        'year': 2006,
        'num_seasons': 4,
        'num_episodes': 98
    },
    'the_jace_hall_show': {
        'title': 'The Jace Hall Show',
        'tvdb_id': 262801,
        'year': 2008,
        'num_seasons': 5,
        'num_episodes': 94
    },
    'motorz_tv': {
        'title': 'Motorz TV',
        'tvdb_id': 315409,
        'year': 2008,
        'num_seasons': 6,
        'num_episodes': 83
    },
    'mystery_hunters': {
        'title': 'Mystery Hunters',
        'tvdb_id': 71537,
        'year': 2002,
        'num_seasons': 4,
        'num_episodes': 78
    },
    'the_wildlife_docs': {
        'title': 'The Wildlife Docs',
        'tvdb_id': 276614,
        'year': 2013,
        'num_seasons': 3,
        'num_episodes': 78
    },
    'shake_it_up': {
        'title': 'Shake It Up',
        'tvdb_id': 205251,
        'year': 2011,
        'num_seasons': 3,
        'num_episodes': 75
    },
    'the_americans': {
        'title': 'The Americans',
        'tvdb_id': 261690,
        'year': 2014,
        'num_seasons': 6,
        'num_episodes': 75
    },
    'kc_undercover': {
        'title': 'K.C. Undercover',
        'tvdb_id': 285824,
        'year': 2015,
        'num_seasons': 3,
        'num_episodes': 75
    },
    'soul_food': {
        'title': 'Soul Food',
        'tvdb_id': 81878,
        'year': 2000,
        'num_seasons': 5,
        'num_episodes': 74
    },
    'i_am_jazz': {
        'title': 'I Am Jazz',
        'tvdb_id': 297378,
        'year': 2015,
        'num_seasons': 8,
        'num_episodes': 73
    },
    'the_profit': {
        'title': 'The Profit',
        'tvdb_id': 271671,
        'year': 2013,
        'num_seasons': 8,
        'num_episodes': 72
    },
    'dog_with_a_blog': {
        'title': 'Dog with a Blog',
        'tvdb_id': 263203,
        'year': 2013,
        'num_seasons': 3,
        'num_episodes': 68
    },
    'yo_gabba_gabba': {
        'title': 'Yo Gabba Gabba!',
        'tvdb_id': 80964,
        'year': 2024,
        'num_seasons': 4,
        'num_episodes': 66
    },
    'spyder_games': {
        'title': 'Spyder Games',
        'tvdb_id': 272994,
        'year': 2001,
        'num_seasons': 1,
        'num_episodes': 65
    },
    'small_talk': {
        'title': 'Small Talk',
        'tvdb_id': 424872,
        'year': 1996,
        'num_seasons': 1,
        'num_episodes': 65
    },
    'biz_kid': {
        'title': 'biz KID$',
        'tvdb_id': 295982,
        'year': 2008,
        'num_seasons': 5,
        'num_episodes': 65
    },
    'the_inspectors': {
        'title': 'The Inspectors',
        'tvdb_id': 301385,
        'year': 1998,
        'num_seasons': 3,
        'num_episodes': 63
    },
    'mexicos_next_top_model': {
        'title': 'Mexico\'s Next Top Model',
        'tvdb_id': 331399,
        'year': 2009,
        'num_seasons': 5,
        'num_episodes': 62
    },
    'blackboxtv_presents': {
        'title': 'BlackBoxTV Presents',
        'tvdb_id': 348398,
        'year': 2010,
        'num_seasons': 5,
        'num_episodes': 61
    },
    'no_you_shut_up': {
        'title': 'No, You Shut Up!',
        'tvdb_id': 281774,
        'year': 2013,
        'num_seasons': 4,
        'num_episodes': 58
    },
    'sea_rescue': {
        'title': 'Sea Rescue',
        'tvdb_id': 257984,
        'year': 2012,
        'num_seasons': 3,
        'num_episodes': 54
    },
    'bates_motel': {
        'title': 'Bates Motel',
        'tvdb_id': 262414,
        'year': 2013,
        'num_seasons': 5,
        'num_episodes': 50
    },
    'angry_kid': {
        'title': 'Angry Kid',
        'tvdb_id': 144661,
        'year': 2002,
        'num_seasons': 4,
        'num_episodes': 50
    },
    'masters_of_sex': {
        'title': 'Masters of Sex',
        'tvdb_id': 261557,
        'year': 2014,
        'num_seasons': 4,
        'num_episodes': 46
    },
    'the_last_ship': {
        'title': 'The Last Ship',
        'tvdb_id': 269533,
        'year': 2014,
        'num_seasons': 5,
        'num_episodes': 46
    },
    'sonny_with_a_chance': {
        'title': 'Sonny with a Chance',
        'tvdb_id': 84963,
        'year': 2010,
        'num_seasons': 2,
        'num_episodes': 46
    },
    'one_day_at_a_time': {
        'title': 'One Day at a Time',
        'tvdb_id': 318363,
        'year': 2017,
        'num_seasons': 4,
        'num_episodes': 46
    },
    'your_pretty_face_is_going_to_hell': {
        'title': 'Your Pretty Face Is Going to Hell',
        'tvdb_id': 268386,
        'year': 2013,
        'num_seasons': 4,
        'num_episodes': 42
    },
    'hip_hop_squares': {
        'title': 'Hip Hop Squares',
        'tvdb_id': 286968,
        'year': 2012,
        'num_seasons': 4,
        'num_episodes': 41
    },
    'sweet_magnolias': {
        'title': 'Sweet Magnolias',
        'tvdb_id': 381065,
        'year': 2020,
        'num_seasons': 4,
        'num_episodes': 40
    },
    'dear_white_people': {
        'title': 'Dear White People',
        'tvdb_id': 323855,
        'year': 2017,
        'num_seasons': 4,
        'num_episodes': 40
    },
    'first_flights_with_neil_armstrong': {
        'title': 'First Flights with Neil Armstrong',
        'tvdb_id': 320769,
        'year': 1991,
        'num_seasons': 3,
        'num_episodes': 39
    },
    'the_jeff_corwin_experience': {
        'title': 'The Jeff Corwin Experience',
        'tvdb_id': 85442,
        'year': 2001,
        'num_seasons': 3,
        'num_episodes': 39
    },
    'just_deal': {
        'title': 'Just Deal',
        'tvdb_id': 288773,
        'year': 2000,
        'num_seasons': 3,
        'num_episodes': 39
    },
    'crash_bernstein': {
        'title': 'Crash & Bernstein',
        'tvdb_id': 263374,
        'year': 2012,
        'num_seasons': 2,
        'num_episodes': 39
    },
    'animated_tales_of_the_world': {
        'title': 'Animated Tales of the World',
        'tvdb_id': 331305,
        'year': 2001,
        'num_seasons': 3,
        'num_episodes': 39
    },
    'stranger_things': {
        'title': 'Stranger Things',
        'tvdb_id': 305288,
        'year': 2016,
        'num_seasons': 5,
        'num_episodes': 38
    },
    'gamers_guide_to_pretty_much_everything': {
        'title': 'Gamer\'s Guide to Pretty Much Everything',
        'tvdb_id': 296809,
        'year': 2015,
        'num_seasons': 2,
        'num_episodes': 37
    },
    'crossing_lines': {
        'title': 'Crossing Lines',
        'tvdb_id': 267970,
        'year': 2013,
        'num_seasons': 3,
        'num_episodes': 34
    },
    'flavor_of_love_girls_charm_school': {
        'title': 'Flavor of Love Girls: Charm School',
        'tvdb_id': 84065,
        'year': 2007,
        'num_seasons': 3,
        'num_episodes': 34
    },
    'my_big_fat_american_gypsy_wedding': {
        'title': 'My Big Fat American Gypsy Wedding',
        'tvdb_id': 258632,
        'year': 2012,
        'num_seasons': 4,
        'num_episodes': 33
    },
    'killing_eve': {
        'title': 'Killing Eve',
        'tvdb_id': 340959,
        'year': 2018,
        'num_seasons': 4,
        'num_episodes': 32
    },
    'narcos_mexico': {
        'title': 'Narcos: Mexico',
        'tvdb_id': 353232,
        'year': 2018,
        'num_seasons': 3,
        'num_episodes': 30
    },
    'ultimate_beastmaster': {
        'title': 'Ultimate Beastmaster',
        'tvdb_id': 321372,
        'year': 2017,
        'num_seasons': 3,
        'num_episodes': 29
    },
    'love_victor': {
        'title': 'Love, Victor',
        'tvdb_id': 368188,
        'year': 2020,
        'num_seasons': 3,
        'num_episodes': 28
    },
    'the_singoff': {
        'title': 'The Sing-Off',
        'tvdb_id': 128861,
        'year': 2009,
        'num_seasons': 5,
        'num_episodes': 28
    },
    'this_is_not_happening_with_ari_shaffir': {
        'title': 'This Is Not Happening with Ari Shaffir',
        'tvdb_id': 271813,
        'year': 2015,
        'num_seasons': 3,
        'num_episodes': 26
    },
    'action_man': {
        'title': 'Action Man',
        'tvdb_id': 170641,
        'year': 2000,
        'num_seasons': 2,
        'num_episodes': 26
    },
    'inspector_gadgets_field_trip': {
        'title': 'Inspector Gadget\'s Field Trip',
        'tvdb_id': 314192,
        'year': 1996,
        'num_seasons': 2,
        'num_episodes': 26
    },
    'jason_and_the_heroes_of_mount_olympus': {
        'title': 'Jason and the Heroes of Mount Olympus',
        'tvdb_id': 301528,
        'year': 2001,
        'num_seasons': 1,
        'num_episodes': 26
    },
    'bump_in_the_night': {
        'title': 'Bump in the Night',
        'tvdb_id': 70945,
        'year': 1994,
        'num_seasons': 1,
        'num_episodes': 26
    },
    'horrible_histories': {
        'title': 'Horrible Histories',
        'tvdb_id': 133051,
        'year': 2009,
        'num_seasons': 9,
        'num_episodes': 100
    },
    'family_time': {
        'title': 'Family Time',
        'tvdb_id': 260185,
        'year': 2012,
        'num_seasons': 3,
        'num_episodes': 26
    },
    'a_series_of_unfortunate_events': {
        'title': 'A Series of Unfortunate Events',
        'tvdb_id': 306304,
        'year': 2017,
        'num_seasons': 3,
        'num_episodes': 25
    },
    'show_100_things_to_do_before_high_school': {
        'title': '100 Things to Do Before High School',
        'tvdb_id': 288148,
        'year': 2014,
        'num_seasons': 1,
        'num_episodes': 25
    },
    'americas_castles': {
        'title': 'America\'s Castles',
        'tvdb_id': 264444,
        'year': 1994,
        'num_seasons': 5,
        'num_episodes': 25
    },
    'love_lust_or_run': {
        'title': 'Love, Lust or Run',
        'tvdb_id': 291031,
        'year': 2015,
        'num_seasons': 2,
        'num_episodes': 24
    },
    'muppets_tonight': {
        'title': 'Muppets Tonight',
        'tvdb_id': 78801,
        'year': 1996,
        'num_seasons': 2,
        'num_episodes': 22
    },
    'funny_or_die_presents': {
        'title': 'Funny or Die Presents',
        'tvdb_id': 143041,
        'year': 2010,
        'num_seasons': 2,
        'num_episodes': 22
    },
    'cooper_camellia_ask_the_world': {
        'title': 'Cooper & Camellia Ask the World',
        'tvdb_id': 351610,
        'year': 2018,
        'num_seasons': 2,
        'num_episodes': 21
    },
    'lewis_blacks_root_of_all_evil': {
        'title': 'Lewis Black\'s Root of All Evil',
        'tvdb_id': 81516,
        'year': 2008,
        'num_seasons': 2,
        'num_episodes': 18
    },
    'the_wilds': {
        'title': 'The Wilds',
        'tvdb_id': 349826,
        'year': 2020,
        'num_seasons': 2,
        'num_episodes': 18
    },
    'grosse_pointe': {
        'title': 'Grosse Pointe',
        'tvdb_id': 80479,
        'year': 2000,
        'num_seasons': 1,
        'num_episodes': 17
    },
    'tv_nation': {
        'title': 'TV Nation',
        'tvdb_id': 78788,
        'year': 1994,
        'num_seasons': 2,
        'num_episodes': 17
    },
    'bodies_of_evidence': {
        'title': 'Bodies of Evidence',
        'tvdb_id': 72112,
        'year': 1992,
        'num_seasons': 2,
        'num_episodes': 16
    },
    'show_30_seconds_to_fame': {
        'title': '30 Seconds to Fame',
        'tvdb_id': 71123,
        'year': 2002,
        'num_seasons': 2,
        'num_episodes': 16
    },
    'the_missing': {
        'title': 'The Missing',
        'tvdb_id': 282401,
        'year': 2014,
        'num_seasons': 2,
        'num_episodes': 16
    },
    'the_lord_of_the_rings_the_rings_of_power': {
        'title': 'The Lord of the Rings: The Rings of Power',
        'tvdb_id': 367506,
        'year': 2022,
        'num_seasons': 2,
        'num_episodes': 16
    },
    'roman_empire': {
        'title': 'Roman Empire',
        'tvdb_id': 319594,
        'year': 2016,
        'num_seasons': 3,
        'num_episodes': 15
    },
    'hap_and_leonard': {
        'title': 'Hap and Leonard',
        'tvdb_id': 305687,
        'year': 2016,
        'num_seasons': 3,
        'num_episodes': 15
    },
    'born_again_virgin': {
        'title': 'Born Again Virgin',
        'tvdb_id': 299645,
        'year': 2015,
        'num_seasons': 2,
        'num_episodes': 14
    },
}

show_catalog = ShowCatalog(SHOWS)

# Global singleton instance
movie_catalog = MovieCatalog()


# ==============================================================================
# Additional Error Handling Utilities
# ==============================================================================

def wait_for_torrent_tracking_removed(
    transferarr,
    torrent_name: str,
    timeout: int = 120
) -> bool:
    """
    Wait for a torrent to be removed from Transferarr tracking.
    
    Args:
        transferarr: TransferarrManager instance
        torrent_name: Name or substring of the torrent
        timeout: Maximum seconds to wait
    
    Returns:
        True if torrent was removed from tracking
        
    Raises:
        TimeoutError: If torrent still tracked after timeout
    """
    def check():
        torrents = transferarr.get_torrents()
        for torrent in torrents:
            if torrent_name in torrent.get('name', ''):
                return False  # Still tracked
        return True  # Not found, removed
    
    return wait_for_condition(
        check,
        timeout=timeout,
        description=f"torrent '{torrent_name}' to be removed from tracking"
    )


def corrupt_state_file(transferarr) -> bool:
    """
    Corrupt the state file in the transferarr state volume.
    
    This writes invalid JSON to the state file to test recovery behavior.
    Uses a temporary container to access the volume even when transferarr is stopped.
    
    Args:
        transferarr: TransferarrManager instance
        
    Returns:
        True if corruption was successful
    """
    try:
        # First try using the running container
        try:
            container = transferarr.docker.containers.get(transferarr.container_name)
            if container.status == 'running':
                result = container.exec_run(
                    "sh -c 'echo \"invalid json content here{{{{\" > /state/state.json'"
                )
                return result.exit_code == 0
        except Exception:
            pass
        
        # If container not running, use a temporary container to access the volume
        # Run a simple alpine container with the volume mounted
        result = transferarr.docker.containers.run(
            'alpine:latest',
            'sh -c "echo \'invalid json content here{{{{\' > /state/state.json"',
            volumes={'transferarr-state': {'bind': '/state', 'mode': 'rw'}},
            remove=True
        )
        return True
    except Exception as e:
        print(f"Failed to corrupt state file: {e}")
        return False


def delete_state_file(transferarr) -> bool:
    """
    Delete the state file in the transferarr state volume.
    
    Uses a temporary container to access the volume even when transferarr is stopped.
    
    Args:
        transferarr: TransferarrManager instance
        
    Returns:
        True if deletion was successful
    """
    try:
        # First try using the running container
        try:
            container = transferarr.docker.containers.get(transferarr.container_name)
            if container.status == 'running':
                result = container.exec_run("rm -f /state/state.json")
                return result.exit_code == 0
        except Exception:
            pass
        
        # If container not running, use a temporary container to access the volume
        result = transferarr.docker.containers.run(
            'alpine:latest',
            'rm -f /state/state.json',
            volumes={'transferarr-state': {'bind': '/state', 'mode': 'rw'}},
            remove=True
        )
        return True
    except Exception as e:
        print(f"Failed to delete state file: {e}")
        return False
