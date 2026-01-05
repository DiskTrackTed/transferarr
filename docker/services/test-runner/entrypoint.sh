#!/bin/bash
# Smart entrypoint that handles dependency caching
#
# Dependencies are cached in a volume. We only reinstall when:
# 1. The cache is empty (first run)
# 2. requirements.txt has changed since last install

set -e

CACHE_DIR="/pip-cache"
SITE_PACKAGES="$CACHE_DIR/site-packages"
REQUIREMENTS_FILE="/app/requirements.txt"
HASH_FILE="$CACHE_DIR/requirements.hash"

# Add cached packages to Python path
export PYTHONPATH="$SITE_PACKAGES:$PYTHONPATH"
export PATH="$SITE_PACKAGES/bin:$PATH"

# Compute hash of current requirements
current_hash=$(md5sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || echo "none")

# Get cached hash (if exists)
cached_hash=""
if [ -f "$HASH_FILE" ]; then
    cached_hash=$(cat "$HASH_FILE")
fi

# Check if we need to install dependencies
if [ "$current_hash" != "$cached_hash" ]; then
    echo "📦 Requirements changed, installing dependencies..."
    pip install --no-cache-dir --target="$SITE_PACKAGES" -r "$REQUIREMENTS_FILE" -q
    
    # Save the new hash
    echo "$current_hash" > "$HASH_FILE"
    echo "✅ Dependencies updated"
else
    echo "✅ Dependencies up to date (cached)"
fi

# Run pytest with any arguments passed to the container
exec pytest "$@"
