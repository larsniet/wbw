# Use Python 3.9 as base image
FROM python:3.9-slim

# Install system dependencies including Chrome
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    unzip \
    xvfb \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create directory for SQLite database with proper permissions
RUN mkdir -p /app/data && \
    chown -R 1000:1000 /app/data && \
    chmod 777 /app/data

# Set database path environment variable
ENV SQLITE_DB_PATH=/app/data/sessions.db

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port for health check
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Create entrypoint script for virtual display
RUN echo '#!/bin/bash\n\
# Start virtual display\n\
Xvfb :99 -screen 0 1024x768x24 &\n\
# Wait a moment for Xvfb to start\n\
sleep 2\n\
# Run the application\n\
exec "$@"' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

# Run the application with virtual display
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"] 