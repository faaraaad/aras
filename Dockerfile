# ==============================================================================
# Multi-purpose Production Dockerfile for Accounting System (Django + Celery)
# ==============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group for security
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Install Python dependencies (leveraging Docker layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# Copy application source code (excluding files in .dockerignore such as front/)
COPY . /app/

# Set up required directories and permissions for appuser
RUN mkdir -p /app/staticfiles /app/media && \
    chmod +x /app/entrypoint.sh && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose Django WSGI HTTP port
EXPOSE 8000

# Health check to ensure service is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health/ || exit 1

# Define container entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command starts Gunicorn WSGI production server
# (Override CMD in docker-compose or docker run for Celery workers / beat)
CMD ["gunicorn", "accounting_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2"]
