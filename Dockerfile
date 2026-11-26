# The API image: also runs migrations (alembic) and the daily sweeps (python -m app.sweeps).
# Build from the repository root: docker build -t my-castings-api .

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
# Same path as the final stage: venv scripts hard-code their interpreter path.
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# Dependencies first, from the lockfile only, so code edits don't redo this layer.
# Every workspace member's pyproject.toml must be present for uv to read the lockfile.
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/pyproject.toml apps/api/
COPY packages/ingestion_core/pyproject.toml packages/ingestion_core/
COPY infra/pyproject.toml infra/
RUN uv sync --frozen --no-dev --package my-castings-api --no-install-workspace

COPY packages/ingestion_core packages/ingestion_core
COPY apps/api apps/api
RUN uv sync --frozen --no-dev --package my-castings-api --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Migrations run from here: `alembic upgrade head`.
COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
# --proxy-headers: the scheme (https) comes from the load balancer's X-Forwarded-Proto.
# The client IP for rate limiting comes from CloudFront-Viewer-Address instead (see
# client_ip_header in app/config.py), since X-Forwarded-For can carry forged entries.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
