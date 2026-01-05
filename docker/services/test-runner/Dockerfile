# Test runner for Transferarr integration tests
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    gnupg \
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
