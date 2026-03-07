# Copilot Instructions for Transferarr

## Project Overview
Transferarr is a Python application that automates torrent migration between download clients (primarily Deluge instances) across different servers. It integrates with media managers (Radarr/Sonarr) to track torrents and uses SFTP/local transfers to move files.

## Architecture

### Core Components
- **`transferarr/main.py`** - Entry point: loads config, starts `TorrentManager` thread, runs Flask web server on port 10444
- **`transferarr/services/torrent_service.py`** (`TorrentManager`) - Central orchestrator managing the torrent lifecycle, connections, and state persistence
- **`transferarr/services/transfer_connection.py`** (`TransferConnection`) - Handles file transfers between source/destination with a ThreadPoolExecutor (max 3 concurrent transfers)
- **`transferarr/services/torrent_transfer.py`** (`TorrentTransferHandler`) - Handles torrent-based transfer states (TORRENT_*), creating transfer torrents and managing BitTorrent-based file transfer
- **`transferarr/services/tracker.py`** (`BitTorrentTracker`) - Lightweight HTTP BitTorrent tracker for peer discovery during torrent-based transfers
- **`transferarr/services/history_service.py`** (`HistoryService`) - SQLite-based transfer history tracking with thread-safe connection-per-thread pattern
- **`transferarr/services/media_managers.py`** - Radarr/Sonarr API integration using devopsarr Python SDKs

### Data Flow
1. `TorrentManager` polls Radarr/Sonarr queues for new torrents
2. Torrents are tracked with state machine (`TorrentState` enum in `models/torrent.py`)
3. Transfer method depends on connection type:
   - **SFTP/Local**: `TransferConnection` copies files via SFTP or local storage, then adds `.torrent` file to destination client
   - **Torrent**: `TorrentTransferHandler` creates a transfer torrent on source, target downloads via BitTorrent P2P through the private tracker
4. Original torrent is added to destination client (via magnet for torrent transfers), then removed from source

### Client Abstractions
- **`clients/download_client.py`** (`DownloadClientBase`) - Abstract base class defining the download client interface (all clients must implement this)
- **`clients/registry.py`** (`ClientRegistry`) - Decorator-based registry for client types with `@ClientRegistry.register("type")` pattern
- **`clients/config.py`** (`ClientConfig`) - Dataclass for download client configuration with `from_dict()` factory method
- **`clients/deluge.py`** - Supports both RPC (`deluge-client`) and Web UI JSON API connections
- **`clients/ftp.py`** (`SFTPClient`) - pysftp wrapper supporting SSH config aliases or direct credentials
- **`clients/transfer_client.py`** - Composite clients (e.g., `LocalAndSFTPClient`) for source→destination transfers

## Key Patterns

### Configuration
All configuration is JSON-based (`config.json`). Structure:
```json
{
  "media_managers": [{"type": "radarr|sonarr", "host", "port", "api_key"}],
  "download_clients": {"name": {"type": "deluge", "connection_type": "rpc|web", ...}},
  "connections": {"name": {"from": "client_name", "to": "client_name", "transfer_config": {...}}},
  "history": {"enabled": true, "retention_days": 90, "track_progress": true},
  "auth": {"enabled": true, "username": "admin", "password_hash": "$2b$...", "session_timeout_minutes": 60},
  "api": {"key": "tr_...", "key_required": true}
}
```

### History Configuration
- `history.enabled` (default: `true`) - Enable/disable history tracking
- `history.retention_days` (default: `90`) - Days to keep history records (null = forever)
- `history.track_progress` (default: `true`) - Update byte progress during transfers

### Authentication Configuration
- `auth.enabled` (default: `false`) - Enable/disable web UI authentication
- `auth.username` - Login username
- `auth.password_hash` - Bcrypt-hashed password (use `hash_password()` from `auth.py`)
- `auth.session_timeout_minutes` (default: `60`) - Session duration (0 = no timeout). **Changes require app restart**

### API Configuration
- `api.key` (default: `null`) - The API key for programmatic access
- `api.key_required` (default: `false`) - Whether API key is required for unauthenticated requests. **Cannot be enabled when user auth is disabled.**

### Tracker Configuration
- `tracker.enabled` (default: `true`) - Enable/disable the BitTorrent tracker
- `tracker.port` (default: `6969`) - Tracker listen port
- `tracker.external_url` (required for torrent transfers) - URL clients use to reach tracker (e.g., `http://transferarr:6969/announce`)
- `tracker.announce_interval` (default: `60`) - Seconds between peer re-announces
- `tracker.peer_expiry` (default: `120`) - Seconds before a peer is considered expired

### Torrent Transfer Architecture

Torrent-based transfers use BitTorrent protocol instead of SFTP. **No filesystem access required** - all operations via Deluge RPC/Web API.

**Key Components:**
- **`TorrentTransferHandler`** (`services/torrent_transfer.py`) - State machine for TORRENT_* states
- **`BitTorrentTracker`** (`services/tracker.py`) - HTTP tracker with whitelist-based peer discovery
- **`TransferConnection.is_torrent_transfer`** - Property to check transfer type

**Transfer Flow:**
1. Create transfer torrent on source (unique hash via tracker URL, `private=False` for BEP 9)
2. Register hash with tracker whitelist
3. Get magnet URI from source, add to target
4. Target announces to tracker, discovers source as peer
5. Target downloads files via BitTorrent P2P
6. Add original torrent to target via magnet (hash check passes instantly)
7. Transition to COPIED → TARGET_CHECKING → TARGET_SEEDING
8. Clean up transfer torrents from both clients, unregister from tracker

**Connection Config for Torrent Transfer:**
```json
{
  "from": "source-deluge",
  "to": "target-deluge",
  "transfer_config": {
    "type": "torrent",
    "destination_path": "/downloads"
  }
}
```

**Key Constraint:** No filesystem access to source or target. Everything via Deluge API:
- `create_torrent()` - Creates transfer torrent from existing files
- `get_magnet_uri()` - Gets magnet link for torrent
- `add_torrent_magnet()` - Adds torrent via magnet link
- `get_transfer_progress()` - Gets download progress
- `force_reannounce()` - Forces tracker re-announce for stall recovery
- `remove_torrent()` - Removes torrent from client

**Transfer Torrent Identification:**
- Transfer torrents are identified by tracker URL (our tracker) and optional `transferarr_tmp` label
- Helper: `is_transfer_torrent_name(name)` checks for `[TR-` prefix (used in state, not Deluge UI)
- Deluge shows the original path basename as the torrent name (ignores custom name parameter)

**Transfer Torrent UI Filtering:**
- Radarr/Sonarr may pick up transfer torrents from Deluge and add them to their queues
- `get_queue_updates()` in both `RadarrManager` and `SonarrManager` skips queue items whose `download_id` matches any tracked torrent's `transfer["hash"]` — prevents transfer torrents from ever entering `self.torrents`
- The existing detection in `update_torrents()` (hash-based `is_transfer` check → `torrents_to_remove`) remains as a safety net
- `TorrentManager.get_all_client_torrents()` filters transfer hashes from raw Deluge listings so they don't appear on the Torrents page
- `TorrentManager._get_transfer_hashes()` collects all active transfer hashes (lowercase) from `self.torrents`

**`Torrent.transfer` dict** (persisted in state.json):
```python
{
    "id": "f7e2a1",           # 6-char transfer ID
    "name": "[TR-f7e2a1] ...", # Transfer torrent name
    "hash": "abc123...",       # Transfer torrent info_hash
    "on_source": True,         # Whether transfer torrent exists on source
    "on_target": True,         # Whether transfer torrent exists on target
    "original_on_target": True,# Whether original torrent added to target
    "started_at": "ISO-8601",  # Transfer start time
    "last_progress_at": "ISO", # Last time bytes_downloaded increased
    "bytes_downloaded": 12345, # Bytes downloaded on target
    "total_size": 99999,       # Total torrent size
    "download_rate": 1024,     # Current download rate (bytes/sec)
    "retry_count": 0,          # Retry counter (max 3)
    "reannounce_count": 0,     # Stall re-announce counter (max 3)
    "cleaned_up": True,        # Set after transfer torrent cleanup
}
```

**Retry & Error Handling:**
- `MAX_RETRIES = 3` per transfer attempt. On max retries: `_cleanup_failed_transfer()` removes from both clients + tracker, then resets to `HOME_SEEDING` for future retry
- `STALL_THRESHOLD_SECONDS = 300` (5 min). Triggers `force_reannounce()` on both source and target, up to 3 times
- `_transfer_id` (history service ID) is serialized to state.json so history tracking survives restarts

**Restart Recovery:**
- `_reregister_pending_transfers()` runs after `load_torrents_state()` on startup
- Scans loaded torrents for TORRENT_* states or COPIED/TARGET_* with un-cleaned transfer data
- Re-registers transfer hashes with tracker (tracker state is in-memory only, lost on restart)
- Forces re-announce on source and target clients so peers rediscover each other

### State Persistence
- Torrent state saved to `state.json` via `save_callback` pattern on the `Torrent` model
- State auto-saves whenever `torrent.state` property is set (see `models/torrent.py` setter)
- State directory configured via `--state-dir` CLI argument (default: `/state` in Docker)
- State is loaded on startup in `TorrentManager.__init__()` after download clients/media managers are initialized
- `media_manager_type` is serialized to state to restore media manager instance on restart

### Threading Model
- `TorrentManager` runs in a daemon thread with periodic processing loop
- Each `TransferConnection` has its own `ThreadPoolExecutor` for concurrent file transfers
- Deluge clients use `threading.RLock` for connection safety

### Web API
Flask blueprints in `web/routes/`:
- `api/` - REST API package (`/api/v1/*`) organized by domain:
  - `__init__.py` - Blueprint registration
  - `system.py` - `/health`, `/config` endpoints
  - `download_clients.py` - Download client CRUD operations
  - `connections.py` - Transfer connection CRUD operations
  - `torrents.py` - `/torrents`, `/all_torrents` endpoints
  - `transfers.py` - `/transfers` history endpoints (list, stats, delete)
  - `manual_transfers.py` - `/transfers/destinations`, `/transfers/manual` manual transfer endpoints
  - `auth.py` - `/auth/*` authentication settings and API key management endpoints
  - `tracker.py` - `/tracker/settings` tracker configuration endpoints
  - `utilities.py` - `/browse` file browser endpoint
  - `validation.py` - `@validate_json` decorator for request validation
  - `responses.py` - Standardized response helpers (`success_response`, `error_response`, etc.)
- `schemas/` - Marshmallow validation schemas (`DownloadClientSchema`, `ConnectionSchema`, etc.)
- `ui.py` - HTML routes serving templates

**API Documentation**: Interactive Swagger UI available at `http://localhost:10444/apidocs`. Powered by `flasgger`.

**Input Validation**: POST/PUT endpoints use `@validate_json(SchemaClass)` decorator from `validation.py`. Validated data is available via `request.validated_data`. Schemas are in `web/schemas/__init__.py`.

**Service Layer**: Business logic is extracted into service classes in `web/services/`:
- `DownloadClientService` - CRUD operations for download clients (list, add, update, delete, test connection)
- `ConnectionService` - CRUD operations for transfer connections (list, add, update, delete, test connection)
- `TorrentService` - Read-only torrent listing (tracked torrents, all client torrents)
- `ManualTransferService` - Manual transfer validation and orchestration (get destinations, detect cross-seeds, validate and initiate transfers)
- `HistoryService` (in `transferarr/services/history_service.py`) - Transfer history tracking with SQLite persistence
- Custom exceptions (`NotFoundError`, `ConflictError`, `ValidationError`, `ConfigSaveError`) map to HTTP responses

**Security Features**:
- All passwords are masked as `"***"` in GET responses (download clients, connections, config)
- PUT endpoints preserve existing passwords if not provided in the request
- Test connection endpoint for download clients accepts optional `name` field to use stored password when editing existing clients
- Frontend edit modals show "Leave blank to keep current password" placeholder

**Frontend Notifications**:
- Toast notifications use `TransferarrNotifications` global (in `web/static/js/notifications.js`)
- Available methods: `success(title, message)`, `error(title, message)`, `warning(title, message)`, `info(title, message)`
- All settings modules (clients, connections, auth, tracker) use this for consistent user feedback
- Success/warning/info auto-dismiss after 5 seconds; errors persist until dismissed
- For persistent warnings (like "API key + auth disabled"), use inline alert elements instead of toasts
- **CRITICAL**: `TransferarrNotifications` is declared with `const` in a classic `<script>` tag. `const` globals do NOT automatically become `window` properties. The file explicitly sets `window.TransferarrNotifications = TransferarrNotifications;` so ES modules loaded via dynamic `import()` can access it. When creating new global objects in classic scripts, always add `window.X = X;` if ES modules need to reference them.

**Frontend Settings Patterns**:
- Settings tabs use ES modules loaded via dynamic `import()` (e.g., `settings-tracker.js`, `settings-auth.js`)
- **Dynamic Save Button**: The tracker tab uses a "Save Settings" / "Save and Apply" pattern. The button text changes dynamically based on whether restart-requiring fields (`port`, `enabled`) have been modified from their API-loaded values. Non-restart fields (`external_url`, `announce_interval`, `peer_expiry`) are applied live to the running tracker without restart. Store `originalValues` on load, compare on input change, and send `apply: true` in the PUT payload when restart-requiring fields changed.
- **Toggle switches**: The `<input type="checkbox">` inside `.toggle-switch` labels is hidden by CSS. In Playwright tests, click the `.toggle-switch` wrapper label, not the hidden checkbox. Use `.filter(has=page.locator('#checkbox-id'))` to target the right wrapper.
- **Number inputs**: When using Playwright `fill()` on number inputs that are pre-populated from API data, always call `clear()` first — otherwise `fill()` appends to the existing value instead of replacing it. Add `page.wait_for_load_state("networkidle")` before interacting with API-loaded form fields.

### Authentication Architecture

The web UI supports optional username/password authentication using Flask-Login and bcrypt.

**Core Components:**
- **`transferarr/auth.py`** - Password hashing, User model, config helpers, secret key management
- **`transferarr/web/routes/auth.py`** - Login/logout/setup page routes
- **`transferarr/web/routes/api/auth.py`** - Auth settings API (`/api/v1/auth/*`)

**Key Functions in `auth.py`:**
- `hash_password(password)` - Bcrypt hash for storing passwords
- `verify_password(password, hash)` - Verify password against hash
- `get_auth_config(config)` - Get auth section with defaults
- `is_auth_enabled(config)` - Check if auth is enabled AND configured
- `is_auth_configured(config)` - Check if user has completed setup
- `save_auth_config(config, updates)` - Save auth changes to config.json
- `get_or_create_secret_key(state_dir)` - Manage Flask session signing key

**Route Protection:**
- UI routes use `@auth_required` decorator (in `web/routes/ui.py`)
- API routes use `@api_auth_required` (in `web/routes/api/__init__.py`)
- Auth settings API uses `@auth_api_required` (allows access when auth disabled)
- Public routes: `/login`, `/setup`, `/api/v1/health`, static files

**First-Run Flow:**
1. No `auth` section in config → redirect to `/setup`
2. User creates account → `auth.enabled=true`, credentials stored
3. User skips setup → `auth.enabled=false`, no credentials needed

**Session Management:**
- Secret key stored in `<state_dir>/secret_key`
- Auto-generated 32-byte random key on first run
- Session timeout configurable (default 60 min, 0 = no timeout)
- "Remember me" extends session to 30 days

**Templates:**
- `login_base.html` - Minimal layout for login/setup (no sidebar)
- `pages/login.html` - Login form with remember me
- `pages/setup.html` - First-run setup with create/skip options
- `partials/settings_auth_tab.html` - Auth settings tab in Settings page

**API Endpoints:**
- `GET /api/v1/auth/settings` - Get auth config (no password_hash)
- `PUT /api/v1/auth/settings` - Update enabled/timeout
- `PUT /api/v1/auth/password` - Change password (requires login)

### API Key Authentication

The API supports optional API key authentication for programmatic access without a session.

**Config Structure:**
```json
{
  "api": {
    "key": "tr_abc123...",
    "key_required": true
  }
}
```

**Key Functions in `auth.py`:**
- `generate_api_key()` - Generate a new API key with `tr_` prefix
- `verify_api_key(provided, stored)` - Constant-time comparison for security
- `get_api_config(config)` - Get api section with defaults
- `is_api_key_required(config)` - Check if API key is required (key exists AND key_required=True)
- `save_api_config(config, updates)` - Save api changes to config.json
- `get_or_create_api_key(config)` - Get existing key or generate new one
- `check_api_key_in_request(config, request)` - Validate API key from request header/query param (shared utility for middleware)

**Authentication Flow (in `web/routes/api/__init__.py`):**
1. Health endpoint (`/api/v1/health`) always allowed
2. If auth not configured (setup pending) → allow all
3. If user logged in via session → allow (bypass API key)
4. If API key required → check `X-API-Key` header or `?apikey=` query param
5. If API key provided (even when not required) and valid → allow
6. Otherwise → 401 Unauthorized

**API Key Endpoints:**
- `GET /api/v1/auth/api-key` - Get API key settings (key, key_required)
- `PUT /api/v1/auth/api-key` - Update key_required setting
- `POST /api/v1/auth/api-key/generate` - Generate new API key (invalidates old key)
- `POST /api/v1/auth/api-key/revoke` - Revoke current API key

**Usage Examples:**
```bash
# Header authentication (preferred)
curl -H "X-API-Key: tr_abc123..." http://localhost:10444/api/v1/torrents

# Query parameter authentication
curl "http://localhost:10444/api/v1/torrents?apikey=tr_abc123..."
```

**UI Integration:**
- Settings page Auth tab includes API Key section
- View/copy current key (masked by default)
- Generate/regenerate key
- Revoke key
- Toggle key requirement

### Tracker Settings API

The tracker has a settings API for viewing and updating configuration.

**API Endpoints:**
- `GET /api/v1/tracker/settings` - Get tracker config and runtime status (running, port, active_transfers)
- `PUT /api/v1/tracker/settings` - Update tracker settings with optional `apply` flag

**PUT with `apply` flag:**
The PUT endpoint accepts an `apply: true` field in the JSON body. When set:
- If `port` or `enabled` changed: stops the running tracker and starts a new one with updated config
- Returns updated `status` object and `applied: true` in response
- Live-updatable settings (`announce_interval`, `peer_expiry`) are always applied to the running tracker instance without restart, regardless of the `apply` flag

There is **no separate restart endpoint**. The restart logic is integrated into the PUT with the `apply` flag.

**BitTorrentTracker runtime updates:**
- `tracker.announce_interval` - Instance attribute on `BitTorrentTracker`, also must update `TrackerRequestHandler.announce_interval` (class variable) for the HTTP handler to use the new value
- `tracker.state.peer_expiry` - Instance attribute on `TrackerState`
- `HTTPServer.shutdown()` only works with `serve_forever()`, NOT manual `handle_request()` loops (causes deadlock). The tracker uses `serve_forever()` in its `_serve()` thread.
- `server_close()` must be called after `shutdown()` to release the socket and prevent "Address already in use" errors on restart

When adding new API endpoints, include YAML docstrings in the function docstring for automatic Swagger documentation:
```python
@api_bp.route("/example", methods=["POST"])
def example_endpoint():
    """Short description of endpoint.
    ---
    tags:
      - Category
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            field_name:
              type: string
    responses:
      200:
        description: Success response
      400:
        description: Bad request
    """
```

## Development Commands

```bash
# Run locally (venv-dev is the development environment)
source venv-dev/bin/activate
python -m transferarr.main --config config.json --state-dir ./data

# Dependencies
pip install -r requirements.txt
```

## Git Workflow

- **`main`** is the protected default branch
- All changes must go through Pull Requests to `main`
- CI tests must pass before merging (required status check: `test`)
- No force pushes or deletions allowed on `main`
- **Docs-only changes** (`*.md`, `docs/**`) skip CI tests

### Creating a Feature Branch

```bash
# Always start from an up-to-date main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/my-feature

# ... make changes ...

# Push and create PR
git push -u origin feature/my-feature
gh pr create --base main --fill
```

### Branch Naming Conventions

- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates
- `refactor/*` - Code refactoring
- `test/*` - Test additions/changes

## Versioning

- Version stored in `VERSION` file at repo root
- Use `bump2version patch/minor/major` to release (auto-commits and tags)
- `./build.sh` builds dev image (`:dev` tag)
- `./build.sh --release` builds versioned image (requires clean git state and version tag)
- Version accessible via `transferarr.__version__` and `/api/v1/health`

## CI/CD

**📖 Full documentation: [docs/ci.md](../docs/ci.md)**

GitHub Actions workflow in `.github/workflows/tests.yml` runs the full test suite.

**Triggers**:
- Push to `main` branch
- Pull requests to `main`
- Manual dispatch (with test type selection)

**What it does**:
1. Builds `transferarr:dev` image
2. Starts full Docker Compose test infrastructure
3. Runs service-registrar to configure Radarr/Sonarr
4. Runs tests in parallel (matrix strategy)
5. Uploads test artifacts on failure (screenshots, logs)

**Manual trigger options** (workflow_dispatch):
- `all` - Run all test categories (default)
- `unit` - Unit tests only (no Docker)
- `integration-api` - API tests
- `integration-auth-user` - User authentication tests
- `integration-auth-api-key` - API key authentication tests
- `integration-lifecycle` - Torrent lifecycle tests
- `integration-persistence-sftp` - SFTP state persistence tests
- `integration-persistence-torrent-restart` - Torrent transfer restart recovery tests
- `integration-persistence-torrent-large` - Large file torrent restart tests
- `integration-persistence-manual-restart` - Manual transfer restart recovery tests
- `integration-transfers-torrent-infra` - Torrent infra and setup tests
- `integration-transfers-torrent-lifecycle` - Torrent download and lifecycle tests
- `integration-transfers-concurrent` - Concurrent and transfer type tests
- `integration-config` - Client routing tests
- `integration-edge` - Edge case/error tests
- `ui-fast` - Fast UI tests
- `ui-crud` - CRUD UI tests
- `ui-e2e` - End-to-end UI tests
- `ui-auth-pages` - Login/setup page UI tests
- `ui-auth-settings` - Auth settings UI tests

**Artifacts on failure**:
- `test-results/` - Screenshots, traces from Playwright
- `service-logs` - Docker Compose logs from all services

## Code Conventions

### Docker
- Use `docker compose` (v2) not `docker-compose` (v1, deprecated)
- Compose files should not include the deprecated `version` field
- **Image pinning**: All images in `docker-compose.test.yml` must use pinned versions via env var defaults (e.g., `${DELUGE_TAG:-2.1.1-r10-ls324}`). Never use `:latest` as a hardcoded tag in compose files. See "Image Version Pinning" section for details.

### Error Handling
- Custom exceptions in `exceptions.py` (note: typo `TrasnferClientException` is intentional/existing)
- Service layer exceptions in `web/services/__init__.py` map to HTTP responses:
  - `NotFoundError` → 404
  - `ConflictError` → 409
  - `ValidationError` → 400
  - `ConfigSaveError` → 500
- Download clients use `handle_exception` parameter to control error propagation vs logging

### Utility Functions
- `utils.decode_bytes()` - Recursively decode bytes from Deluge RPC responses
- `utils.get_paths_to_copy()` - Extract unique top-level paths from torrent file list
- `utils.generate_transfer_id()` - Generate random 6-char alphanumeric transfer ID
- `utils.build_transfer_torrent_name(name, id)` - Build `[TR-xxxxxx] Original Name` format
- `utils.parse_magnet_uri(uri)` - Parse magnet URI into `{hash, name, trackers}` dict
- `utils.build_magnet_uri(hash, name, trackers)` - Build magnet URI from components

### Client Connection Pattern
```python
# Always use ensure_connected() before operations
with self._lock:
    if not self.ensure_connected():
        raise ConnectionError(...)
    # perform operation
```

## Torrent State Machine

Torrents progress through states defined in `models/torrent.py`. The `TorrentManager.update_torrents()` method drives transitions.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TORRENT LIFECYCLE                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │  MANAGER_QUEUED  │  ← Radarr/Sonarr adds torrent to queue
    └────────┬─────────┘
             │ TorrentManager finds torrent on a download client
             ▼
    ┌──────────────────┐
    │    HOME_* states │  ← Torrent downloading/seeding on source client
    │  (DOWNLOADING,   │    States mirror Deluge status
    │   SEEDING, etc.) │
    └────────┬─────────┘
             │ HOME_SEEDING + has target connection
             │
             ├─── SFTP/Local transfer ──────────┐
             │                                   │
             │     ┌──────────────────┐          │
             │     │     COPYING      │          │
             │     └────────┬─────────┘          │
             │              │                    │
             │     ┌────────▼─────────┐          │
             │     │      COPIED      │          │
             │     └────────┬─────────┘          │
             │              │                    │
             ├─── Torrent transfer ─────────┐    │
             │                               │    │
             │  ┌─────────────────────────┐  │    │
             │  │  TORRENT_CREATING       │  │    │
             │  │  TORRENT_TARGET_ADDING  │  │    │
             │  │  TORRENT_DOWNLOADING    │  │    │
             │  │  TORRENT_SEEDING        │  │    │
             │  │  → COPIED               │  │    │
             │  └────────────┬────────────┘  │    │
             │               │               │    │
             ▼───────────────▼───────────────▼────▼
    ┌──────────────────┐
    │  TARGET_* states │  ← Torrent checking/seeding on destination
    │  (CHECKING,      │
    │   SEEDING, etc.) │
    └────────┬─────────┘
             │ TARGET_SEEDING: cleanup transfer torrent (if torrent transfer)
             │ TARGET_SEEDING + media manager confirms grab
             ▼
    ┌──────────────────┐
    │    [REMOVED]     │  ← Removed from home client & tracking list
    └──────────────────┘

    Error States:
    ─────────────
    UNCLAIMED  → Torrent not found on any client (retries 10x then removed)
    ERROR      → Transfer or client operation failed (SFTP)
    MISSING    → Torrent disappeared unexpectedly
    
    Torrent Transfer Errors:
    ────────────────────────
    Max retries → _cleanup_failed_transfer (remove from clients + tracker)
               → Reset to HOME_SEEDING for future retry
```

**Key transition logic** (in `torrent_service.py`):
- `MANAGER_QUEUED` → `HOME_*`: When torrent found on a download client via `client.has_torrent()`
- `HOME_SEEDING` → `TARGET_*`: Shortcut when torrent already exists on target (skips transfer entirely)
- `HOME_SEEDING` → `COPYING`: When SFTP/local connection, `connection.enqueue_copy_torrent()` is called
- `HOME_SEEDING` → `TORRENT_CREATING`: When torrent connection, handler begins transfer torrent creation
- `TORRENT_CREATING` → `TORRENT_TARGET_ADDING` → `TORRENT_DOWNLOADING` → `TORRENT_SEEDING` → `COPIED`: Torrent transfer states
- `TORRENT_*` → `ERROR`: If no transfer handler available or no connection found for torrent
- `COPYING` → `COPIED`: Set by `TransferConnection._do_copy_torrent()` on success
- `COPIED` → `TARGET_*`: When target client reports torrent status
- `TARGET_SEEDING` → cleanup transfer torrent (if present) → removed: When `media_manager.torrent_ready_to_remove()` returns True

## Adding New Download Clients

To add a new download client type (e.g., qBittorrent, Transmission):

1. **Create client class** in `clients/` extending `DownloadClientBase` and registering via decorator:
   ```python
   from transferarr.clients.registry import ClientRegistry
   from transferarr.clients.download_client import DownloadClientBase
   from transferarr.clients.config import ClientConfig

   @ClientRegistry.register("newclient")
   class NewClient(DownloadClientBase):
       def __init__(self, config: ClientConfig): ...
       def ensure_connected(self) -> bool: ...
       def has_torrent(self, torrent) -> bool: ...
       def get_torrent_info(self, torrent) -> dict: ...
       def get_torrent_state(self, torrent) -> TorrentState: ...
       def add_torrent_file(self, path, data, options): ...
       def remove_torrent(self, torrent_id, remove_data=False): ...
       def get_all_torrents(self) -> dict: ...
       def test_connection(self) -> tuple: ...
   ```

2. **Import the module** in `clients/__init__.py` so the `@register` decorator runs at import time

3. **Map client states** to `TorrentState` enum (HOME_* for source, TARGET_* for destination)

## Feature Tracking

Features and bugs are tracked via **GitHub Issues** with milestones for version planning.

- **Issues:** https://github.com/DiskTrackTed/transferarr/issues
- **Milestones:** https://github.com/DiskTrackTed/transferarr/milestones

### GitHub CLI
The `gh` CLI is available for interacting with issues:
```bash
# List open issues
gh issue list

# Create an issue
gh issue create --title "Feature: X" --label "feature" --milestone "v0.X.0"

# View issue details
gh issue view 1

# Close an issue
gh issue close 1
```

## Important Files
- `README.md` - Project documentation (quick start, configuration, architecture)
- `config.json` - Runtime configuration (gitignored, use `config copy.json` as template)
- `state.json` - Persistent torrent state (stored in state directory)
- `history.db` - SQLite database for transfer history (stored in state directory)
- `build.sh` - Docker image build script
- `run_tests.sh` - Docker-based test runner script
- `testing.ipynb` - Development/debugging notebook
- `docs/ci.md` - CI/CD documentation (workflows, image pinning, weekly latest tests)
- `docs/integration-tests.md` - Integration test documentation (test coverage, test names, patterns)
- `docs/ui-tests.md` - UI test documentation (Playwright, page objects, fixtures)

## Testing Infrastructure

### Docker Test Environment
The `docker/` directory contains a complete test environment:

```bash
# Start test infrastructure (all services)
docker compose -f docker/docker-compose.test.yml up -d

# Check service status
docker compose -f docker/docker-compose.test.yml ps

# Tear down and reset
docker compose -f docker/docker-compose.test.yml down -v
```

### Image Version Pinning
All Docker images in `docker-compose.test.yml` are pinned to specific versions for deterministic CI. Images use env var substitution with pinned defaults so the weekly `:latest` workflow can override them.

**Pinned images** (env var → default tag):
| Env Var | Default Tag | Image |
|---------|-------------|-------|
| `DELUGE_TAG` | `2.1.1-r10-ls324` | `lscr.io/linuxserver/deluge` |
| `RADARR_TAG` | `6.0.4.10291-ls294` | `lscr.io/linuxserver/radarr` |
| `SONARR_TAG` | `4.0.16.2944-ls303` | `lscr.io/linuxserver/sonarr` |
| `OPENSSH_TAG` | `10.2_p1-r0-ls218` | `lscr.io/linuxserver/openssh-server` |
| `ALPINE_TAG` | `3.21` | `alpine` |

- **opentracker**: Only `latest` and `pre-update` tags exist; no versioned tags available
- **Locally-built images** (mock-indexer, test-runner, registrar, torrent-creator): Python base images pinned to `bookworm` Debian release in their Dockerfiles
- **Deluge is pinned to 2.1.1** because 2.2.0 has a `create_torrent` bug

**Updating pinned versions**: When updating a pin, use the full linuxserver tag format: `{app_version}-ls{build_number}` (e.g., `2.1.1-r10-ls324`). Find available tags at `https://hub.docker.com/r/linuxserver/{image}/tags`.

**Weekly `:latest` workflow** (`.github/workflows/weekly-latest.yml`): Runs every Sunday at 06:00 UTC against `:latest` images. Tests a slim subset (unit, integration-api, integration-lifecycle, ui-fast). On failure, creates a GitHub issue with `ci-compatibility` label. Can also be triggered manually via `workflow_dispatch`.

### Test Services (Host Ports)
| Service | Host Port | Internal Port | Purpose |
|---------|-----------|---------------|---------|
| Tracker | 6969 | 6969 | OpenTracker for torrent seeding |
| SFTP | 2222 | 2222 | File transfer between Deluge instances |
| Deluge Source | 18112 (Web), 18846 (RPC) | 8112, 58846 | Source download client |
| Deluge Target | 18113 (Web), 18847 (RPC) | 8112, 58846 | Target download client |
| Deluge Target 2 | 18114 (Web), 18848 (RPC) | 8112, 58846 | Second target client |
| Radarr | 17878 | 7878 | Movie manager |
| Sonarr | 18989 | 8989 | TV show manager |
| Mock Indexer | 9696 | 9696 | Fake Torznab indexer for testing |
| Transferarr | 10445 | 10444 | Application under test |

### Test Credentials
- **Deluge Web UI**: password `testpassword`
- **Deluge RPC**: users `localclient` and `transferarr`, password `testpassword`
- **SFTP**: username `testuser`, password `testpass`

### Creating Test Torrents
```bash
# Create a movie torrent (10MB) - requires --profile tools
docker compose -f docker/docker-compose.test.yml --profile tools run --rm torrent-creator \
  --name "Test.Movie.2024.1080p.WEB-DL" --size 10

# Create a TV episode torrent (10MB)
docker compose -f docker/docker-compose.test.yml --profile tools run --rm torrent-creator \
  --name "Test.Series.S01E01.1080p.WEB-DL" --size 10

# List available torrents
curl http://localhost:9696/torrents
```

### Key Test Files
- `docker/docker-compose.test.yml` - Main compose file for test environment
- `docker/scripts/cleanup.sh` - Reset test environment (torrents, state, indexer)
- `docker/scripts/register-services.py` - Auto-registers download clients with Radarr/Sonarr
- `docker/scripts/create-test-torrent.py` - Test torrent generation script
- `scripts/generate_movie_catalog.py` - Wikidata SPARQL script to expand movie catalog
- `docker/services/mock-indexer/app.py` - Torznab API implementation
- `docker/services/deluge/auth` - Shared RPC authentication file (same credentials for all Deluge instances)
- `docker/services/deluge/web.conf` - Web UI password configuration
- `docker/services/deluge/configure-deluge.sh` - Init script to enable RPC remote connections and pin BitTorrent listen port
- `docker/fixtures/config.local.json` - Config for running transferarr locally against Docker services
- `docker/fixtures/config.torrent-transfer.json` - Config for torrent-based transfer tests (uses tracker, no SFTP)
- `docker/fixtures/config.sftp-to-sftp-no-tracker.json` - SFTP config with tracker explicitly disabled (for testing no-handler error paths)
- `docker/fixtures/config.torrent-transfer-no-tracker.json` - Torrent-type connection config with tracker disabled (for testing tracker validation error paths)

### Running Transferarr with Test Environment
```bash
# Start all services (includes transferarr)
docker compose -f docker/docker-compose.test.yml up -d

# To run transferarr locally instead, stop the container and run locally
docker stop test-transferarr
./docker/fixtures/update-local-config.sh  # Updates API keys in config.local.json
source venv-dev/bin/activate
python -m transferarr.main --config docker/fixtures/config.local.json --state-dir ./docker/state
```

### Torznab API Notes
The mock-indexer implements a minimal Torznab API. Key requirements for Radarr/Sonarr compatibility:
- **RFC 2822 Date Format**: `pubDate` must have correct day-of-week (e.g., "Mon, 08 Dec 2025"). 
  Radarr's `DateTime.Parse` with `DateTimeFormatInfo.InvariantInfo` validates the day-of-week matches the actual date.
- **Categories**: Movie categories start at 2000 (2040=HD), TV categories start at 5000 (5030=SD)
- **Capabilities XML**: Must include `<search>`, `<movie-search>`, `<tv-search>` with `supportedParams="q"`

### Service Startup Flow
The test environment uses Docker Compose profiles and dependencies:

1. **Base services** start first: tracker, sftp-server, deluge-source, deluge-target
2. **fix-permissions** runs to create `/downloads/movies` and `/downloads/tv` directories with correct ownership
3. **Media managers** (radarr, sonarr) start after base services are healthy
4. **service-registrar** runs after media managers, registering:
   - Root folders (`/downloads/movies`, `/downloads/tv`)
   - Download client (source-deluge)
   - Mock indexer (if torrents exist)
   - Generates `config.json` for transferarr
5. **transferarr** starts after registration completes

### Running Integration Tests (Phase 5)

Integration tests are in `tests/integration/` organized by category and use pytest. Use the `run_tests.sh` script for easy execution:

```bash
# Prerequisites: Start test services
docker compose -f docker/docker-compose.test.yml up -d

# Run all integration tests (includes cleanup)
./run_tests.sh tests/integration/

# Run specific category
./run_tests.sh tests/integration/lifecycle/ -v
./run_tests.sh tests/integration/api/ -v
./run_tests.sh tests/integration/transfers/ -v

# Run without automatic cleanup
./run_tests.sh --no-cleanup

# Run specific test file
./run_tests.sh tests/integration/lifecycle/test_torrent_lifecycle.py -v -s

# Run with pytest filters
./run_tests.sh -k "lifecycle" -v

# Run movie catalog validation (slow, excluded by default)
./run_tests.sh tests/catalog_tests/test_movie_catalog.py -v -s -m ""
```

#### Manual Docker Commands (Alternative)

```bash
# Run all integration tests via Docker
# (test code is mounted, dependencies are cached - no rebuild needed!)
docker compose -f docker/docker-compose.test.yml --profile test run --rm test-runner

# Run specific category
docker compose -f docker/docker-compose.test.yml --profile test run --rm test-runner \
  tests/integration/lifecycle/ -v -s

# Run with custom pytest args
docker compose -f docker/docker-compose.test.yml --profile test run --rm test-runner \
  tests/integration/ -v -s
```

**Note**: The test runner mounts source code and caches pip dependencies. You only need to rebuild if you modify the Dockerfile itself or system dependencies.

**Integration Test Directory Structure**:
```
tests/integration/
    api/                    # API and CRUD tests (~5 min)
    auth/                   # Authentication tests
        user/               # User auth tests (~20 min)
        api-key/            # API key auth tests (~10 min)
    lifecycle/              # Torrent lifecycle tests (~15 min)
    persistence/            # State persistence tests (~8 min)
    transfers/              # Transfer type variations (~12 min)
    config/                 # Client routing tests (~10 min)
    edge/                   # Error handling, edge cases (~8 min)
```

**Test Files**:
- `tests/conftest.py` - Fixtures for Docker, API clients, cleanup
- `tests/utils.py` - Helper functions (wait_for_*, clear_*, movie_catalog)
- `tests/integration/helpers.py` - Unified `LifecycleRunner` and `MediaManagerAdapter`
- `tests/integration/{category}/*.py` - Integration test files (see `docs/integration-tests.md` for complete test names and descriptions)
- `tests/ui/` - UI tests using Playwright (see UI Testing section below)
- `tests/catalog_tests/test_movie_catalog.py` - Validation test for all movies in the catalog (marked slow, excluded by default)
- `tests/catalog_tests/test_show_catalog.py` - Validation test for all shows in the catalog (marked slow, excluded by default)
- `docker/services/test-runner/Dockerfile` - Docker image for test execution (includes Chromium dependencies)
- `pytest.ini` - Pytest configuration with warning filters and slow test exclusion

**Key Fixtures** (in `tests/conftest.py`):

The conftest uses internal helper functions (prefixed with `_`) to reduce duplication:
- `_extract_api_key()` - Generic API key extraction from *arr config.xml
- `_register_mock_indexer()` - Generic mock indexer registration for Radarr/Sonarr

*Session-scoped fixtures*:
- `docker_services` - Ensures all containers are healthy
- `radarr_client` - REST API client for Radarr
- `sonarr_client` - REST API client for Sonarr
- `radarr_api_key` / `sonarr_api_key` - API keys extracted from config.xml
- `ensure_indexer_registered` / `ensure_sonarr_indexer_registered` - Registers mock indexer

*Function-scoped fixtures*:
- `deluge_source`, `deluge_target` - RPC clients for Deluge instances
- `deluge_target_2` - RPC client for second target Deluge (skip if not running)
- `create_torrent` - Factory to create test torrents via torrent-creator container (supports `size_mb` and `multi_file` params)
- `transferarr` - Manager to start/stop/restart transferarr container (supports `config_type` and `history_config` params). Config types: `sftp-to-local`, `local-to-sftp`, `sftp-to-sftp`, `sftp-to-sftp-no-tracker`, `local-to-local`, `multi-target`, `torrent-transfer`, `torrent-transfer-no-tracker`. Defaults to `sftp-to-sftp`.
- `clean_test_environment` - Standard setup/teardown fixture for all integration tests
- `lifecycle_runner` - Unified runner for standardized migration tests (Radarr/Sonarr)

**Key Test Utilities** (in `tests/utils.py`):

The test utilities use internal helper functions (prefixed with `_`) to reduce duplication. Public functions are thin wrappers around these helpers.

*Queue Utilities* (use generic `_wait_for_queue_item_by_hash()` and `_find_queue_item_by_name()` internally):
- `wait_for_queue_item_by_hash()` - Wait for torrent in Radarr queue by hash (preferred). Has `check_for_errors=True` param that raises `QueueItemError` on download failures.
- `wait_for_sonarr_queue_item_by_hash()` - Wait for torrent in Sonarr queue by hash. Same error detection as Radarr version.
- `find_queue_item_by_name()` / `find_sonarr_queue_item_by_name()` - Find queue item by name substring
- `remove_from_queue_by_name()` / `remove_from_sonarr_queue_by_name()` - Find and remove queue item by name
- `check_queue_item_for_errors()` - Check if queue item has error status (returns tuple of `(has_error, error_message)`)
- `QueueItemError` - Exception raised when queue item has error status (has `queue_item`, `status`, `tracked_status`, `error_message` attributes)

*Wait Utilities*:
- `wait_for_condition()` - Generic wait helper used by other wait functions
- `wait_for_torrent_in_deluge()` - Wait for torrent in Deluge with expected state
- `wait_for_torrent_removed()` - Wait for torrent to be removed from Deluge
- `wait_for_transferarr_state()` - Wait for torrent to reach state in transferarr

*Cleanup Utilities*:
- `clear_radarr_state()` - Clear all movies and queue items
- `clear_sonarr_state()` - Clear all series and queue items
- `clear_deluge_torrents()` - Remove all torrents from Deluge instance

*Catalogs & Naming*:
- `movie_catalog` - Singleton that provides unique test movies to avoid collisions
- `show_catalog` - Singleton that provides unique test shows to avoid collisions
- `sanitize_title_for_torrent()` - Sanitize titles for torrent names (removes colons, en dashes, etc.)
- `make_torrent_name()` - Create standard movie torrent name from title and year
- `make_episode_name()` - Create standard episode torrent name (Show.Title.S01E01...)

*Other*:
- `decode_bytes()` - Recursively decode bytes from Deluge RPC responses
- `corrupt_state_file()` - Corrupt transferarr's state.json for testing recovery
- `delete_state_file()` - Delete transferarr's state.json for testing recovery
- `force_torrent_state_in_file(transferarr, torrent_name, new_state)` - Force a torrent's state in state.json via Docker volume (in `tests/integration/edge/test_torrent_transfer_edge.py`). Uses temp alpine container to read/modify/write state.json with base64 encoding. Transferarr must be stopped when calling this.
- `STATE_VOLUME` - Docker volume name (`transferarr_test_transferarr-state`) for direct state.json access via temp containers

**Integration Test Pattern**:
Standardized migration tests should use the `lifecycle_runner` fixture to avoid boilerplate.

```python
class TestSomething:
    @pytest.fixture(autouse=True)
    def setup(self, clean_test_environment):
        """Use shared test environment setup."""
        pass
    
    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_radarr_migration(self, lifecycle_runner):
        # Runs the full 7-step migration for a movie
        lifecycle_runner.run_migration_test('radarr', item_type='movie')

    @pytest.mark.timeout(TIMEOUTS['torrent_transfer'])
    def test_sonarr_season_pack(self, lifecycle_runner):
        # Runs the full 7-step migration for a season pack
        lifecycle_runner.run_migration_test(
            'sonarr', 
            item_type='season-pack', 
            show_key='the_flash', 
            season_number=1
        )
```

**Manual Pattern** (for edge cases/error handling):
If the standard runner is too restrictive, use the manual pattern:
```python
    def test_manual_example(self, create_torrent, radarr_client, deluge_source, 
                            deluge_target, transferarr, docker_services):
        # 1. Get unique movie from catalog
        movie = movie_catalog.get_movie()
        torrent_name = make_torrent_name(movie['title'], movie['year'])
        
        # 2. Create torrent and add to Radarr
        torrent_info = create_torrent(torrent_name, size_mb=10)
        radarr_client.add_movie(title=movie['title'], tmdb_id=movie['tmdb_id'], ...)
        
        # 3. Wait for queue item BY HASH
        wait_for_queue_item_by_hash(radarr_client, torrent_info['hash'], ...)
        
        # 4. Start transferarr and wait for state transitions
        transferarr.start(wait_healthy=True)
        wait_for_transferarr_state(transferarr, torrent_name, 'TARGET_SEEDING')
```

**Warning Handling**:
- `pytest.ini` filters paramiko's TripleDES deprecation warning (library-level, can't fix)
- `decode_utf8=True` is set on all `DelugeRPCClient` instances to avoid deluge-client deprecation
- **Small test files**: Radarr/Sonarr show "Unable to determine if file is a sample" for files under ~50MB. This prevents auto-import but doesn't block the transfer flow.
- **Indexer registration**: Mock indexer registration fails if no torrents exist yet. Create torrents first, then re-run `service-registrar` or manually trigger a search after creating torrents.
- **Capabilities XML**: Must include `<search>`, `<movie-search>`, `<tv-search>` with `supportedParams="q"`

### Critical Testing Notes

**Always use hash-based queue matching**: Radarr/Sonarr's `downloadId` field contains the torrent hash (uppercase). Use `wait_for_queue_item_by_hash()` or `wait_for_sonarr_queue_item_by_hash()` instead of name-based matching because:
- Mock indexer may have pre-existing torrents with similar names but different hashes
- Name matching can fail when the media manager grabs a different torrent than the one created for the test

**Clean mock indexer between test runs**: The cleanup script (`./docker/scripts/cleanup.sh all`) clears mock indexer torrents to prevent hash collisions. Always run cleanup before tests.

**Use catalogs for unique items**: Use `movie_catalog` or `show_catalog` in `tests/utils.py` to avoid collisions and "already exists" errors in Radarr/Sonarr.

**Torrent Name Sanitization**: Always use `make_torrent_name()` or `make_episode_name()` to generate torrent names. Media managers are sensitive to:
- **Colons**: Must be removed (e.g., "Avengers: Endgame" -> "Avengers.Endgame")
- **En Dashes**: Must be replaced with spaces/dots
- **Years in Titles**: Avoid movies with years in their actual titles (e.g., "Blade Runner 2049") as the parser gets confused when combined with the release year.
- **Episode/Part Numbers**: Avoid movies with "Episode X" or "Part X" in their full titles (e.g., "Star Wars: Episode VII – The Force Awakens"). Radarr's clean title strips these, causing matching failures. Use shorter titles (e.g., "Star Wars: The Force Awakens").
- **Articles**: Radarr's parser removes articles like "and the" from titles when matching. If a movie title contains these, the torrent name may not match. Test with Radarr's `/api/v3/parse` endpoint.
- **Aliases**: For Sonarr, use the title returned by the API (`added_series['title']`) for torrent naming to handle aliases (e.g., "The Flash" vs "The Flash (2014)").

**Sonarr Specifics**:
- **Daily/Yearly Shows**: Some shows use years as seasons (e.g., "Washington Week" -> `S1967E01`). The mock indexer supports multi-digit seasons.
- **TVDB ID**: The mock indexer must return `tvdbid` in Torznab XML attributes for Sonarr to match correctly.
- **Sizing**: Sonarr has strict "Minimum/Maximum Size" constraints. The mock indexer uses dynamic sizing (150MB-500MB) to satisfy these.

**TIMEOUTS constant**: Standard timeouts are defined in `tests/conftest.py`:
```python
TIMEOUTS = {
    'service_startup': 120,      # 2 minutes for all services to be healthy
    'torrent_transfer': 300,     # 5 minutes for file transfer
    'state_transition': 120,     # 2 minutes for state machine transitions
    'api_response': 30,          # 30 seconds for API calls
    'torrent_seeding': 60,       # 1 minute for torrent to start seeding
}
```

**Torrent transfers complete fast on Docker network**: Small torrent transfers (10MB) between Docker containers complete almost instantly, making it impossible to reliably catch torrents in mid-transfer states (e.g., `TORRENT_DOWNLOADING`). Never write tests that depend on stopping transferarr while a torrent is in a transient `TORRENT_*` state. Instead, use `force_torrent_state_in_file()` to deterministically set the desired state in `state.json` while the container is stopped, then restart.

### UI Testing

**📖 Full documentation: [docs/ui-tests.md](../docs/ui-tests.md)**

UI tests use Playwright for browser automation and follow the Page Object Model pattern.

**Directory Structure**:
```
tests/ui/
    auth/                   # Authentication tests
        pages/              # Login/setup page tests (~25 min)
            test_login_page.py
            test_login_logout.py
            test_setup_page.py
        settings/           # Auth settings tab tests (~15 min)
            test_settings_auth.py
    fast/                   # UI-only tests (~5 min)
        test_navigation.py
        test_dashboard.py
        test_torrents.py
        test_settings.py
        test_settings_tracker.py
        test_history.py
    crud/                   # CRUD operations (~8 min)
        test_client_crud.py
        test_connection_crud.py
    e2e/                    # Real transfers (~15 min)
        test_e2e_workflows.py
        test_smoke.py
        test_torrent_transfer_ui.py
        test_transfer_types.py
    pages/                  # Page objects
    conftest.py
    helpers.py
```

**Running UI Tests**:
```bash
# Run all UI tests in Docker (headless, screenshots on failure)
./run_tests.sh tests/ui/ -v

# Run specific category
./run_tests.sh tests/ui/auth/pages/ -v
./run_tests.sh tests/ui/auth/settings/ -v
./run_tests.sh tests/ui/fast/ -v
./run_tests.sh tests/ui/crud/ -v
./run_tests.sh tests/ui/e2e/ -v

# Run specific test
./run_tests.sh tests/ui/fast/test_navigation.py -v -s
```

**Key Points**:
- Page objects in `tests/ui/pages/` (BasePage, DashboardPage, TorrentsPage, SettingsPage)
- Timeouts defined in `tests/ui/helpers.py` (`UI_TIMEOUTS` dict)
- Shared helpers in `tests/ui/helpers.py` (`add_connection_via_ui()`, `delete_connection_via_api()`, etc.)
- CRUD tests auto-cleanup created clients via API in fixture teardown
- Screenshots saved to `test-results/` on failure

**Playwright API Notes**:
- **No `wait_for_response()`**: Use `expect_response()` as a context manager instead:
  ```python
  # WRONG - will raise AttributeError
  response = page.wait_for_response(lambda r: "/api/torrents" in r.url)
  
  # CORRECT - use context manager
  with page.expect_response(lambda r: "/api/torrents" in r.url, timeout=5000) as response_info:
      pass  # Wait for the response
  assert response_info.value.status == 200
  ```
- **Assertions**: Use `expect()` from `playwright.sync_api` for auto-retry assertions
- **Regex in assertions**: Use `re.compile(r"pattern")` not JavaScript `/pattern/` syntax
- **Locators**: Prefer `page.locator()` over `page.query_selector()` for auto-waiting
- **Toggle switches**: Hidden checkbox inputs inside `.toggle-switch` wrappers — click the wrapper, not the input. See Frontend Settings Patterns above.
- **Number inputs**: Use `clear()` before `fill()` on pre-populated number fields. See Frontend Settings Patterns above.
- **Notification selectors**: Toast notifications have class `notification notification-{type}` (from notifications.js). Use `.notification-success`, `.notification-error`, etc. — not `.toast-success` or `.notification.success`.
- **Wait for API data**: Use `page.wait_for_load_state("networkidle")` after navigating to pages/tabs that load data from APIs before interacting with form fields.

**Docker Caching**:
- Pip packages cached in `test-runner-pip-cache` volume
- Playwright browsers cached in same volume (`/pip-cache/ms-playwright`)
- pytest cache stored in `test-results/.pytest_cache` (writable mount)
- Only reinstalls when `requirements.txt` hash changes or Playwright version changes