#!/bin/bash
# cleanup.sh - Reset test environment to clean state
# 
# Usage:
#   ./docker/scripts/cleanup.sh          # Clean all services
#   ./docker/scripts/cleanup.sh torrents # Clean only torrents
#   ./docker/scripts/cleanup.sh state    # Clean only transferarr state
#   ./docker/scripts/cleanup.sh volumes  # Reset Docker volumes (full reset)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.test.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Deluge credentials
DELUGE_PASSWORD="testpassword"

# Clean torrents from Deluge instance via Web API
clean_deluge_torrents() {
    local host=$1
    local port=$2
    local name=$3
    
    log_info "Cleaning torrents from $name ($host:$port)..."
    
    # Get session cookie
    local cookie_file=$(mktemp)
    
    # Login
    local login_response=$(curl -s -c "$cookie_file" -X POST \
        "http://$host:$port/json" \
        -H "Content-Type: application/json" \
        -d '{"method": "auth.login", "params": ["'"$DELUGE_PASSWORD"'"], "id": 1}')
    
    if [[ $(echo "$login_response" | grep -c '"result": true') -eq 0 ]]; then
        log_warn "Could not login to $name - may not be running"
        rm -f "$cookie_file"
        return 0
    fi
    
    # Connect to first available host
    curl -s -b "$cookie_file" -X POST \
        "http://$host:$port/json" \
        -H "Content-Type: application/json" \
        -d '{"method": "web.connect", "params": [""], "id": 2}' > /dev/null
    
    # Get torrent list
    local torrents_response=$(curl -s -b "$cookie_file" -X POST \
        "http://$host:$port/json" \
        -H "Content-Type: application/json" \
        -d '{"method": "core.get_torrents_status", "params": [{}, ["hash"]], "id": 3}')
    
    # Extract torrent hashes
    local hashes=$(echo "$torrents_response" | grep -oP '"[a-f0-9]{40}"' | tr -d '"' | sort -u)
    
    if [[ -z "$hashes" ]]; then
        log_info "No torrents found in $name"
        rm -f "$cookie_file"
        return 0
    fi
    
    # Remove each torrent
    local count=0
    for hash in $hashes; do
        curl -s -b "$cookie_file" -X POST \
            "http://$host:$port/json" \
            -H "Content-Type: application/json" \
            -d '{"method": "core.remove_torrent", "params": ["'"$hash"'", true], "id": 4}' > /dev/null
        ((count++)) || true
    done
    
    log_info "Removed $count torrent(s) from $name"
    rm -f "$cookie_file"
}

# Clean Radarr queue and movies
clean_radarr() {
    local host=$1
    local port=$2
    
    log_info "Cleaning Radarr ($host:$port)..."
    
    # Get API key from config
    local api_key=$(docker exec test-radarr cat /config/config.xml 2>/dev/null | grep -oP '(?<=<ApiKey>)[^<]+' || true)
    
    if [[ -z "$api_key" ]]; then
        log_warn "Could not get Radarr API key - may not be running"
        return 0
    fi
    
    # Get queue items
    local queue_response=$(curl -s "http://$host:$port/api/v3/queue?apikey=$api_key")
    local queue_ids=$(echo "$queue_response" | grep -oP '"id":\s*\K\d+' || true)
    
    # Remove queue items
    for id in $queue_ids; do
        curl -s -X DELETE "http://$host:$port/api/v3/queue/$id?apikey=$api_key&removeFromClient=true&blocklist=false" > /dev/null
    done
    
    if [[ -n "$queue_ids" ]]; then
        log_info "Cleared $(echo "$queue_ids" | wc -l) queue item(s) from Radarr"
    fi
    
    # Get and remove movies
    local movies_response=$(curl -s "http://$host:$port/api/v3/movie?apikey=$api_key")
    local movie_ids=$(echo "$movies_response" | grep -oP '"id":\s*\K\d+' | head -20 || true)
    
    for id in $movie_ids; do
        curl -s -X DELETE "http://$host:$port/api/v3/movie/$id?apikey=$api_key&deleteFiles=true" > /dev/null
    done
    
    if [[ -n "$movie_ids" ]]; then
        log_info "Removed $(echo "$movie_ids" | wc -l) movie(s) from Radarr"
    fi
}

# Clean Sonarr queue and series
clean_sonarr() {
    local host=$1
    local port=$2
    
    log_info "Cleaning Sonarr ($host:$port)..."
    
    # Get API key from config
    local api_key=$(docker exec test-sonarr cat /config/config.xml 2>/dev/null | grep -oP '(?<=<ApiKey>)[^<]+' || true)
    
    if [[ -z "$api_key" ]]; then
        log_warn "Could not get Sonarr API key - may not be running"
        return 0
    fi
    
    # Get queue items
    local queue_response=$(curl -s "http://$host:$port/api/v3/queue?apikey=$api_key")
    local queue_ids=$(echo "$queue_response" | grep -oP '"id":\s*\K\d+' || true)
    
    # Remove queue items
    for id in $queue_ids; do
        curl -s -X DELETE "http://$host:$port/api/v3/queue/$id?apikey=$api_key&removeFromClient=true&blocklist=false" > /dev/null
    done
    
    if [[ -n "$queue_ids" ]]; then
        log_info "Cleared $(echo "$queue_ids" | wc -l) queue item(s) from Sonarr"
    fi
    
    # Get and remove series
    local series_response=$(curl -s "http://$host:$port/api/v3/series?apikey=$api_key")
    local series_ids=$(echo "$series_response" | grep -oP '"id":\s*\K\d+' | head -20 || true)
    
    for id in $series_ids; do
        curl -s -X DELETE "http://$host:$port/api/v3/series/$id?apikey=$api_key&deleteFiles=true" > /dev/null
    done
    
    if [[ -n "$series_ids" ]]; then
        log_info "Removed $(echo "$series_ids" | wc -l) series from Sonarr"
    fi
}

# Clean transferarr state
clean_transferarr_state() {
    log_info "Cleaning transferarr state..."
    
    # Remove state from Docker volume
    docker exec test-transferarr rm -f /app/state.json 2>/dev/null || true
    
    # Also clean local state file if running locally
    rm -f "$PROJECT_ROOT/docker/fixtures/state.json" 2>/dev/null || true
    rm -f "$PROJECT_ROOT/state.json" 2>/dev/null || true
    
    log_info "Transferarr state cleaned"
}

# Clean mock indexer torrents
clean_mock_indexer() {
    log_info "Cleaning mock indexer torrents..."
    
    # Check if container is running
    if ! docker exec test-mock-indexer true 2>/dev/null; then
        log_warn "Mock indexer container not running"
        return 0
    fi
    
    # Count torrents before cleanup
    local before_count=$(docker exec test-mock-indexer find /torrents -name "*.torrent" -type f 2>/dev/null | wc -l)
    
    if [[ "$before_count" -eq 0 ]]; then
        log_info "No torrents in mock indexer"
        return 0
    fi
    
    # Clear the torrents directory inside the mock-indexer container
    docker exec test-mock-indexer find /torrents -name "*.torrent" -type f -delete
    
    # Verify cleanup
    local after_count=$(docker exec test-mock-indexer find /torrents -name "*.torrent" -type f 2>/dev/null | wc -l)
    
    if [[ "$after_count" -eq 0 ]]; then
        log_info "Removed $before_count torrent(s) from mock indexer"
    else
        log_warn "Failed to clean mock indexer: $after_count torrents remain"
    fi
}

# Clean downloaded files from volumes
clean_downloads() {
    log_info "Cleaning downloaded files..."
    
    # Clean source downloads - both root level torrent folders and movie/tv subdirs
    # Torrents download to /downloads/<torrent_name>/ by default
    docker exec test-deluge-source bash -c '
        # Remove movie/tv subdirs
        rm -rf /downloads/movies/* /downloads/tv/* 2>/dev/null
        # Remove torrent folders (anything that is not movies/tv directories)
        find /downloads -maxdepth 1 -type d ! -name downloads ! -name movies ! -name tv -exec rm -rf {} + 2>/dev/null
    ' || true
    
    # Clean target downloads  
    docker exec test-deluge-target bash -c '
        # Remove movie/tv subdirs
        rm -rf /downloads/movies/* /downloads/tv/* 2>/dev/null
        # Remove torrent folders (anything that is not movies/tv directories)
        find /downloads -maxdepth 1 -type d ! -name downloads ! -name movies ! -name tv -exec rm -rf {} + 2>/dev/null
    ' || true
    
    log_info "Downloaded files cleaned"
}

# Full cleanup - all state
clean_all() {
    log_info "Performing full cleanup..."
    
    clean_deluge_torrents "localhost" "18112" "deluge-source"
    clean_deluge_torrents "localhost" "18113" "deluge-target"
    clean_radarr "localhost" "17878"
    clean_sonarr "localhost" "18989"
    clean_mock_indexer
    clean_transferarr_state
    clean_downloads
    
    log_info "Full cleanup complete"
}

# Reset volumes - complete reset requiring service restart
reset_volumes() {
    log_warn "Resetting Docker volumes - this will require restarting services"
    
    # Stop services
    docker compose -f "$COMPOSE_FILE" down
    
    # Remove volumes
    docker compose -f "$COMPOSE_FILE" down -v
    
    log_info "Volumes reset. Run 'docker compose -f docker/docker-compose.test.yml up -d' to restart"
}

# Cleanup just torrents
clean_torrents() {
    log_info "Cleaning torrents only..."
    
    clean_deluge_torrents "localhost" "18112" "deluge-source"
    clean_deluge_torrents "localhost" "18113" "deluge-target"
    clean_mock_indexer
    clean_downloads
    
    log_info "Torrents cleaned"
}

# Main
case "${1:-all}" in
    all)
        clean_all
        ;;
    torrents)
        clean_torrents
        ;;
    state)
        clean_transferarr_state
        ;;
    volumes)
        reset_volumes
        ;;
    downloads)
        clean_downloads
        ;;
    radarr)
        clean_radarr "localhost" "17878"
        ;;
    sonarr)
        clean_sonarr "localhost" "18989"
        ;;
    indexer)
        clean_mock_indexer
        ;;
    *)
        echo "Usage: $0 [all|torrents|state|volumes|downloads|radarr|sonarr|indexer]"
        echo ""
        echo "Commands:"
        echo "  all       - Clean all state (default)"
        echo "  torrents  - Clean only Deluge torrents"
        echo "  state     - Clean only transferarr state"
        echo "  volumes   - Reset Docker volumes (requires restart)"
        echo "  downloads - Clean downloaded files only"
        echo "  radarr    - Clean Radarr queue and movies"
        echo "  sonarr    - Clean Sonarr queue and series"
        echo "  indexer   - Clean mock indexer torrents"
        exit 1
        ;;
esac

exit 0
