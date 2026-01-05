#!/usr/bin/env python3
"""
Generate movie catalog for tests from Wikidata.

Queries Wikidata's SPARQL endpoint for popular movies (by box office)
and outputs a Python dict suitable for tests/utils.py.

Usage:
    python scripts/generate_movie_catalog.py > movies.py
    python scripts/generate_movie_catalog.py --limit 100
"""

import argparse
import re
import sys
import urllib.request
import urllib.parse
import json


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

SPARQL_QUERY = """
SELECT ?movie ?movieLabel ?tmdbId (MIN(?year) AS ?releaseYear) (MAX(?boxOffice) AS ?maxBoxOffice) WHERE {
  ?movie wdt:P31 wd:Q11424.
  ?movie wdt:P4947 ?tmdbId.
  ?movie wdt:P577 ?date.
  ?movie wdt:P2142 ?boxOffice.
  ?movie wdt:P495 wd:Q30.
  BIND(YEAR(?date) AS ?year)
  FILTER(?year >= 1985 && ?year <= 2024)
  FILTER(?boxOffice > 100000000)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
GROUP BY ?movie ?movieLabel ?tmdbId
HAVING(MIN(?year) >= 1985)
ORDER BY DESC(?maxBoxOffice)
LIMIT 1000
"""


def query_wikidata(query: str) -> list[dict]:
    """Execute SPARQL query against Wikidata."""
    url = SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({
        "query": query,
        "format": "json"
    })
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "TransferarrTestMovieCatalog/1.0 (https://github.com/transferarr)"
    })
    
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    
    return data["results"]["bindings"]


def has_year_in_title(title: str) -> bool:
    """
    Check if title contains a year (4 digits that look like a year).
    
    We want to filter these out because Radarr's parser gets confused
    when the torrent name has both the title year and release year.
    e.g., "Blade Runner 2049" -> "Blade.Runner.2049.2017.1080p" confuses Radarr.
    """
    # Match 4-digit numbers that look like years (1900-2099)
    year_pattern = r'\b(19|20)\d{2}\b'
    return bool(re.search(year_pattern, title))


def has_episode_in_title(title: str) -> bool:
    """
    Check if title contains "Episode" or "Part".
    
    We want to filter these out because Radarr's clean title parser
    strips "Episode X" and "Part X" from titles when matching, causing
    torrent names to not match the movie.
    e.g., "Star Wars: Episode VII" clean title is just "Star Wars"
    """
    return bool(re.search(r'\b(Episode|Part)\b', title, re.IGNORECASE))


def is_single_word_title(title: str) -> bool:
    """
    Check if title is a single word.
    
    Single-word titles like "Kill", "Viy", "Ice" are too generic and
    may cause Radarr matching issues.
    """
    # Split on whitespace and filter out empty strings
    words = [w for w in title.split() if w]
    return len(words) <= 1


def sanitize_key(title: str) -> str:
    """Convert movie title to a valid Python dict key."""
    # Remove special characters, replace spaces with underscores
    key = re.sub(r'[^\w\s]', '', title.lower())
    key = re.sub(r'\s+', '_', key.strip())
    # Ensure it doesn't start with a number
    if key and key[0].isdigit():
        key = 'movie_' + key
    return key


def main():
    parser = argparse.ArgumentParser(description="Generate movie catalog from Wikidata")
    parser.add_argument("--limit", type=int, default=200, help="Maximum movies to output")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON instead of Python dict")
    args = parser.parse_args()
    
    print(f"Querying Wikidata for movies...", file=sys.stderr)
    results = query_wikidata(SPARQL_QUERY)
    print(f"Got {len(results)} results from Wikidata", file=sys.stderr)
    
    # Process and deduplicate
    seen_tmdb_ids = set()
    seen_keys = set()
    movies = []
    
    for row in results:
        title = row["movieLabel"]["value"]
        tmdb_id = row["tmdbId"]["value"]
        year = int(row["releaseYear"]["value"])
        box_office = int(float(row["maxBoxOffice"]["value"]))
        
        # Skip if we've seen this TMDB ID
        if tmdb_id in seen_tmdb_ids:
            continue
        seen_tmdb_ids.add(tmdb_id)
        
        # Skip movies with years in titles
        if has_year_in_title(title):
            print(f"  Skipping (year in title): {title}", file=sys.stderr)
            continue
        
        # Skip movies with "Episode" or "Part" in titles
        if has_episode_in_title(title):
            print(f"  Skipping (Episode/Part in title): {title}", file=sys.stderr)
            continue
        
        # Skip single-word titles (too generic for Radarr matching)
        if is_single_word_title(title):
            print(f"  Skipping (single word): {title}", file=sys.stderr)
            continue
        
        # Generate unique key
        key = sanitize_key(title)
        if key in seen_keys:
            # Add year to make unique
            key = f"{key}_{year}"
        if key in seen_keys:
            # Still duplicate? Skip it
            print(f"  Skipping (duplicate key): {title}", file=sys.stderr)
            continue
        seen_keys.add(key)
        
        movies.append({
            "key": key,
            "title": title,
            "tmdb_id": int(tmdb_id),
            "year": year,
            "box_office": box_office,
        })
        
        if len(movies) >= args.limit:
            break
    
    print(f"Filtered to {len(movies)} unique movies", file=sys.stderr)
    
    if args.raw:
        print(json.dumps(movies, indent=2))
        return
    
    # Output Python dict format
    print("    # Auto-generated from Wikidata - top box office movies 1985-2024")
    print("    # Generated by: python scripts/generate_movie_catalog.py")
    print("    # ")
    print("    # NOTE: Movies with years in their titles (like \"Blade Runner 2049\") are filtered out.")
    print("    # Radarr's release title parser gets confused when the torrent name includes")
    print("    # both the title year AND a release year (e.g., \"Blade.Runner.2049.2017.1080p\").")
    print("    # ")
    print("    # NOTE: Movies with \"Episode\" or \"Part\" in titles are also filtered out.")
    print("    # Radarr's clean title parser strips these, causing matching failures.")
    print("    MOVIES = {")
    
    for movie in movies:
        # Escape any single quotes in title
        title = movie["title"].replace("'", "\\'")
        print(f"        '{movie['key']}': {{'title': '{title}', 'tmdb_id': {movie['tmdb_id']}, 'year': {movie['year']}}},")
    
    print("    }")


if __name__ == "__main__":
    main()
