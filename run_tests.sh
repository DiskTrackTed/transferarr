#!/bin/bash
# run_tests.sh - Test runner for Transferarr
#
# Usage:
#   ./run_tests.sh [--no-cleanup] [pytest args...]
#
# Examples:
#   ./run_tests.sh                                    # Run all integration tests
#   ./run_tests.sh tests/integration/ -v             # Run integration tests with verbose
#   ./run_tests.sh -k "lifecycle" -v                 # Run tests matching "lifecycle"
#   ./run_tests.sh tests/ui/ -v                      # Run UI tests
#   ./run_tests.sh tests/ui/ -v --headed             # Run UI tests with visible browser

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.test.yml"

# Project name must match hardcoded values in tests/conftest.py
export COMPOSE_PROJECT_NAME="transferarr_test"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SKIP_CLEANUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [--no-cleanup] [pytest args...]"
            echo ""
            echo "Options:"
            echo "  --no-cleanup  Skip cleaning up the test environment before running tests"
            echo ""
            echo "Examples:"
            echo "  ./run_tests.sh                                       # All integration tests"
            echo "  ./run_tests.sh --no-cleanup                          # Run without cleanup"
            echo "  ./run_tests.sh tests/integration/ -v                 # All integration tests"
            echo "  ./run_tests.sh tests/integration/lifecycle/ -v       # Lifecycle tests"
            echo "  ./run_tests.sh tests/integration/api/ -v             # API tests"
            echo "  ./run_tests.sh tests/ui/ -v                          # All UI tests"
            echo "  ./run_tests.sh tests/ui/fast/ -v                     # Fast UI tests"
            echo "  ./run_tests.sh tests/unit/ -v                        # Unit tests"
            echo "  ./run_tests.sh -k 'lifecycle' -v                     # Filter tests"
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

echo -e "${GREEN}🐳 Running tests in Docker...${NC}"
echo -e "${YELLOW}   pytest $PYTEST_ARGS${NC}"
echo ""

# Export UID/GID so test artifacts are owned by host user
# Note: Can't use UID directly as it's readonly in bash
export HOST_UID=$(id -u)
export HOST_GID=$(id -g)

# Create test-results directory (owned by current user, not root)
mkdir -p "$SCRIPT_DIR/test-results"

# Check if services are running
if ! docker compose -f "$COMPOSE_FILE" ps --quiet radarr 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}⚠️  Test services not running. Start them with:${NC}"
    echo "   docker compose -f docker/docker-compose.test.yml up -d"
    exit 1
fi

docker compose -f "$COMPOSE_FILE" --profile test run --rm test-runner $PYTEST_ARGS
