# Dockerfile for Unified GA & Mirror Media CMS MCP Server
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project specification files
COPY pyproject.toml README.md ./
COPY analytics_mcp ./analytics_mcp

# Install Python dependencies and the analytics-mcp package
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . uvicorn starlette

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python3", "-m", "analytics_mcp.server"]
