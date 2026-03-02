#!/bin/bash
# Configure Deluge for the test environment
# This script is run as a custom init script for the linuxserver deluge container
#
# It patches these settings in core.conf:
# 1. allow_remote: true         - enables RPC connections from other containers
# 2. listen_ports: [6881, 6881] - pins BitTorrent port for predictable networking
# 3. random_port: false       - disables random port (otherwise listen_ports is ignored)
#
# Uses Python for reliable config modification (Deluge's config format is a JSON
# header + JSON body, which sed can't handle reliably across all volume states).

python3 << 'PYEOF'
import json
import os
import sys

CONFIG_FILE = "/config/core.conf"
DELUGE_HEADER = '{\n    "file": 1,\n    "format": 1\n}'

REQUIRED_SETTINGS = {
    "allow_remote": True,
    "listen_ports": [6881, 6881],
    "random_port": False,
}

def log(msg):
    print(f"[configure-deluge] {msg}", flush=True)

def read_config():
    """Read Deluge config, returning (header, config_dict)."""
    with open(CONFIG_FILE, "r") as f:
        content = f.read()
    # Deluge format: {"file":1,"format":1}{"actual":"config",...}
    first_close = content.index("}")
    header = content[: first_close + 1]
    body = content[first_close + 1 :]
    return header, json.loads(body)

def write_config(header, config):
    """Write config in Deluge format."""
    with open(CONFIG_FILE, "w") as f:
        f.write(header + json.dumps(config, indent=4, sort_keys=True))

# --- Main ---

header = DELUGE_HEADER
config = {}

if os.path.exists(CONFIG_FILE):
    try:
        header, config = read_config()
        log("Loaded existing config")
    except Exception as e:
        log(f"Failed to parse existing config ({e}), will recreate")
        config = {}
else:
    log("No config file found (fresh volume), creating one")

# Check what needs changing
changes = []
for key, value in REQUIRED_SETTINGS.items():
    if config.get(key) != value:
        changes.append(key)

if not changes:
    log("Config already correct, no changes needed")
    sys.exit(0)

# Apply changes
for key in changes:
    config[key] = REQUIRED_SETTINGS[key]
    log(f"Setting {key} = {json.dumps(REQUIRED_SETTINGS[key])}")

write_config(header, config)

# Verify
try:
    _, verify = read_config()
    for key, value in REQUIRED_SETTINGS.items():
        if verify.get(key) == value:
            log(f"✓ {key} verified")
        else:
            log(f"WARNING: {key} verification failed (got {verify.get(key)})")
except Exception as e:
    log(f"WARNING: Verification read failed ({e})")

log("Done")
PYEOF
