# Configuration Guide

Transferarr uses a JSON configuration file. Create `config.json` with the following structure:

## Basic Example

```json
{
  "media_managers": [
    {
      "type": "radarr",
      "host": "localhost",
      "port": 7878,
      "api_key": "your-radarr-api-key"
    },
    {
      "type": "sonarr",
      "host": "localhost",
      "port": 8989,
      "api_key": "your-sonarr-api-key"
    }
  ],
  "download_clients": {
    "homelab-deluge": {
      "type": "deluge",
      "connection_type": "rpc",
      "host": "192.168.1.50",
      "port": 58846,
      "username": "localclient",
      "password": "deluge-password"
    },
    "seedbox-deluge": {
      "type": "deluge",
      "connection_type": "web",
      "host": "seedbox.example.com",
      "port": 8112,
      "password": "deluge-password",
      "delete_cross_seeds": true
    }
  },
  "connections": {
    "homelab-to-seedbox": {
      "from": "homelab-deluge",
      "to": "seedbox-deluge",
      "transfer_config": {
        "from": {
          "type": "local"
        },
        "to": {
          "type": "sftp",
          "sftp": {
            "ssh_config_file": "~/.ssh/config",
            "ssh_config_host": "seedbox"
          }
        }
      },
      "source_dot_torrent_path": "/path/to/deluge/state/",
      "source_torrent_download_path": "/path/to/downloads/",
      "destination_dot_torrent_tmp_dir": "/home/user/tmp/",
      "destination_torrent_download_path": "/home/user/downloads/"
    }
  }
}
```

---

## Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--config` | `/config/config.json` | Path to configuration file |
| `--state-dir` | `/state` | Directory for `state.json` and `history.db` |

**Environment Variables** (override defaults if CLI args not provided):
- `CONFIG_FILE` - Path to configuration file
- `STATE_DIR` - Path to state directory

**Priority**: CLI argument > Environment variable > Default

**Example**:
```bash
# Docker (uses defaults)
docker run -v ./config:/config -v ./state:/state transferarr:latest

# Local development
python -m transferarr.main --config ./config.json --state-dir ./data
```

---

## Configuration Options

### Media Managers

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `radarr` or `sonarr` |
| `host` | string | ✓ | Hostname or IP address (can include port, e.g., `localhost:7878`) |
| `port` | number | | API port, only needed if not included in `host` |
| `api_key` | string | ✓ | API key from Settings → General |

### Download Clients

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | `deluge` (more clients planned) |
| `connection_type` | string | | `rpc` (daemon) or `web` (Web UI). Defaults to `rpc` |
| `host` | string | ✓ | Hostname or IP address |
| `port` | number | ✓ | RPC port (58846) or Web port (8112) |
| `username` | string | | Username (RPC only, optional) |
| `password` | string | ✓ | Password |
| `delete_cross_seeds` | boolean | | Remove cross-seed siblings from this client when a torrent is removed after transfer. Defaults to `true` |

### Connections

Connections are defined as an object where each key is a unique connection name:

```json
"connections": {
  "my-connection-name": {
    "from": "source-client",
    "to": "destination-client",
    ...
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| *(key)* | string | Unique connection name (e.g., `"homelab-to-seedbox"`) |
| `from` | string | Name of source download client |
| `to` | string | Name of destination download client |
| `transfer_config` | object | Transfer method configuration (see [Transfer Config](#transfer-config)) |

Additional path fields depend on the transfer method — see the Transfer Config section below.

### Transfer Config

The `transfer_config` object defines how files are transferred between source and destination. Two transfer methods are available:

#### File Transfer (SFTP/Local)

Copies files and `.torrent` to the destination via SFTP or local storage.

```json
{
  "from": {
    "type": "local"
  },
  "to": {
    "type": "sftp",
    "sftp": {
      "ssh_config_file": "~/.ssh/config",
      "ssh_config_host": "seedbox"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `from.type` | string | `local` or `sftp` |
| `to.type` | string | `local` or `sftp` |

**SFTP options** (nested under `sftp` key):

*Option 1: Use SSH config file (recommended)*

| Field | Type | Description |
|-------|------|-------------|
| `ssh_config_file` | string | Path to SSH config file (default: `~/.ssh/config`) |
| `ssh_config_host` | string | Host alias from SSH config |

*Option 2: Direct credentials*

| Field | Type | Description |
|-------|------|-------------|
| `host` | string | Hostname or IP address |
| `port` | number | SSH port (default: 22) |
| `username` | string | SSH username |
| `password` | string | SSH password (or use `private_key`) |
| `private_key` | string | Path to SSH private key |

**File transfer connections** use these additional connection fields:

| Field | Type | Description |
|-------|------|-------------|
| `source_dot_torrent_path` | string | Path to `.torrent` files on source (Deluge state dir) |
| `source_torrent_download_path` | string | Download path on source client |
| `destination_dot_torrent_tmp_dir` | string | Temp directory for `.torrent` files on destination |
| `destination_torrent_download_path` | string | Download path on destination client |

#### Torrent Transfer (BitTorrent P2P)

Transfers files via BitTorrent protocol using a built-in tracker. In magnet-only mode, **no filesystem access is required** — all operations happen through Deluge’s API. Optionally, configure source access (SFTP or local) to fetch `.torrent` files for private tracker support.

```json
{
  "type": "torrent",
  "destination_path": "/downloads"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Must be `"torrent"` |
| `destination_path` | string | Download path on destination client |
| `source` | object | Optional source config to fetch `.torrent` metadata (see below) |

**Source Access** (optional — for private tracker torrents):

By default, torrent transfers add the original torrent to the target via magnet link. This works for public trackers but **private tracker torrents require the `.torrent` file** (magnet links don’t carry the private flag/passkey). When `source` is configured, Transferarr fetches the `.torrent` file from the source’s Deluge state directory.

Two access modes are available:

**SFTP** — Fetch the `.torrent` file over SFTP from a remote source:

```json
{
  "type": "torrent",
  "destination_path": "/downloads",
  "source": {
    "type": "sftp",
    "sftp": {
      "host": "source-server",
      "port": 22,
      "username": "user",
      "password": "pass"
    },
    "state_dir": "/home/user/.config/deluge/state"
  }
}
```

**Local** — Read the `.torrent` file from a locally-mounted path (e.g., Docker volume, NFS mount):

```json
{
  "type": "torrent",
  "destination_path": "/downloads",
  "source": {
    "type": "local",
    "state_dir": "/mnt/deluge-state"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `source.type` | string | Access mode: `"sftp"` or `"local"` |
| `source.sftp` | object | SFTP connection details (required when `type` is `"sftp"`) |
| `source.sftp.host` | string | SFTP hostname or IP |
| `source.sftp.port` | number | SSH port (default: 22) |
| `source.sftp.username` | string | SSH username |
| `source.sftp.password` | string | SSH password (or use SSH key auth via `ssh_config_host`) |
| `source.state_dir` | string | Path to Deluge’s state directory containing `.torrent` files |

**Requirements:**
- Both source and destination must be Deluge clients
- The built-in tracker must be enabled (see [Tracker Configuration](#tracker-configuration))
- `tracker.external_url` must be set to a URL reachable by both clients

**How it works:**
1. Transferarr creates a transfer torrent from the source files
2. Registers the hash with the built-in tracker
3. Adds the torrent to the target via magnet link
4. Target downloads directly from source via BitTorrent P2P
5. Original torrent is added to target (instant hash check since files already exist)
6. Transfer torrents are cleaned up from both clients

---

## History Configuration

The `history` section controls transfer history tracking:

```json
{
  "history": {
    "enabled": true,
    "retention_days": 90,
    "track_progress": true
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable history tracking |
| `retention_days` | number | `90` | Days to retain records. Set to `null` to keep forever |
| `track_progress` | boolean | `true` | Update byte progress during transfers (disable to reduce DB writes) |

**Notes:**
- Retention policy is applied on application startup
- Only completed/failed/cancelled transfers are pruned
- History database (`history.db`) is stored in the state directory
- History API available at `/api/v1/transfers` (see Swagger docs)
- Active transfers (pending/transferring) cannot be deleted unless using `?force=true`

---

## Authentication Configuration

The `auth` section controls web UI authentication:

```json
{
  "auth": {
    "enabled": true,
    "username": "admin",
    "password_hash": "$2b$12$...",
    "session_timeout_minutes": 60
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `false` | Enable/disable authentication |
| `username` | string | `null` | Login username |
| `password_hash` | string | `null` | Bcrypt-hashed password (never store plain text) |
| `session_timeout_minutes` | number | `60` | Session duration before re-login required. Set to `0` for no timeout. **Changes require restart** |

**First-Run Behavior:**
- If no `auth` section exists, Transferarr shows a setup page on first access
- You can create credentials or skip setup (which sets `enabled: false`)
- Skipping allows full access without login

**Enabling Auth Later:**
1. Go to **Settings → Auth** tab
2. Toggle "Authentication" on
3. Set your session timeout preference
4. Click "Save Settings"

**Changing Password:**
1. Go to **Settings → Auth** tab
2. Fill in the "Change Password" form
3. Enter current password and new password
4. Click "Change Password"

**Session Storage:**
- Sessions are signed using a secret key stored in `<state_dir>/secret_key`
- The secret key is auto-generated on first run
- Deleting the secret key will invalidate all existing sessions

**Protected Routes:**
- When auth is enabled, all routes redirect to `/login` except:
  - `/login` and `/setup` pages
  - `/api/v1/health` endpoint (for monitoring)

### API Key Authentication

For programmatic access (scripts, integrations), you can use API key authentication instead of sessions.

**Configuration:**
```json
{
  "api": {
    "key": "tr_abc123...",
    "key_required": false
  }
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `key` | `null` | The API key (auto-generated via Settings) |
| `key_required` | `false` | Require API key for unauthenticated requests |

**Usage:**
```bash
# Via header (preferred)
curl -H "X-API-Key: tr_abc123..." http://localhost:10444/api/v1/torrents

# Via query parameter
curl "http://localhost:10444/api/v1/torrents?apikey=tr_abc123..."
```

**Managing Keys:**
1. Go to **Settings → Auth** tab
2. Scroll to the "API Key" section
3. Click "Generate API Key" to create a new key
4. Toggle "Require API Key" to enforce authentication
5. Use "Revoke Key" to invalidate the current key

**Important Notes:**
- Session-authenticated users bypass API key requirement
- Cannot enable "Require API Key" when user authentication is disabled
- The `/api/v1/health` endpoint is always accessible (no auth required)

---

## Tracker Configuration

The `tracker` section controls the built-in BitTorrent tracker used for torrent-based transfers:

```json
{
  "tracker": {
    "enabled": true,
    "port": 6969,
    "external_url": "http://transferarr:6969/announce",
    "internal_url": null,
    "announce_interval": 60,
    "peer_expiry": 120
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable/disable the tracker |
| `port` | number | `6969` | Port for the tracker to listen on |
| `external_url` | string | `null` | URL that download clients use to reach the tracker. **Required for torrent transfers** |
| `internal_url` | string | `null` | URL for clients on the same network as the tracker (e.g., Docker). When set, both URLs are included in transfer torrents so each client uses whichever responds |
| `announce_interval` | number | `60` | Seconds between peer re-announces |
| `peer_expiry` | number | `120` | Seconds before a peer is considered expired |

**Notes:**
- The tracker is enabled by default. Disable it if you only use SFTP/local transfers.
- `external_url` must be reachable by both source and target Deluge clients (e.g., `http://transferarr:6969/announce` in Docker networks).
- `internal_url` is useful when one client (e.g., homelab behind VPN) can't reach the external URL but can reach the tracker directly.
- Changing `port` or `enabled` requires a tracker restart (available via Settings → Tracker → "Save and Apply").
- `announce_interval`, `peer_expiry`, `external_url`, and `internal_url` can be changed live without restarting the tracker.
- Tracker state (registered hashes, peers) is in-memory only and is rebuilt from torrent state on restart.

---

## Transfer Type Combinations

Transferarr supports five transfer type combinations:

| Method | From | To | Use Case |
|--------|------|----|----------|
| File Transfer | `local` | `sftp` | Homelab → Seedbox |
| File Transfer | `sftp` | `local` | Seedbox → Homelab |
| File Transfer | `sftp` | `sftp` | Between two remote servers |
| File Transfer | `local` | `local` | Same server, different clients |
| Torrent | — | — | P2P between two Deluge instances (no filesystem access needed) |

---

## Manual Transfers & Cross-Seeds

### Manual Transfers

The Torrents page allows you to manually select seeding torrents and transfer them to a destination client. The page uses a per-client torrent table with state filtering, name search, sortable columns, and pagination. Select one or more torrents using the row checkboxes (or the inline transfer button), choose a destination, and click **Start Transfer**.

### Cross-Seeds

If you use a tool like [cross-seed](https://www.cross-seed.org/), your source client may have multiple torrents sharing the same data files via hardlinks. When manually transferring, Transferarr detects these cross-seed siblings (torrents with the same name and size) and offers an **Include Cross-Seeds** checkbox.

**This checkbox is unchecked by default**, and we recommend leaving it unchecked. Here's why:

1. **Hardlink safety**: On the source, cross-seeds share data through hardlinks — deleting one torrent's data doesn't affect others. Transferarr copies files independently to the target, so there are no hardlinks on the destination. If you later "Remove with data" on any one torrent, it deletes the shared files and breaks the others.

2. **Less bandwidth**: Only one copy needs to be transferred. Cross-seed can re-add the siblings on the target from the same data.

3. **Correct tracker metadata**: Cross-seed generates `.torrent` files with the correct passkeys, announce URLs, and piece hashes for each tracker. Transferring the original cross-seed torrents may carry source-specific metadata.

#### Recommended Workflow

1. **Transfer the original torrent** (leave "Include Cross-Seeds" unchecked)
2. **Run cross-seed on your target client** — it will scan the downloaded files and create matching torrents for your other trackers, with proper hardlinks
3. **Remove the original + cross-seeds from the source** once the target is seeding

This preserves hardlink safety on both source and target, uses minimal bandwidth, and ensures each tracker gets the correct torrent metadata.

> **Power users**: If you understand the hardlink implications and want to transfer cross-seeds anyway (e.g., for a quick migration where you'll fix hardlinks later), you can check the box. A warning will appear reminding you about the hardlink safety concern.

---

## Docker Compose Example

```yaml
services:
  transferarr:
    image: transferarr:latest
    container_name: transferarr
    ports:
      - "10444:10444"
      - "6969:6969"    # Tracker port (for torrent-based transfers)
    volumes:
      - ./state:/state            # Contains state.json and history.db
      - ~/.ssh:/home/appuser/.ssh:ro  # For SFTP key authentication
    restart: unless-stopped
```

### Volume Contents

| Volume | Contents | Description |
|--------|----------|-------------|
| `/config` | `config.json` | Application configuration |
| `/state` | `state.json`, `history.db` | Runtime state and transfer history |

---

## Getting API Keys

### Radarr
Settings → General → Security → API Key

### Sonarr
Settings → General → Security → API Key

### Deluge RPC
The RPC password is configured in Deluge's `auth` file, typically at:
- `~/.config/deluge/auth` (Linux)
- `/config/auth` (Docker)

Format: `username:password:level`

### Deluge Web UI
Set via Web UI: Preferences → Interface → Password
