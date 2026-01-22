# Transferarr

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Automate torrent migration between download clients across servers.**

Transferarr monitors your Radarr/Sonarr queues and automatically transfers completed torrents from one torrent client to another. Perfect for homelab-to-seedbox workflows or load balancing across multiple servers.

---

## Features

- 🔄 **Automatic Migration** — Monitors media manager queues and transfers torrents when seeding completes
- 🌐 **Multi-Server Support** — Transfer between local storage, SFTP, or any combination
- 📊 **Web Dashboard** — Real-time status and manual controls
- � **Transfer History** — Track completed/failed transfers with stats, filtering, and retention policies
- �🔗 **Radarr & Sonarr Integration** — Seamless integration via API
- 🐳 **Docker Ready** — Simple deployment with Docker Compose
- 💾 **State Persistence** — Survives restarts without losing progress

---

## Version

Current version: See [VERSION](VERSION) file.

### Release Process

1. Bump version: `bump2version patch` (or `minor`/`major`)
2. Push with tags: `git push && git push --tags`
3. Build release: `./build.sh --release`

---

## Quick Start

### Docker (Recommended)

```bash
# Create config and state directories
mkdir -p config state

# Create config file (see Configuration section)
cp config.example.json config/config.json
# Edit config/config.json with your settings

# Run with Docker
docker run -d \
  --name transferarr \
  -p 10444:10444 \
  -v ./config:/config \
  -v ./state:/state \
  transferarr:latest
```

### Local Installation

```bash
# Clone and setup
git clone https://github.com/yourusername/transferarr.git
cd transferarr

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run (specify config file and state directory)
python -m transferarr.main --config ./config.json --state-dir ./data
```

Visit `http://localhost:10444` to access the web dashboard.

---

## Configuration

All configuration can be setup via the UI, but is saved as a json so can be manually edited.

See **[CONFIGURATION.md](CONFIGURATION.md)** for the complete configuration guide.

---

## How It Works

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Radarr/    │      │    Source    │      │ Destination  │
│   Sonarr     │─────▶│    Client    │─────▶│    Client    │
└──────────────┘      └──────────────┘      └──────────────┘
       │                     │                     │
       │ 1. Queue            │ 2. Download         │ 5. Verify
       │    torrent          │    & seed           │    & seed
       │                     │                     │
       │              ┌──────────────┐             │
       └─────────────▶│ Transferarr  │◀────────────┘
                      └──────────────┘
                             │
                        3. Monitor
                        4. Transfer files
                        6. Cleanup source
```

1. **Queue** — Radarr/Sonarr sends torrent to source download client
2. **Download & Seed** — Source client downloads and starts seeding
3. **Monitor** — Transferarr detects torrent is seeding
4. **Transfer** — Copies files and `.torrent` to destination via SFTP/local
5. **Verify & Seed** — Destination client verifies files and starts seeding
6. **Cleanup** — Transferarr removes torrent from source client

---

## Web API

Transferarr exposes a REST API at `/api/v1/` with interactive documentation available at:

**`http://localhost:10444/apidocs`**

The Swagger UI allows you to explore all endpoints, view request/response schemas, and test the API directly in your browser.

---

## Docker Compose

```yaml
services:
  transferarr:
    image: transferarr:latest
    container_name: transferarr
    ports:
      - "10444:10444"
    volumes:
      - ./config:/config
      - ./state:/state
      - ~/.ssh:/home/appuser/.ssh:ro  # For SFTP key authentication
    restart: unless-stopped
```

---

## Development

### Setup

```bash
# Create development environment
python -m venv venv-dev
source venv-dev/bin/activate
pip install -r requirements.txt

# Run locally
python -m transferarr.main --config config.json --state-dir ./data
```

### Testing

The project includes a complete Docker-based test environment:

```bash
# Start test infrastructure
docker compose -f docker/docker-compose.test.yml up -d

# Run integration tests
./run_tests.sh

# Run UI tests
./run_tests.sh tests/ui/ -v
```

See [tests/TESTING.md](tests/TESTING.md) for the complete testing guide.

---

## Project Structure

```
transferarr/
├── main.py                 # Entry point
├── config.py               # Configuration loading
├── clients/
│   ├── deluge.py           # Deluge RPC/Web client
│   ├── ftp.py              # SFTP client wrapper
│   └── transfer_client.py  # Transfer abstractions
├── models/
│   └── torrent.py          # Torrent model & state machine
├── services/
│   ├── torrent_service.py  # Central orchestrator
│   ├── transfer_connection.py  # File transfer handling
│   ├── history_service.py  # Transfer history (SQLite)
│   └── media_managers.py   # Radarr/Sonarr integration
└── web/
    └── routes/             # Flask API & UI routes
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/amazing-feature
   ```
3. Make your changes and commit (`git commit -m 'Add amazing feature'`)
4. Push to your branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request to `main`

### Branch Rules

- **`main`** is the protected default branch
- All changes must go through Pull Requests
- CI tests must pass before merging (skipped for docs-only changes)
- Branch naming: `feature/*`, `fix/*`, `docs/*`

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [Radarr](https://radarr.video/) and [Sonarr](https://sonarr.tv/) for the excellent media management
- [Deluge](https://deluge-torrent.org/) for the versatile torrent client
- [devopsarr](https://github.com/devopsarr) for the Python SDKs
