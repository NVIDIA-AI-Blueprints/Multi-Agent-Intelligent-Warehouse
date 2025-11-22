# Multi-stage Dockerfile for Warehouse Operational Assistant
# This Dockerfile builds both frontend and backend with version injection

# =============================================================================
# Frontend Build Stage
# =============================================================================
FROM node:18-alpine AS frontend-builder

WORKDIR /app/src/ui/web

# Copy package files
COPY src/ui/web/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source
COPY src/ui/web/ ./

# Build arguments for version injection
ARG VERSION=0.0.0
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown

# Set environment variables for build
ENV REACT_APP_VERSION=$VERSION
ENV REACT_APP_GIT_SHA=$GIT_SHA
ENV REACT_APP_BUILD_TIME=$BUILD_TIME

# Build the frontend
RUN npm run build

# =============================================================================
# Backend Dependencies Stage
# =============================================================================
FROM python:3.11-slim AS backend-deps

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    g++ \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Final Runtime Stage
# =============================================================================
FROM python:3.11-slim AS final

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from backend-deps stage
COPY --from=backend-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-deps /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Build arguments for version injection
ARG VERSION=0.0.0
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown

# Set environment variables
ENV VERSION=$VERSION
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIME=$BUILD_TIME
ENV DOCKER_IMAGE=warehouse-assistant:$VERSION
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Copy frontend build from frontend-builder stage
COPY --from=frontend-builder /app/src/ui/web/build ./src/ui/web/build

# Create non-root user for security
RUN groupadd -r appuser && \
    useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

# Expose port
EXPOSE 8001

# Start command
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8001"]
