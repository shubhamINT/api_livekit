# Stage 1: Build stage
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
# We use --no-install-project to only install dependencies first (caching)
RUN uv sync --frozen --no-install-project --no-dev

# Stage 2: Final runtime stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PORT=8001

# Copy source code and other necessary files
COPY src /app/src
COPY assets /app/assets
COPY docs /app/docs
COPY mkdocs.yml /app/mkdocs.yml
COPY server_run.py /app/server_run.py
COPY sip_dispatcher_run.py /app/sip_dispatcher_run.py
COPY agent_run.py /app/agent_run.py

# Build MkDocs documentation
RUN mkdocs build -d site

# Download necessary files (models, etc.) during build
RUN python -m livekit.agents download-files && mkdir -p /app/logs

# Expose the API port
EXPOSE 8001

# Default command - can be overridden in docker-compose
CMD ["python", "server_run.py"]
