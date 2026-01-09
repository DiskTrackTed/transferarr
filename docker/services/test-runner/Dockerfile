# Test runner for Transferarr integration and UI tests
#
# This image provides:
# - Python 3.12 with pytest
# - Docker CLI for container management in tests
# - Chromium dependencies for Playwright UI tests
#
# Dependencies (pip packages and Playwright browsers) are cached in a volume
# to speed up subsequent test runs. See entrypoint.sh for caching logic.

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies:
# - Docker CLI: for container management in integration tests
# - Playwright Chromium deps: for headless browser UI testing
#
# Chromium dependencies list from: playwright install-deps chromium --dry-run
# These are required for Chromium to run in headless mode
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    gnupg \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Copy entrypoint script (handles smart dependency caching)
COPY docker/services/test-runner/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Don't copy application code - it will be mounted at runtime
# Don't install dependencies here - entrypoint handles caching

# Set Python to unbuffered mode for real-time output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Smart entrypoint that checks/installs deps only when needed
ENTRYPOINT ["/entrypoint.sh"]
CMD ["tests/integration/", "-v", "--tb=short"]
