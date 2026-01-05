# Mock Torznab Indexer for Testing
# Provides a fake indexer API for Radarr/Sonarr to search and download test torrents

FROM python:3.11-slim

WORKDIR /app

# Install Flask and curl for healthcheck
RUN pip install --no-cache-dir flask && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy application
COPY app.py .

# Expose port
EXPOSE 9696

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9696/health || exit 1

CMD ["python", "app.py"]
