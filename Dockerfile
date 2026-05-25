# syntax=docker/dockerfile:1.7

# Multi-stage build: pin Python, install uv, sync deps, then a slim runtime image.
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install uv from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Cache deps separately from source for fast incremental rebuilds
COPY pyproject.toml ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev || uv sync --no-dev

# --- Runtime ---------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY data/ ./data/

EXPOSE 8000

# Lightweight healthcheck against the FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" || exit 1

# Default: FastAPI HTTP surface. MCP stdio is for local/dev use; see README.
CMD ["python", "-m", "mcp_clinical_doc_agent.api"]
