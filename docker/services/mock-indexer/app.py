#!/usr/bin/env python3
"""
Mock Torznab indexer for testing.

Returns test torrents when queried by Radarr/Sonarr.
Provides minimal Torznab API implementation:
- /api?t=caps - Returns indexer capabilities
- /api?t=search|movie|tvsearch - Returns available test torrents
- /download/<filename> - Serves .torrent files
- /health - Health check endpoint
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

# Configuration from environment
TORRENT_DIR = Path(os.environ.get('TORRENT_DIR', '/torrents'))
TRACKER_URL = os.environ.get('TRACKER_URL', 'http://tracker:6969/announce')

# Ensure torrent directory exists
TORRENT_DIR.mkdir(parents=True, exist_ok=True)


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'torrent_dir': str(TORRENT_DIR),
        'torrent_count': len(list(TORRENT_DIR.glob('*.torrent')))
    })


@app.route('/api')
def torznab_api():
    """Torznab API endpoint - main entry point for Radarr/Sonarr"""
    t = request.args.get('t', '')
    
    if t == 'caps':
        return Response(CAPS_XML, mimetype='application/xml')
    
    if t in ('search', 'movie', 'tvsearch'):
        query = request.args.get('q', '')
        # Get requested categories (comma-separated list)
        cat_str = request.args.get('cat', '')
        categories = [int(c) for c in cat_str.split(',') if c.isdigit()] if cat_str else []
        tvdbid = request.args.get('tvdbid')
        tmdbid = request.args.get('tmdbid')
        
        return Response(
            generate_search_results(query, categories, tvdbid=tvdbid, tmdbid=tmdbid),
            mimetype='application/xml'
        )
    
    # Unknown command
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<error code="100" description="Incorrect parameter"/>',
        mimetype='application/xml',
        status=400
    )


def generate_search_results(query: str, requested_categories: list = None, tvdbid: str = None, tmdbid: str = None) -> str:
    """
    Generate Torznab XML with available test torrents.
    
    Matches torrents by:
    - If query is empty, returns all torrents
    - If query provided, matches case-insensitively against torrent name
    - If categories provided, only returns torrents matching those categories
    """
    items = []
    
    # Map parent categories to include subcategories
    # 2000 = Movies, 5000 = TV
    def matches_category(torrent_cat: int, requested: list) -> bool:
        if not requested:
            return True
        # Check if torrent's category or its parent category is in requested
        for req_cat in requested:
            # Direct match
            if torrent_cat == req_cat:
                return True
            # Parent category match (2000 matches 2010, 2020, etc)
            if (req_cat // 1000) * 1000 == (torrent_cat // 1000) * 1000:
                return True
            # Requested is parent, torrent is in that range
            if req_cat % 1000 == 0 and req_cat <= torrent_cat < req_cat + 1000:
                return True
        return False
    
    for torrent_file in sorted(TORRENT_DIR.glob('*.torrent')):
        name = torrent_file.stem
        
        # Match query against torrent name
        match_name = name.lower().replace('.', ' ').replace('_', ' ')
        match_query = query.lower() if query else ""
        
        # If it's a TV search, be more lenient with episode/season suffixes in query
        if any(c >= 5000 and c < 6000 for c in requested_categories) and match_query:
            # Strip SxxExx or Sxx or year from query to match just the title
            # Sonarr often sends "Show Title S01E01" or "Show Title (2014) S01E01"
            match_query = re.sub(r'\s+s\d+(e\d+)?.*$', '', match_query)
            match_query = re.sub(r'\s+\(\d{4}\).*$', '', match_query)
            match_query = match_query.strip()
            
        if match_query and match_query not in match_name:
            continue
        
        # Get file size (rough estimate from torrent file)
        # Real implementation would parse the torrent
        torrent_size = torrent_file.stat().st_size
        
        # Determine category based on name
        # Movies typically have year pattern, TV has SxxExx pattern
        if re.search(r'S\d+E\d+', name, re.IGNORECASE):
            category = 5030  # TV/SD (within 5000 range)
            # Dynamic size for TV to avoid Sonarr rejections
            if 'Angry.Kid' in name:
                estimated_size = 50 * 1024 * 1024  # 50MB for short shows
            else:
                estimated_size = 500 * 1024 * 1024 # 500MB for regular shows
        elif re.search(r'S\d+', name, re.IGNORECASE):
            category = 5000  # TV/Season Pack
            estimated_size = 10 * 1024 * 1024 * 1024 # 10GB for season packs
        else:
            category = 2040  # Movies/HD (within 2000 range)
            estimated_size = max(torrent_size * 100, 500 * 1024 * 1024)
        
        # Filter by category if requested
        if not matches_category(category, requested_categories):
            continue
        
        # Generate proper RFC 2822 date (with correct day-of-week)
        pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        
        item_xml = f'''        <item>
            <title>{escape_xml(name)}</title>
            <guid>{escape_xml(name)}</guid>
            <link>http://mock-indexer:9696/download/{escape_xml(torrent_file.name)}</link>
            <pubDate>{pub_date}</pubDate>
            <size>{estimated_size}</size>
            <description>{escape_xml(name)}</description>
            <category>{category}</category>
            <enclosure url="http://mock-indexer:9696/download/{escape_xml(torrent_file.name)}" 
                       length="{estimated_size}" 
                       type="application/x-bittorrent"/>
            <newznab:attr name="category" value="{category}"/>
            <newznab:attr name="size" value="{estimated_size}"/>
            <newznab:attr name="seeders" value="1"/>
            <newznab:attr name="peers" value="1"/>
            <newznab:attr name="downloadvolumefactor" value="1"/>
            <newznab:attr name="uploadvolumefactor" value="1"/>'''
        
        if tvdbid:
            item_xml += f'\n            <newznab:attr name="tvdbid" value="{tvdbid}"/>'
        if tmdbid:
            item_xml += f'\n            <newznab:attr name="tmdbid" value="{tmdbid}"/>'
            
        item_xml += '\n        </item>'
        items.append(item_xml)
    
    result_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" 
     xmlns:torznab="http://torznab.com/schemas/2015/feed"
     xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
    <channel>
        <title>Mock Indexer</title>
        <description>Test torrent indexer for Transferarr testing</description>
        <link>http://mock-indexer:9696</link>
        <language>en-us</language>
        <atom:link rel="self" type="application/rss+xml"/>
        <newznab:response offset="0" total="{len(items)}"/>
{chr(10).join(items)}
    </channel>
</rss>'''
    
    return result_xml


def escape_xml(text: str) -> str:
    """Escape XML special characters"""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


@app.route('/download/<filename>')
def download_torrent(filename: str):
    """
    Serve .torrent files.
    
    This is called when Radarr/Sonarr wants to download a torrent
    after finding it in search results.
    """
    # Sanitize filename to prevent directory traversal
    safe_filename = Path(filename).name
    torrent_path = TORRENT_DIR / safe_filename
    
    if not torrent_path.exists():
        app.logger.warning(f"Torrent not found: {safe_filename}")
        return Response('Torrent not found', status=404)
    
    app.logger.info(f"Serving torrent: {safe_filename}")
    return Response(
        torrent_path.read_bytes(),
        mimetype='application/x-bittorrent',
        headers={
            'Content-Disposition': f'attachment; filename="{safe_filename}"'
        }
    )


@app.route('/torrents')
def list_torrents():
    """List available torrents (debugging endpoint)"""
    torrents = []
    for torrent_file in sorted(TORRENT_DIR.glob('*.torrent')):
        torrents.append({
            'name': torrent_file.stem,
            'filename': torrent_file.name,
            'size': torrent_file.stat().st_size,
            'download_url': f'http://mock-indexer:9696/download/{torrent_file.name}'
        })
    return jsonify({
        'torrent_dir': str(TORRENT_DIR),
        'count': len(torrents),
        'torrents': torrents
    })


# Torznab capabilities XML
CAPS_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<caps>
    <server version="1.0" title="Mock Indexer" strapline="Test indexer for Transferarr" 
            email="" url="http://mock-indexer:9696" image=""/>
    <limits max="100" default="50"/>
    <registration available="no" open="no"/>
    <searching>
        <search available="yes" supportedParams="q"/>
        <tv-search available="yes" supportedParams="q,season,ep,tvdbid"/>
        <movie-search available="yes" supportedParams="q,imdbid"/>
    </searching>
    <categories>
        <category id="2000" name="Movies">
            <subcat id="2010" name="Movies/Foreign"/>
            <subcat id="2020" name="Movies/Other"/>
            <subcat id="2030" name="Movies/SD"/>
            <subcat id="2040" name="Movies/HD"/>
            <subcat id="2045" name="Movies/UHD"/>
            <subcat id="2050" name="Movies/BluRay"/>
            <subcat id="2060" name="Movies/3D"/>
        </category>
        <category id="5000" name="TV">
            <subcat id="5010" name="TV/WEB-DL"/>
            <subcat id="5020" name="TV/Foreign"/>
            <subcat id="5030" name="TV/SD"/>
            <subcat id="5040" name="TV/HD"/>
            <subcat id="5045" name="TV/UHD"/>
            <subcat id="5050" name="TV/Other"/>
            <subcat id="5060" name="TV/Sport"/>
        </category>
    </categories>
</caps>'''


if __name__ == '__main__':
    print(f"Mock Indexer starting...")
    print(f"  Torrent directory: {TORRENT_DIR}")
    print(f"  Tracker URL: {TRACKER_URL}")
    print(f"  Listening on port 9696")
    app.run(host='0.0.0.0', port=9696, debug=False)
