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
      "password": "deluge-password"
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
| `transfer_config` | object | Transfer method configuration (see below) |
| `source_dot_torrent_path` | string | Path to `.torrent` files on source (Deluge state dir) |
| `source_torrent_download_path` | string | Download path on source client |
| `destination_dot_torrent_tmp_dir` | string | Temp directory for `.torrent` files on destination |
| `destination_torrent_download_path` | string | Download path on destination client |

### Transfer Config

The `transfer_config` object defines how files are transferred between source and destination:

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
- History database is stored alongside the state file (e.g., `history.db`)
- History API available at `/api/v1/transfers` (see Swagger docs)
- Active transfers (pending/transferring) cannot be deleted unless using `?force=true`

---

## Transfer Type Combinations

Transferarr supports four transfer type combinations:

| From | To | Use Case |
|------|----|----------|
| `local` | `sftp` | Homelab → Seedbox |
| `sftp` | `local` | Seedbox → Homelab |
| `sftp` | `sftp` | Between two remote servers |
| `local` | `local` | Same server, different clients |

---

## Docker Compose Example

```yaml
services:
  transferarr:
    image: transferarr:latest
    container_name: transferarr
    ports:
      - "10444:10444"
    volumes:
      - ./config.json:/app/config.json
      - ./state.json:/app/state.json
      - ~/.ssh:/home/appuser/.ssh:ro  # For SFTP key authentication
    restart: unless-stopped
```

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
