FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/inmo24x7/api/pyproject.toml apps/inmo24x7/api/pyproject.toml

RUN uv sync --frozen --no-dev --all-packages --no-install-project

COPY packages/core packages/core
COPY apps/inmo24x7/api apps/inmo24x7/api

RUN uv sync --frozen --no-dev --all-packages

FROM python:3.12-slim

ARG APP_VERSION=0.1.0
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder /app/.venv .venv
COPY --from=builder /app/packages/core packages/core
COPY --from=builder /app/apps/inmo24x7/api apps/inmo24x7/api

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=$APP_VERSION \
    GIT_COMMIT=$GIT_COMMIT \
    BUILD_DATE=$BUILD_DATE

USER app

WORKDIR /app/apps/inmo24x7/api

EXPOSE 8001

CMD ["uvicorn", "inmo24x7_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
