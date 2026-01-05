#!/bin/bash
# run_tests.sh - Simplified test runner for Transferarr
#
# Usage:
#   ./run_tests.sh [--docker|--local] [pytest args...]
#
# Examples:
#   ./run_tests.sh                                    # Run all tests in Docker (default)
#   ./run_tests.sh --docker tests/integration/ -v    # Run integration tests in Docker
#   ./run_tests.sh --local tests/integration/ -v -s  # Run integration tests locally
#   ./run_tests.sh -k "lifecycle" -v                 # Run tests matching "lifecycle"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.test.yml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default mode
MODE="docker"
SKIP_CLEANUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker)
            MODE="docker"
            shift
            ;;
        --local)
            MODE="local"
            shift
            ;;
        --no-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [--docker|--local] [--no-cleanup] [pytest args...]"
            echo ""
            echo "Options:"
            echo "  --docker      Run tests in Docker container (default)"
            echo "  --local       Run tests using local Python environment"
            echo "  --no-cleanup  Skip cleaning up the test environment before running tests"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                                    # All tests in Docker"
            echo "  ./run_tests.sh --no-cleanup                       # Run without cleanup"
            echo "  ./run_tests.sh --docker tests/integration/ -v     # Integration tests in Docker"
            echo "  ./run_tests.sh --local -k 'lifecycle' -v          # Filter tests locally"
            echo "  ./run_tests.sh tests/integration/test_torrent_lifecycle.py -v -s"
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

# Default pytest args if none provided
if [ $# -eq 0 ]; then
    PYTEST_ARGS="tests/integration/ -v"
else
    PYTEST_ARGS="$*"
fi

# Run cleanup unless skipped
if [ "$SKIP_CLEANUP" = false ]; then
    echo -e "${GREEN}🧹 Cleaning up test environment...${NC}"
    "$SCRIPT_DIR/docker/scripts/cleanup.sh" all
    echo ""
fi

if [ "$MODE" = "docker" ]; then
    echo -e "${GREEN}🐳 Running tests in Docker...${NC}"
    echo -e "${YELLOW}   pytest $PYTEST_ARGS${NC}"
    echo ""
    
    # Check if services are running
    if ! docker compose -f "$COMPOSE_FILE" ps --quiet radarr 2>/dev/null | grep -q .; then
        echo -e "${YELLOW}⚠️  Test services not running. Start them with:${NC}"
        echo "   docker compose -f docker/docker-compose.test.yml up -d"
        exit 1
    fi
    
    docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner $PYTEST_ARGS
else
    echo -e "${GREEN}🐍 Running tests locally...${NC}"
    echo -e "${YELLOW}   pytest $PYTEST_ARGS${NC}"
    echo ""
    
    # Check if venv is activated
    if [ -z "$VIRTUAL_ENV" ]; then
        echo -e "${YELLOW}⚠️  No virtual environment detected. Activate with:${NC}"
        echo "   source venv-dev/bin/activate"
        exit 1
    fi
    
    # Check if services are running
    if ! docker compose -f "$COMPOSE_FILE" ps --quiet radarr 2>/dev/null | grep -q .; then
        echo -e "${YELLOW}⚠️  Test services not running. Start them with:${NC}"
        echo "   docker compose -f docker/docker-compose.test.yml up -d"
        exit 1
    fi
    
    pytest $PYTEST_ARGS
fi
