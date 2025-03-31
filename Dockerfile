FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy application files
# COPY ./main.py /app/
COPY ./requirements.txt /app/
# COPY ./transferarr /app/transferarr/
# COPY ./templates /app/templates/

# Install dependencies
RUN apt-get update && apt-get install -y git && apt-get clean
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (if needed)
EXPOSE 10444

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["python", "main.py"]
