# Google Workspace ADK Multi-Agent System
# Production Dockerfile

# Stage 1: Python base
FROM python:3.11-slim as python-base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Node.js (for MCP servers)
FROM python-base as node-base

# Install Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN python --version && node --version && npm --version

# Stage 3: Application
FROM node-base

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install common MCP servers globally
RUN npm install -g \
    @modelcontextprotocol/server-gmail \
    @modelcontextprotocol/server-gdrive \
    @modelcontextprotocol/server-firecrawl

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/.cache

# Set permissions
RUN chmod +x /app/main.py

# Environment variables (defaults, override with --env-file or Cloud Run env vars)
ENV ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    SESSION_STORAGE=memory

# Health check (optional, useful for Cloud Run)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Expose port (if running web server in future)
EXPOSE 8080

# Run application
CMD ["python", "main.py"]
