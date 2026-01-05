#!/usr/bin/env python3
"""
Generate show catalog for tests from Wikidata.

Queries Wikidata's SPARQL endpoint for popular TV shows (by episode count/seasons)
and outputs a Python dict suitable for tests/utils.py.

Usage:
    python scripts/generate_show_catalog.py > shows.py
    python scripts/generate_show_catalog.py --limit 100
"""

import argparse
import re
import sys
import urllib.request
import urllib.parse
import json


SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Query for TV Series (Q5398477)
# P4835 = TVDB ID
# P1113 = number of episodes
# P2437 = number of seasons
# P495 = country of origin (Q30 = USA)
# P577 = publication date
SPARQL_QUERY = """
SELECT ?show ?showLabel ?tvdbId ?numEpisodes ?numSeasons (MIN(?year) AS ?startYear) WHERE {
  ?show wdt:P31 wd:Q5398426.
  ?show wdt:P4835 ?tvdbId.
  OPTIONAL { ?show wdt:P1113 ?numEpisodes. }
  OPTIONAL { ?show wdt:P2437 ?numSeasons. }
  ?show wdt:P495 wd:Q30.
  ?show wdt:P577 ?date.
  BIND(YEAR(?date) AS ?year)
  FILTER(?year >= 1990 && ?year <= 2024)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
GROUP BY ?show ?showLabel ?tvdbId ?numEpisodes ?numSeasons
HAVING(MIN(?year) >= 1990)
ORDER BY DESC(?numEpisodes)
LIMIT 1000
"""


def query_wikidata(query: str) -> list[dict]:
    """Execute SPARQL query against Wikidata."""
    url = SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({
        "query": query,
        "format": "json"
    })
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "TransferarrTestShowCatalog/1.0 (https://github.com/transferarr)"
    })
    
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    
    return data["results"]["bindings"]


def has_year_in_title(title: str) -> bool:
    """
    Check if title contains a year (4 digits that look like a year).
    
    We want to filter these out because Sonarr's parser gets confused
    when the torrent name has both the title year and release year.
    """
    # Match 4-digit numbers that look like years (1900-2099)
    year_pattern = r'\b(19|20)\d{2}\b'
    return bool(re.search(year_pattern, title))


def is_single_word_title(title: str) -> bool:
    """
    Check if title is a single word.
    
    Single-word titles like "Hacks", "Mom", "24" are too generic and
    may cause Sonarr matching issues.
    """
    # Split on whitespace and filter out empty strings
    words = [w for w in title.split() if w]
    return len(words) <= 1


def sanitize_key(title: str) -> str:
    """Convert show title to a valid Python dict key."""
    # Remove special characters, replace spaces with underscores
    key = re.sub(r'[^\w\s]', '', title.lower())
    key = re.sub(r'\s+', '_', key.strip())
    # Ensure it doesn't start with a number
    if key and key[0].isdigit():
        key = 'show_' + key
    return key


def main():
    parser = argparse.ArgumentParser(description="Generate show catalog from Wikidata")
    parser.add_argument("--limit", type=int, default=200, help="Maximum shows to output")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON instead of Python dict")
    args = parser.parse_args()
    
    try:
        results = query_wikidata(SPARQL_QUERY)
    except Exception as e:
        print(f"Error querying Wikidata: {e}", file=sys.stderr)
        sys.exit(1)
        
    shows = []
    seen_tvdb_ids = set()
    
    for result in results:
        title = result["showLabel"]["value"]
        tvdb_id = result["tvdbId"]["value"]
        year = int(result["startYear"]["value"])
        
        # Handle optional fields
        num_episodes = int(result["numEpisodes"]["value"]) if "numEpisodes" in result else 0
        num_seasons = int(result["numSeasons"]["value"]) if "numSeasons" in result else 0
        
        # Skip shows with very few episodes if we have the data
        if num_episodes > 0 and num_episodes < 12:
            continue
        if num_seasons > 0 and num_seasons < 1:
            continue

        # Skip duplicates
        if tvdb_id in seen_tvdb_ids:
            continue
            
        # Filter out titles with years (confuses Sonarr parser)
        if has_year_in_title(title):
            continue
            
        # Filter out single-word titles (too generic)
        if is_single_word_title(title):
            continue
            
        # Filter out non-ASCII titles (problematic for some file systems/parsers)
        if not all(ord(c) < 128 for c in title):
            continue
            
        shows.append({
            "key": sanitize_key(title),
            "title": title,
            "tvdb_id": int(tvdb_id),
            "year": year,
            "num_seasons": num_seasons,
            "num_episodes": num_episodes
        })
        seen_tvdb_ids.add(tvdb_id)
        
        if len(shows) >= args.limit:
            break
        
        if len(shows) >= args.limit:
            break
            
    if args.raw:
        print(json.dumps(shows, indent=2))
    else:
        print("SHOWS = {")
        for show in shows:
            safe_title = show['title'].replace("'", "\\'")
            print(f"    '{show['key']}': {{")
            print(f"        'title': '{safe_title}',")
            print(f"        'tvdb_id': {show['tvdb_id']},")
            print(f"        'year': {show['year']},")
            print(f"        'num_seasons': {show['num_seasons']},")
            print(f"        'num_episodes': {show['num_episodes']}")
            print("    },")
        print("}")


if __name__ == "__main__":
    main()
