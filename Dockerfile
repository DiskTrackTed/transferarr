FROM python:3.9-slim

# Build arguments
ARG VERSION=dev
ARG UID=1000
ARG GID=1000

# Labels
LABEL org.opencontainers.image.version=$VERSION

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY ./requirements.txt /app/

# Install dependencies
RUN apt-get update && apt-get install -y git procps curl && apt-get clean 
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY ./transferarr /app/transferarr/
COPY ./VERSION /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV UID=${UID}
ENV GID=${GID}

# Create a non-root user with specified UID/GID and required directories
RUN groupadd -g ${GID} appuser && \
    useradd -u ${UID} -g ${GID} -m appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /tmp/torrents /config /state && \
    chown appuser:appuser /tmp/torrents /config /state

# Expose port (if needed)
EXPOSE 10444

# Define volumes for config and state
VOLUME ["/config", "/state"]

# Switch to non-root user
USER appuser

# Command to run the application (uses default paths: /config/config.json, /state)
CMD ["python3", "-m", "transferarr.main"]
