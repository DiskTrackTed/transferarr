#!/usr/bin/env python3
"""
Check why Radarr rejected releases.

This script queries Radarr's API and logs to find rejection reasons for releases.
Useful for debugging why a torrent isn't being grabbed.

Usage:
    ./scripts/check-radarr-rejections.py [options]

Examples:
    # Check rejections for all pending releases
    ./scripts/check-radarr-rejections.py
    
    # Check rejections for a specific movie by name
    ./scripts/check-radarr-rejections.py --movie "Star Wars"
    
    # Check rejections for a specific torrent name
    ./scripts/check-radarr-rejections.py --torrent "Star.Wars.Episode.VII"
    
    # Show recent Radarr log entries about decisions
    ./scripts/check-radarr-rejections.py --logs
    
    # Test if a release title would be parsed correctly
    ./scripts/check-radarr-rejections.py --parse "Star.Wars.The.Force.Awakens.2015.1080p.BluRay.x264"
"""
import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Optional

# Configuration (can be overridden via CLI args)
config = {
    'host': os.environ.get('RADARR_HOST', 'localhost'),
    'port': int(os.environ.get('RADARR_PORT', '17878')),
    'container': 'test-radarr',
}


def get_api_key() -> str:
    """Get Radarr API key from container config."""
    try:
        result = subprocess.run(
            ['docker', 'exec', config['container'], 'cat', '/config/config.xml'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"Error reading Radarr config: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        root = ET.fromstring(result.stdout)
        api_key = root.find('ApiKey')
        if api_key is None or not api_key.text:
            print("Could not find ApiKey in Radarr config", file=sys.stderr)
            sys.exit(1)
        return api_key.text
    except subprocess.TimeoutExpired:
        print("Timeout reading Radarr config", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def radarr_api(endpoint: str, api_key: str, params: dict = None) -> dict:
    """Make a request to the Radarr API."""
    import urllib.request
    import urllib.parse
    
    url = f"http://{config['host']}:{config['port']}/api/v3/{endpoint}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url)
    req.add_header('X-Api-Key', api_key)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return {}


def get_movies(api_key: str) -> list:
    """Get all movies from Radarr."""
    return radarr_api('movie', api_key) or []


def get_releases_for_movie(api_key: str, movie_id: int) -> list:
    """Get available releases for a movie."""
    return radarr_api('release', api_key, {'movieId': movie_id}) or []


def parse_title(api_key: str, title: str) -> dict:
    """Use Radarr's parser to analyze a release title."""
    return radarr_api('parse', api_key, {'title': title}) or {}


def get_container_logs(lines: int = 100, filter_pattern: str = None) -> list:
    """Get recent Radarr container logs."""
    try:
        result = subprocess.run(
            ['docker', 'logs', '--tail', str(lines), config['container']],
            capture_output=True,
            text=True,
            timeout=30
        )
        logs = result.stderr.split('\n')  # Radarr logs go to stderr
        
        if filter_pattern:
            pattern = re.compile(filter_pattern, re.IGNORECASE)
            logs = [line for line in logs if pattern.search(line)]
        
        return logs
    except Exception as e:
        print(f"Error getting logs: {e}", file=sys.stderr)
        return []


def print_release_info(release: dict):
    """Print detailed info about a release."""
    title = release.get('title', 'Unknown')
    rejected = release.get('rejected', False)
    rejections = release.get('rejections', [])
    
    status = '❌ REJECTED' if rejected else '✅ ACCEPTED'
    print(f"\n  {status}: {title}")
    
    if rejections:
        print("    Rejection reasons:")
        for reason in rejections:
            if isinstance(reason, dict):
                print(f"      - {reason.get('reason', reason)}")
            else:
                print(f"      - {reason}")
    
    # Print additional useful info
    quality = release.get('quality', {}).get('quality', {}).get('name', 'Unknown')
    size = release.get('size', 0)
    size_mb = size / (1024 * 1024) if size else 0
    indexer = release.get('indexer', 'Unknown')
    
    print(f"    Quality: {quality}")
    print(f"    Size: {size_mb:.1f} MB")
    print(f"    Indexer: {indexer}")


def check_all_movies(api_key: str, movie_filter: str = None):
    """Check releases for all movies (or filtered by name)."""
    movies = get_movies(api_key)
    
    if not movies:
        print("No movies found in Radarr")
        return
    
    if movie_filter:
        movies = [m for m in movies if movie_filter.lower() in m.get('title', '').lower()]
        if not movies:
            print(f"No movies matching '{movie_filter}'")
            return
    
    print(f"\n{'='*60}")
    print(f"Checking releases for {len(movies)} movie(s)")
    print(f"{'='*60}")
    
    for movie in movies:
        movie_id = movie.get('id')
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        clean_title = movie.get('cleanTitle', '')
        
        print(f"\n📽️  {title} ({year})")
        print(f"    Clean title: {clean_title}")
        print(f"    Movie ID: {movie_id}")
        
        # Get alternative titles
        alt_titles = movie.get('alternateTitles', [])
        if alt_titles:
            print(f"    Alternative titles ({len(alt_titles)}):")
            for alt in alt_titles[:5]:  # Show first 5
                print(f"      - {alt.get('title', '')}")
            if len(alt_titles) > 5:
                print(f"      ... and {len(alt_titles) - 5} more")
        
        # Get releases
        releases = get_releases_for_movie(api_key, movie_id)
        
        if not releases:
            print("    No releases found")
            continue
        
        print(f"    Found {len(releases)} release(s):")
        
        rejected_count = sum(1 for r in releases if r.get('rejected'))
        accepted_count = len(releases) - rejected_count
        print(f"    Summary: {accepted_count} accepted, {rejected_count} rejected")
        
        for release in releases:
            print_release_info(release)


def check_torrent_name(api_key: str, torrent_name: str):
    """Check if a specific torrent name would be rejected."""
    print(f"\n{'='*60}")
    print(f"Checking torrent: {torrent_name}")
    print(f"{'='*60}")
    
    # First, parse the title
    result = parse_title(api_key, torrent_name)
    
    if not result:
        print("\n❌ Radarr could not parse this title at all")
        return
    
    parsed_movie = result.get('movie')
    parsed_info = result.get('parsedMovieInfo', {})
    
    print("\n📊 Parse Result:")
    print(f"  Movie Title: {parsed_info.get('movieTitle', 'NOT DETECTED')}")
    print(f"  Year: {parsed_info.get('year', 'NOT DETECTED')}")
    print(f"  Quality: {parsed_info.get('quality', {}).get('quality', {}).get('name', 'Unknown')}")
    print(f"  Edition: {parsed_info.get('edition', 'None')}")
    print(f"  Release Group: {parsed_info.get('releaseGroup', 'None')}")
    
    if parsed_movie:
        print(f"\n✅ Matched to movie: {parsed_movie.get('title')} ({parsed_movie.get('year')})")
        print(f"   Clean title: {parsed_movie.get('cleanTitle')}")
    else:
        print("\n❌ Could not match to any movie in library")
        print("   This torrent would be rejected as 'Unknown Movie'")
        
        # Try to suggest why
        movie_title = parsed_info.get('movieTitle', '')
        if movie_title:
            print(f"\n   Parsed movie title: '{movie_title}'")
            print("   Possible issues:")
            print("   - Movie not added to Radarr library")
            print("   - Title doesn't match any known aliases")
            print("   - Year mismatch")
            
            # Check if any movie has a similar name
            movies = get_movies(api_key)
            similar = [m for m in movies if movie_title.lower() in m.get('title', '').lower() 
                      or movie_title.lower() in m.get('cleanTitle', '').lower()]
            if similar:
                print(f"\n   Similar movies in library:")
                for m in similar[:3]:
                    print(f"     - {m.get('title')} ({m.get('year')}) [clean: {m.get('cleanTitle')}]")


def show_decision_logs(lines: int = 50):
    """Show recent decision-related log entries."""
    print(f"\n{'='*60}")
    print(f"Recent Radarr Decision Logs (last {lines} relevant lines)")
    print(f"{'='*60}\n")
    
    # Get logs and filter for decision-related entries
    patterns = [
        r'DownloadDecisionMaker',
        r'Processing.*releases?',
        r'reports? downloaded',
        r'rejected',
        r'accepted',
        r'grabbed',
        r'Unknown Movie',
        r'ReleaseSearchService',
        r'DownloadService.*Report',
    ]
    
    all_logs = get_container_logs(lines=500)
    
    combined_pattern = '|'.join(patterns)
    filtered = [log for log in all_logs if re.search(combined_pattern, log, re.IGNORECASE)]
    
    if not filtered:
        print("No relevant decision logs found")
        return
    
    for log in filtered[-lines:]:
        # Color code the output
        if 'rejected' in log.lower() or 'Unknown Movie' in log:
            print(f"❌ {log}")
        elif 'downloaded' in log.lower() or 'grabbed' in log.lower():
            print(f"✅ {log}")
        elif 'Processing' in log:
            print(f"📋 {log}")
        else:
            print(f"   {log}")


def main():
    parser = argparse.ArgumentParser(
        description='Check why Radarr rejected releases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--movie', '-m', type=str,
                       help='Filter by movie name')
    parser.add_argument('--torrent', '-t', type=str,
                       help='Check a specific torrent name')
    parser.add_argument('--parse', '-p', type=str,
                       help='Parse a release title to see how Radarr interprets it')
    parser.add_argument('--logs', '-l', action='store_true',
                       help='Show recent decision logs from container')
    parser.add_argument('--log-lines', type=int, default=50,
                       help='Number of log lines to show (default: 50)')
    parser.add_argument('--host', type=str,
                       help=f"Radarr host (default: {config['host']})")
    parser.add_argument('--port', type=int,
                       help=f"Radarr port (default: {config['port']})")
    
    args = parser.parse_args()
    
    # Override config with CLI args if provided
    if args.host:
        config['host'] = args.host
    if args.port:
        config['port'] = args.port
    
    # Get API key
    api_key = get_api_key()
    
    if args.logs:
        show_decision_logs(args.log_lines)
    elif args.parse or args.torrent:
        check_torrent_name(api_key, args.parse or args.torrent)
    else:
        check_all_movies(api_key, args.movie)


if __name__ == '__main__':
    main()
