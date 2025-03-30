FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy application files
COPY ./main.py /app/
COPY ./requirements.txt /app/
COPY ./transferarr /app/transferarr/

# Install dependencies
RUN apt-get update && apt-get install -y git && apt-get clean
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (if needed)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["python", "main.py"]
