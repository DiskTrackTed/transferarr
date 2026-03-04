# CI/CD

*Last Updated: 2026-03-03*

## Overview

Transferarr uses GitHub Actions for continuous integration with two workflows:

1. **Tests** (`tests.yml`) — Runs the full test suite on every push/PR to `main`
2. **Weekly Latest Images** (`weekly-latest.yml`) — Compatibility testing against `:latest` Docker images

Both workflows use the same Docker Compose test infrastructure (`docker/docker-compose.test.yml`) with pinned image versions that can be overridden via environment variables.

## Workflow Files

```
.github/workflows/
    tests.yml              # Main CI — full test suite
    weekly-latest.yml      # Weekly — :latest image compatibility
```

## Tests Workflow (`tests.yml`)

The primary CI workflow. Runs the full test matrix in parallel.

### Triggers

| Trigger | Condition |
|---------|-----------|
| Push to `main` | Automatic (skips docs-only changes) |
| Pull request to `main` | Automatic (skips docs-only changes) |
| Manual dispatch | Select specific test category or "all" |

**Docs-only skip**: Changes to `*.md`, `docs/**`, and `.github/copilot-instructions.md` do not trigger the workflow.

### Test Matrix

All categories run in parallel with `fail-fast: false` (one failure doesn't cancel others):

| Category | Path | Timeout | Docker | Description |
|----------|------|---------|--------|-------------|
| `unit` | `tests/unit/` | 5 min | No | Core logic, no external deps |
| `integration-api` | `tests/integration/api/` | 30 min | Yes | REST API and CRUD tests |
| `integration-auth-user` | `tests/integration/auth/user/` | 30 min | Yes | User authentication flows |
| `integration-auth-api-key` | `tests/integration/auth/api-key/` | 30 min | Yes | API key authentication |
| `integration-lifecycle` | `tests/integration/lifecycle/` | 20 min | Yes | Torrent migration end-to-end |
| `integration-persistence` | `tests/integration/persistence/` | 30 min | Yes | State recovery and restart |
| `integration-transfers` | `tests/integration/transfers/` | 30 min | Yes | Transfer type variations |
| `integration-config` | `tests/integration/config/` | 15 min | Yes | Client routing configs |
| `integration-edge` | `tests/integration/edge/` | 30 min | Yes | Error handling, edge cases |
| `ui-fast` | `tests/ui/fast/` | 10 min | Yes | UI rendering, navigation |
| `ui-crud` | `tests/ui/crud/` | 30 min | Yes | Client/connection CRUD via UI |
| `ui-e2e` | `tests/ui/e2e/` | 30 min | Yes | End-to-end UI + transfers |
| `ui-auth-pages` | `tests/ui/auth/pages/` | 30 min | Yes | Login/setup page tests |
| `ui-auth-settings` | `tests/ui/auth/settings/` | 30 min | Yes | Auth settings tab tests |

### Execution Flow

```
                                    ┌─────────────────┐
                                    │  Check if should │
                                    │      run         │
                                    └────────┬────────┘
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                   needs_docker=false  needs_docker=true        │
                          │                  │                  │
                  ┌───────▼───────┐  ┌───────▼───────┐          │
                  │ Setup Python  │  │ Free disk     │          │
                  │ Install deps  │  │ Build images  │          │
                  │ Run pytest    │  │ Start services│          │
                  └───────┬───────┘  │ Run tests     │          │
                          │          └───────┬───────┘          │
                          │                  │                  │
                          └──────────────────┼──────────────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  On failure:    │
                                    │  Upload results │
                                    │  Upload logs    │
                                    └────────┬────────┘
                                             │
                                    ┌────────▼────────┐
                                    │    Cleanup      │
                                    │  docker down -v │
                                    └─────────────────┘
```

For Docker-based tests:
1. **Free disk space** — Removes .NET SDK, Android, CodeQL to free ~15GB on the runner
2. **Build Transferarr image** — `./build.sh` creates the `transferarr:dev` image
3. **Build test infrastructure** — Builds locally-built images (mock-indexer, registrar, torrent-creator)
4. **Start services with retry** — `docker compose up -d --wait` with up to 3 attempts (handles transient network failures)
5. **Run tests** — `./run_tests.sh <path> -v --tb=short`
6. **Cleanup** — Always runs `docker compose down -v --remove-orphans`

### Branch Protection

The `test-summary` job aggregates all matrix results into a single `test` status check. This is the required status check for merging PRs to `main`:

- All matrix jobs must pass → `test-summary` reports success
- Any matrix job fails → `test-summary` reports failure → PR cannot merge

### Manual Dispatch

From the GitHub Actions tab, select "Tests" → "Run workflow" and choose a specific test category. Only the selected category runs; others are skipped via the `should_run` check.

### Artifacts

On failure, each job uploads:
- **`{category}-results/`** — Test output, Playwright screenshots and traces
- **`{category}-logs/`** — Full `docker compose logs` output

Artifacts are retained for **7 days**.

## Weekly Latest Images Workflow (`weekly-latest.yml`)

Detects breaking changes in upstream Docker images before they hit the main CI.

### Why This Exists

The main `tests.yml` workflow uses **pinned image versions** for deterministic, reproducible builds. This means upstream breaking changes (like the [Deluge 2.2.0 `create_torrent` bug](plans/006-deluge-2.2.0-create-torrent-bug.md)) are invisible until we manually update the pins.

The weekly workflow catches these proactively by testing against `:latest` on a schedule.

### Triggers

| Trigger | Condition |
|---------|-----------|
| Schedule | Every Sunday at 06:00 UTC |
| Manual dispatch | On-demand with option to create/skip GitHub issue on failure |

### Test Categories

Runs a **slim subset** of the full matrix — enough to catch breaking changes without the full 30+ minute suite:

| Category | Path | Timeout | Why |
|----------|------|---------|-----|
| `unit` | `tests/unit/` | 5 min | Core logic still works |
| `integration-api` | `tests/integration/api/` | 30 min | Service communication works |
| `integration-lifecycle` | `tests/integration/lifecycle/` | 20 min | End-to-end torrent flow works |
| `ui-fast` | `tests/ui/fast/` | 10 min | Web UI still renders |

### How It Overrides Image Versions

The workflow sets env vars that override the `docker-compose.test.yml` defaults:

```yaml
env:
  DELUGE_TAG: latest
  RADARR_TAG: latest
  SONARR_TAG: latest
  OPENSSH_TAG: latest
  ALPINE_TAG: latest
```

The compose file uses these with fallback syntax: `image: lscr.io/linuxserver/deluge:${DELUGE_TAG:-2.1.1-r10-ls324}`.
When the env var is set, it takes precedence. When unset (normal CI), the pinned default is used.

### Additional Steps (vs. main workflow)

The weekly workflow includes extra diagnostics:

1. **`docker compose pull --ignore-buildable`** — Explicitly pulls latest images before starting
2. **Log pulled image versions** — Records the actual image digests that were pulled
3. **Log running service versions** — Captures `Linuxserver.io version: X.Y.Z` from container logs

This makes it easy to identify *which* image update caused a failure.

### Failure Notification

When the workflow fails, the `notify` job creates a GitHub issue:

- **Label**: `bug`, `ci-compatibility`
- **Title**: `Weekly :latest compatibility test failed (YYYY-MM-DD)`
- **Body**: Link to workflow run + action items
- **Deduplication**: If an open issue with `ci-compatibility` label already exists, adds a comment instead of creating a duplicate

The `create_issue` input (manual dispatch only) controls whether an issue is created — useful for debugging without creating noise.

### Responding to Weekly Failures

1. Open the failed workflow run from the GitHub issue link
2. Check which categories failed and read the logs
3. Identify which image update caused the failure (compare "Running service versions" with pinned versions)
4. Choose a response:
   - **Fix in Transferarr**: Implement a workaround, update the pin to include the new version
   - **Skip the broken version**: Keep the current pin, note the incompatibility
   - **Report upstream**: File a bug with the upstream project
5. Close the `ci-compatibility` issue once resolved

## Image Version Pinning

All external Docker images in `docker-compose.test.yml` are pinned to specific versions for deterministic CI.

### Pinned Images

| Env Var | Default Tag | Image | Notes |
|---------|-------------|-------|-------|
| `DELUGE_TAG` | `2.1.1-r10-ls324` | `lscr.io/linuxserver/deluge` | Pinned to 2.1.1 — 2.2.0 has `create_torrent` bug |
| `RADARR_TAG` | `6.0.4.10291-ls294` | `lscr.io/linuxserver/radarr` | |
| `SONARR_TAG` | `4.0.16.2944-ls303` | `lscr.io/linuxserver/sonarr` | |
| `OPENSSH_TAG` | `10.2_p1-r0-ls218` | `lscr.io/linuxserver/openssh-server` | |
| `ALPINE_TAG` | `3.21` | `alpine` | Utility container only |

### Unpinnable Images

| Image | Reason |
|-------|--------|
| `lednerb/opentracker-docker` | Only `latest` and `pre-update` tags exist |
| `transferarr:dev` | Built locally by `./build.sh` |
| mock-indexer, test-runner, registrar, torrent-creator | Built locally; Python base pinned to `bookworm` |

### Updating a Pin

1. Find the new tag on Docker Hub: `https://hub.docker.com/r/linuxserver/{image}/tags`
2. Use the full linuxserver tag format: `{app_version}-ls{build_number}` (e.g., `6.0.4.10291-ls294`)
3. Update the default in `docker-compose.test.yml`: `${RADARR_TAG:-NEW_TAG}`
4. Update the table in the [Image Version Pinning](../.github/copilot-instructions.md#image-version-pinning) section of copilot-instructions.md
5. Update the table above in this document
6. Test locally: `docker compose -f docker/docker-compose.test.yml up -d`

### Testing with Latest Locally

```bash
# Override all pins with :latest
DELUGE_TAG=latest RADARR_TAG=latest SONARR_TAG=latest \
  OPENSSH_TAG=latest ALPINE_TAG=latest \
  docker compose -f docker/docker-compose.test.yml up -d

# Override a single image
DELUGE_TAG=latest docker compose -f docker/docker-compose.test.yml up -d

# Verify resolved images
docker compose -f docker/docker-compose.test.yml config --images
```

## Concurrency

Both workflows use concurrency groups to cancel stale runs:

| Workflow | Group | Behavior |
|----------|-------|----------|
| Tests | `Tests-{ref}` | New push to same branch cancels in-progress run |
| Weekly Latest | `weekly-latest` | Only one weekly run at a time |

## Key Files

| File | Purpose |
|------|---------|
| `.github/workflows/tests.yml` | Main CI workflow |
| `.github/workflows/weekly-latest.yml` | Weekly `:latest` compatibility |
| `docker/docker-compose.test.yml` | Test infrastructure (all services) |
| `run_tests.sh` | Test runner script (cleanup + pytest) |
| `build.sh` | Docker image build script |
| `docker/scripts/cleanup.sh` | Reset test environment |
| `docker/scripts/register-services.py` | Auto-configures Radarr/Sonarr |
| `docker/services/test-runner/Dockerfile` | Test runner image (pytest + Playwright) |
