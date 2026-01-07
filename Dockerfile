# Use official Python image
FROM python:3.9-slim

# Set working directory inside container
WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install dependencies first (for Docker layer caching)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Expose port 8000 (FastAPI default)
EXPOSE 8000

# Health check - ECS uses this to know if container is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI with Uvicorn
# - 0.0.0.0: Listen on all interfaces (required for Docker)
# - workers=4: Use 4 worker processes for better CPU utilization
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
