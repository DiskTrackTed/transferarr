# Testing Guide

This document provides an overview of Transferarr's testing infrastructure.

## Quick Start

```bash
# Start test infrastructure
docker compose -f docker/docker-compose.test.yml up -d

# Run all integration tests
./run_tests.sh

# Run specific test category
./run_tests.sh tests/integration/lifecycle/ -v
./run_tests.sh tests/ui/fast/ -v

# Run specific test file
./run_tests.sh tests/integration/lifecycle/test_torrent_lifecycle.py -v
```

## Test Structure

```
tests/
    unit/                            # No Docker needed (<1 min)
        test_history_service.py
    
    integration/
        api/                         # API tests (~3 min)
        lifecycle/                   # Core migration flows (~15 min)
        persistence/                 # State recovery (~20 min)
        transfers/                   # Concurrent/type tests (~15 min)
        config/                      # Configuration tests (~10 min)
        edge/                        # Edge cases & errors (~10 min)
    
    ui/
        fast/                        # UI-only tests (~5 min)
        crud/                        # CRUD operations (~8 min)
        e2e/                         # Real transfers (~15 min)
    
    catalog_tests/                   # Manual only (@pytest.mark.slow)
```

## Test Infrastructure

The testing environment uses Docker Compose to spin up isolated instances of all required services:

| Service | Port | Purpose |
|---------|------|---------|
| Deluge Source | 18112 (Web), 18846 (RPC) | Source download client |
| Deluge Target | 18113 (Web), 18847 (RPC) | Target download client |
| Radarr | 17878 | Movie manager |
| Sonarr | 18989 | TV show manager |
| Mock Indexer | 9696 | Torznab indexer for test torrents |
| SFTP Server | 2222 | File transfer between clients |
| Tracker | 6969 | OpenTracker for torrent seeding |
| Transferarr | 10445 | Application under test |

### Test Runner

The `run_tests.sh` script handles:
- Environment cleanup before tests
- Running tests in Docker
- Proper pytest configuration

```bash
./run_tests.sh [--no-cleanup] [pytest args...]
```

**Options:**
- `--no-cleanup` - Skip pre-test cleanup

### Cleanup

Reset the test environment:

```bash
# Full cleanup (torrents, state, media managers)
./docker/scripts/cleanup.sh all

# Specific cleanup targets
./docker/scripts/cleanup.sh torrents    # Just torrents
./docker/scripts/cleanup.sh state       # Transferarr state
./docker/scripts/cleanup.sh config      # Regenerate config
./docker/scripts/cleanup.sh radarr      # Clear Radarr
./docker/scripts/cleanup.sh sonarr      # Clear Sonarr
./docker/scripts/cleanup.sh indexer     # Clear mock indexer
./docker/scripts/cleanup.sh downloads   # Clear downloaded files
./docker/scripts/cleanup.sh volumes     # Full volume reset (requires restart)
```

## Test Categories

### Unit Tests

Fast tests that don't require Docker infrastructure.

**Location:** `tests/unit/`

**Coverage:**
- HistoryService SQLite operations
- Threading and concurrency
- Cleanup and retention

### Integration Tests

End-to-end tests verifying the complete torrent migration lifecycle.

**Location:** `tests/integration/`

| Category | Path | Description |
|----------|------|-------------|
| API | `api/` | Transfer history API endpoints |
| Lifecycle | `lifecycle/` | Radarr/Sonarr migration flows |
| Persistence | `persistence/` | State recovery across restarts |
| Transfers | `transfers/` | Concurrent and transfer type tests |
| Config | `config/` | History config, client routing |
| Edge | `edge/` | Edge cases, error handling |

📖 **Full documentation:** [docs/integration-tests.md](../docs/integration-tests.md)

### UI Tests

Playwright-based browser automation tests using the Page Object Model pattern.

**Location:** `tests/ui/`

| Category | Path | Description |
|----------|------|-------------|
| Fast | `fast/` | Navigation, dashboard, settings (no transfers) |
| CRUD | `crud/` | Client and connection CRUD via modals |
| E2E | `e2e/` | Full workflows with real transfers |

📖 **Full documentation:** [docs/ui-tests.md](../docs/ui-tests.md)

### Catalog Tests

Validation tests for movie/show catalogs used in integration tests.

**Location:** `tests/catalog_tests/`

These are marked `@pytest.mark.slow` and excluded by default. Run manually:

```bash
./run_tests.sh tests/catalog_tests/ -v -m slow
```

## Test Fixtures

Key fixtures defined in `tests/conftest.py`:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `docker_services` | session | Ensures all containers are healthy |
| `radarr_client` | session | Radarr API client |
| `sonarr_client` | session | Sonarr API client |
| `deluge_source` | session | Source Deluge RPC client |
| `deluge_target` | session | Target Deluge RPC client |
| `create_torrent` | session | Factory to create test torrents |
| `transferarr` | function | Start/stop/restart transferarr |
| `clean_test_environment` | function | Standard setup/teardown |
| `lifecycle_runner` | function | Unified migration test runner |

## Writing Tests

### Integration Test Pattern

```python
class TestExample:
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_migration(self, lifecycle_runner):
        lifecycle_runner.run_migration_test('radarr')
```

### UI Test Pattern

```python
def test_dashboard_shows_stats(self, dashboard_page):
    dashboard_page.goto()
    stats = dashboard_page.get_all_stats()
    assert stats['active'] >= 0
```

## Troubleshooting

**Tests fail with "service not healthy":**
```bash
docker compose -f docker/docker-compose.test.yml ps
docker compose -f docker/docker-compose.test.yml logs <service>
```

**Permission errors on config save:**
```bash
./docker/scripts/cleanup.sh config
```

**Stale state between test runs:**
```bash
./docker/scripts/cleanup.sh all
```

**Mock indexer has no torrents:**
```bash
curl http://localhost:9696/torrents
```
