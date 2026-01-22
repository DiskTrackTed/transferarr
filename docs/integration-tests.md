# Integration Tests

*Last Updated: 2026-01-19*

## Overview

Transferarr has 55+ integration tests organized into 6 categories, covering the complete torrent migration lifecycle for both Radarr and Sonarr, plus history tracking and API tests.

## Directory Structure

```
tests/integration/
    api/                    # API endpoint tests (~3 min)
    lifecycle/              # Core migration flows (~15 min)
    persistence/            # State recovery tests (~20 min)
    transfers/              # Concurrent & type tests (~15 min)
    config/                 # Configuration tests (~10 min)
    edge/                   # Edge cases & errors (~10 min)
```

## Running Tests

```bash
# Start test infrastructure
docker compose -f docker/docker-compose.test.yml up -d

# Run all integration tests
./run_tests.sh tests/integration/ -v

# Run specific category
./run_tests.sh tests/integration/lifecycle/ -v
./run_tests.sh tests/integration/api/ -v

# Run specific file
./run_tests.sh tests/integration/lifecycle/test_torrent_lifecycle.py -v
```

## Test Files

### lifecycle/

#### [test_torrent_lifecycle.py](../tests/integration/lifecycle/test_torrent_lifecycle.py)
Core happy-path tests for Radarr movie migrations.

| Test | Description |
|------|-------------|
| `test_complete_transfer_lifecycle` | Full flow: Radarr queue → source seeding → copy → target seeding → cleanup |
| `test_discovers_existing_torrent` | Transferarr discovers torrent already seeding before startup |

#### [test_sonarr_lifecycle.py](../tests/integration/lifecycle/test_sonarr_lifecycle.py)
TV show migration tests using the unified `LifecycleRunner`.

| Test | Description |
|------|-------------|
| `test_single_episode_migration` | Single episode transfer |
| `test_multi_episode_torrent` | Torrent with episodes 1-2 |
| `test_season_pack_migration` | Full season pack (10GB) |

### persistence/

#### [test_state_persistence.py](../tests/integration/persistence/test_state_persistence.py)
Verifies state survives container restarts and file corruption.

| Test | Description |
|------|-------------|
| `test_state_survives_restart_during_copying` | Restart mid-transfer, verify completion |
| `test_state_survives_restart_target_seeding` | Restart after target seeding, verify cleanup |
| `test_restart_after_radarr_import_during_copying` | Restart after Radarr import completes (queue empty), verify transfer resumes |
| `test_state_file_corruption_recovery` | Corrupt state.json, verify recovery |
| `test_state_file_delete_recovery` | Delete state.json, verify recovery |
| `test_multiple_torrents_state_persistence` | 3 torrents at different states, verify all restored |

### transfers/

#### [test_concurrent_transfers.py](../tests/integration/transfers/test_concurrent_transfers.py)
Parallel transfer handling with `max_workers=3`.

| Test | Description |
|------|-------------|
| `test_two_simultaneous_transfers` | 2 torrents in parallel |
| `test_three_simultaneous_max_concurrency` | 3 torrents at max capacity |
| `test_queue_overflow` | 5 torrents (3 start, 2 wait for slots) |
| `test_mixed_state_concurrency` | Torrents at different lifecycle stages |

#### [test_transfer_types.py](../tests/integration/transfers/test_transfer_types.py)
Parameterized test for all 5 transfer type combinations.

| Transfer Type | Source | Destination |
|---------------|--------|-------------|
| `sftp-to-local` | SFTP | Local |
| `local-to-sftp` | Local | SFTP |
| `sftp-to-sftp` | SFTP | SFTP |
| `local-to-local` | Local | Local |
| `multi-target` | SFTP | SFTP (multiple targets) |

### edge/

#### [test_error_handling.py](../tests/integration/edge/test_error_handling.py)
Error scenarios and recovery behavior.

| Test | Description |
|------|-------------|
| `test_queue_item_removed_while_tracking` | Queue item removed from Radarr while Transferarr is tracking |
| `test_source_torrent_removed_during_copying` | Source torrent deleted mid-COPYING |
| `test_target_torrent_disappears_after_copied` | Target torrent removed after COPIED |
| `test_radarr_connection_failure_and_recovery` | Radarr unavailable, verify recovery |
| `test_source_client_unavailable_at_start` | Source Deluge down at startup |
| `test_torrent_found_on_target_without_outbound_connection` | Torrent on target but no connection configured |

#### [test_edge_cases.py](../tests/integration/edge/test_edge_cases.py)
Unusual filenames, large files, and boundary conditions.

| Test | Description |
|------|-------------|
| `test_special_characters_in_filename` | Parentheses, brackets, dashes |
| `test_spaces_in_torrent_name` | Spaces instead of dots |
| `test_2_5gb_torrent_transfer` | Large file with speed tracking |
| `test_multi_file_torrent_transfer` | 5 files in one torrent |
| `test_torrent_already_on_target_skips_copy` | Duplicate detection, skips COPYING phase |

### config/

#### [test_client_routing.py](../tests/integration/config/test_client_routing.py)
Multi-target routing with two destination Deluge instances.

| Test | Description |
|------|-------------|
| `test_multi_target_routing` | Route to different targets based on connection config |

#### [test_history_config.py](../tests/integration/config/test_history_config.py)
History configuration behavior tests.

| Test | Description |
|------|-------------|
| `test_history_disabled_no_records_created` | No history records when `history.enabled=false` |
| `test_track_progress_false_skips_progress_updates` | No byte progress updates when `history.track_progress=false` |
| `test_retention_prunes_old_entries_unit` | Unit test for retention pruning logic |
| `test_retention_config_is_applied` | Verify `history.retention_days` config is respected |

### api/

#### [test_transfer_history_api.py](../tests/integration/api/test_transfer_history_api.py)
Transfer History API endpoint tests (23 tests).

| Test Class | Description |
|------|-------------|
| `TestTransfersListEndpoint` | GET /transfers pagination, filtering, sorting |
| `TestActiveTransfersEndpoint` | GET /transfers/active real-time list |
| `TestTransferStatsEndpoint` | GET /transfers/stats totals |
| `TestSingleTransferEndpoint` | GET /transfers/<id> detail |
| `TestTransferHistoryIntegration` | End-to-end record creation during transfer |
| `TestDeleteTransferEndpoint` | DELETE /transfers/<id> single record deletion |
| `TestClearTransfersEndpoint` | DELETE /transfers batch clearing by status |

---

## Test Framework

### Key Fixtures (`tests/conftest.py`)

```python
TIMEOUTS = {
    'service_startup': 120,
    'torrent_transfer': 300,
    'state_transition': 120,
    'api_response': 30,
    'torrent_seeding': 60,
}
```

- `docker_services` – Ensures containers are healthy
- `radarr_client`, `sonarr_client` – REST API clients
- `deluge_source`, `deluge_target` – RPC clients
- `create_torrent(name, size_mb, multi_file)` – Creates test torrents
- `transferarr` – Start/stop/restart container
- `lifecycle_runner` – Unified 7-step migration runner
- `clean_test_environment` – Setup/teardown fixture

### Utilities (`tests/utils.py`)

- `wait_for_queue_item_by_hash()` – Wait for torrent in Radarr queue
- `wait_for_sonarr_queue_item_by_hash()` – Wait for torrent in Sonarr queue
- `wait_for_transferarr_state()` – Wait for state transition
- `movie_catalog` / `show_catalog` – Unique test items to avoid collisions
- `QueueItemError` – Exception for failed queue items with retry support

### LifecycleRunner (`tests/integration/helpers.py`)

Standardized migration test pattern:

```python
def test_movie_migration(self, lifecycle_runner):
    lifecycle_runner.run_migration_test('radarr', item_type='movie')

def test_season_pack(self, lifecycle_runner):
    lifecycle_runner.run_migration_test('sonarr', item_type='season-pack')
```

---

## Test Infrastructure

### Docker Services

| Service | Host Ports | Purpose |
|---------|------------|---------|
| Tracker | 6969 | OpenTracker for seeding |
| SFTP | 2222 | File transfers |
| Deluge Source | 18112, 18846 | Source client |
| Deluge Target | 18113, 18847 | Target client |
| Deluge Target 2 | 18114, 18848 | Second target (routing tests) |
| Radarr | 17878 | Movie manager |
| Sonarr | 18989 | TV manager |
| Mock Indexer | 9696 | Fake Torznab API |
| Transferarr | 10445 | Application under test |

### Credentials

- **Deluge Web**: `testpassword`
- **Deluge RPC**: user `transferarr`, password `testpassword`
- **SFTP**: user `testuser`, password `testpass`

---

## Deferred Tests

| Test | Reason |
|------|--------|
| API Smoke Tests | Lower priority; core functionality covered |

---

## Planning Documents (Archive)

Detailed planning and implementation notes:
- [testing-infrastructure.md](plans/testing-infrastructure.md) – Original Phase 5 infrastructure setup
- [integration-tests-expansion.md](plans/integration-tests-expansion.md) – Phase 5a/5b test specifications
- [integration-tests-phase-6.md](plans/integration-tests-phase-6.md) – Phase 6 (Sonarr, concurrency, transfer types)
- [transfer-type-testing.md](plans/transfer-type-testing.md) – Transfer type matrix design
