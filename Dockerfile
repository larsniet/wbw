# Use Python 3.9 as base image
FROM python:3.9-slim

# Install basic dependencies
RUN apt-get update && apt-get install -y \
    curl \
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

# Run the application
CMD ["python", "main.py"] 