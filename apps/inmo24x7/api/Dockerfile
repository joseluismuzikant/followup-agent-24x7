FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# The whole Python workspace: `uv sync --all-packages` needs every member, and the migrate
# service runs `alembic upgrade heads` (every product's migration branch) from this image.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/platform/pyproject.toml packages/platform/pyproject.toml
COPY apps/inmo24x7/api/pyproject.toml apps/inmo24x7/api/pyproject.toml
COPY apps/cuentas-claras/api/pyproject.toml apps/cuentas-claras/api/pyproject.toml

RUN uv sync --frozen --no-dev --all-packages --no-install-project

COPY alembic.ini alembic.ini
COPY migrations migrations
COPY packages/core packages/core
COPY packages/platform packages/platform
COPY apps/inmo24x7/api apps/inmo24x7/api
COPY apps/cuentas-claras/api apps/cuentas-claras/api

RUN uv sync --frozen --no-dev --all-packages

FROM python:3.12-slim

ARG APP_VERSION=0.1.0
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --from=builder /app/alembic.ini alembic.ini
COPY --from=builder /app/migrations migrations
COPY --from=builder /app/packages/core packages/core
COPY --from=builder /app/packages/platform packages/platform
COPY --from=builder /app/apps/inmo24x7/api apps/inmo24x7/api
COPY --from=builder /app/apps/cuentas-claras/api apps/cuentas-claras/api
# One-off admin commands: `docker compose run --rm api python scripts/make_admin.py <email>`.
COPY scripts/_cli.py scripts/make_admin.py scripts/recompute_llm_costs.py scripts/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=$APP_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    BUILD_DATE=$BUILD_DATE

USER app

EXPOSE 8001

CMD ["uvicorn", "inmo24x7_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
