#!/bin/bash
# docker/fixtures/update-local-config.sh
# Updates config.local.json with current API keys from running test containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.local.json"

echo "Extracting API keys from test containers..."

RADARR_KEY=$(docker exec test-radarr cat /config/config.xml 2>/dev/null | grep -oP '(?<=<ApiKey>)[^<]+')
SONARR_KEY=$(docker exec test-sonarr cat /config/config.xml 2>/dev/null | grep -oP '(?<=<ApiKey>)[^<]+')

if [ -z "$RADARR_KEY" ]; then
    echo "ERROR: Could not extract Radarr API key. Is test-radarr running?"
    exit 1
fi

if [ -z "$SONARR_KEY" ]; then
    echo "ERROR: Could not extract Sonarr API key. Is test-sonarr running?"
    exit 1
fi

echo "  Radarr: ${RADARR_KEY:0:8}..."
echo "  Sonarr: ${SONARR_KEY:0:8}..."

# Update the config file
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS sed
    sed -i '' "s/REPLACE_WITH_RADARR_KEY/$RADARR_KEY/g" "$CONFIG_FILE"
    sed -i '' "s/REPLACE_WITH_SONARR_KEY/$SONARR_KEY/g" "$CONFIG_FILE"
else
    # Linux sed
    sed -i "s/REPLACE_WITH_RADARR_KEY/$RADARR_KEY/g" "$CONFIG_FILE"
    sed -i "s/REPLACE_WITH_SONARR_KEY/$SONARR_KEY/g" "$CONFIG_FILE"
fi

# Also handle already-set keys (for re-running)
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/\"api_key\": \"[a-f0-9]\{32\}\"/\"api_key\": \"$RADARR_KEY\"/1" "$CONFIG_FILE"
else
    # Use python for more reliable JSON handling
    python3 << EOF
import json
with open("$CONFIG_FILE", "r") as f:
    config = json.load(f)

for mm in config.get("media_managers", []):
    if mm.get("type") == "radarr":
        mm["api_key"] = "$RADARR_KEY"
    elif mm.get("type") == "sonarr":
        mm["api_key"] = "$SONARR_KEY"

with open("$CONFIG_FILE", "w") as f:
    json.dump(config, f, indent=4)
EOF
fi

echo "✅ Updated $CONFIG_FILE with current API keys"
echo ""
echo "Run transferarr with:"
echo "  python -m transferarr.main --config docker/fixtures/config.local.json"
