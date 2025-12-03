FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy application files
# COPY ./main.py /app/
COPY ./requirements.txt /app/
# COPY ./transferarr /app/transferarr/
# COPY ./templates /app/templates/

# Install dependencies
RUN apt-get update && apt-get install -y git procps && apt-get clean 
RUN pip install --no-cache-dir -r requirements.txt

# Set build arguments for customizable UID/GID
ARG UID=1000
ARG GID=1000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV UID=${UID}
ENV GID=${GID}

# Create a non-root user with specified UID/GID
RUN groupadd -g ${GID} appuser && \
    useradd -u ${UID} -g ${GID} -m appuser && \
    chown -R appuser:appuser /app

# Expose port (if needed)
EXPOSE 10444

# Switch to non-root user
USER appuser

# Command to run the application
CMD ["python3", "-m", "transferarr.main"]
