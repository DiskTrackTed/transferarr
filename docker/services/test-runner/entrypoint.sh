#!/bin/bash
# Smart entrypoint that handles dependency caching
#
# Dependencies are cached in a volume. We only reinstall when:
# 1. The cache is empty (first run)
# 2. requirements.txt has changed since last install
#
# Playwright browsers are also cached and only reinstalled when:
# 1. The playwright version changes
# 2. Dependencies were updated (which might update playwright)

set -e

CACHE_DIR="/pip-cache"
SITE_PACKAGES="$CACHE_DIR/site-packages"
REQUIREMENTS_FILE="/app/requirements.txt"
HASH_FILE="$CACHE_DIR/requirements.hash"
PLAYWRIGHT_HASH_FILE="$CACHE_DIR/playwright.hash"
PLAYWRIGHT_BROWSERS="$CACHE_DIR/ms-playwright"

# Add cached packages to Python path
export PYTHONPATH="$SITE_PACKAGES:$PYTHONPATH"
export PATH="$SITE_PACKAGES/bin:$PATH"

# Store Playwright browsers in the cached volume (persists between container runs)
export PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS"

# Ensure cache directory exists
mkdir -p "$SITE_PACKAGES"

# Verify requirements file exists
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "❌ Error: $REQUIREMENTS_FILE not found"
    echo "   Make sure the app volume is mounted correctly"
    exit 1
fi

# Compute hash of current requirements
current_hash=$(md5sum "$REQUIREMENTS_FILE" 2>/dev/null | cut -d' ' -f1 || echo "none")

# Get cached hash (if exists)
cached_hash=""
if [ -f "$HASH_FILE" ]; then
    cached_hash=$(cat "$HASH_FILE")
fi

# Check if we need to install dependencies
deps_changed=false
if [ "$current_hash" != "$cached_hash" ]; then
    echo "📦 Requirements changed, installing dependencies..."
    if ! pip install --no-cache-dir --target="$SITE_PACKAGES" -r "$REQUIREMENTS_FILE" -q; then
        echo "❌ Error: Failed to install dependencies"
        exit 1
    fi
    
    # Save the new hash
    echo "$current_hash" > "$HASH_FILE"
    echo "✅ Dependencies updated"
    deps_changed=true
else
    echo "✅ Dependencies up to date (cached)"
fi

# Check if we need to install Playwright browsers
# Get playwright version from installed packages (use python -m since --target doesn't create bin scripts)
playwright_version=$(python -m playwright --version 2>/dev/null || echo "none")
cached_playwright_version=""
if [ -f "$PLAYWRIGHT_HASH_FILE" ]; then
    cached_playwright_version=$(cat "$PLAYWRIGHT_HASH_FILE")
fi

# Install browsers if playwright version changed or deps were updated
if [ "$playwright_version" != "$cached_playwright_version" ] || [ "$deps_changed" = true ]; then
    if [ "$playwright_version" != "none" ]; then
        echo "🎭 Installing Playwright browsers (version: $playwright_version)..."
        if ! python -m playwright install chromium; then
            echo "❌ Error: Failed to install Playwright browsers"
            echo "   This may be due to missing system dependencies."
            echo "   Ensure the Dockerfile installs all Chromium dependencies."
            exit 1
        fi
        echo "$playwright_version" > "$PLAYWRIGHT_HASH_FILE"
        echo "✅ Playwright browsers installed"
    else
        echo "ℹ️  Playwright not in requirements, skipping browser installation"
    fi
else
    echo "✅ Playwright browsers up to date (cached)"
fi

# Run pytest with any arguments passed to the container
echo ""
echo "🧪 Running tests..."
pytest "$@"
exit_code=$?

# Fix ownership of test-results so host user can access them
if [ -d "/app/test-results" ] && [ -n "$HOST_UID" ] && [ -n "$HOST_GID" ]; then
    chown -R "$HOST_UID:$HOST_GID" /app/test-results 2>/dev/null || true
fi

exit $exit_code
