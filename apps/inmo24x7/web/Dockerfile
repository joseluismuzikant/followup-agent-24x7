FROM node:22-alpine AS builder

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/ui/package.json packages/ui/package.json
COPY packages/api-client-inmo24x7/package.json packages/api-client-inmo24x7/package.json
COPY packages/observability/package.json packages/observability/package.json
COPY apps/inmo24x7/web/package.json apps/inmo24x7/web/package.json
COPY apps/inmo24x7/backoffice/package.json apps/inmo24x7/backoffice/package.json

RUN corepack pnpm install --frozen-lockfile

COPY packages/ui packages/ui
COPY packages/api-client-inmo24x7 packages/api-client-inmo24x7
COPY packages/observability packages/observability
COPY apps/inmo24x7/web apps/inmo24x7/web

ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || (echo "VITE_API_URL build argument is required." >&2; exit 1)
ENV VITE_API_URL=$VITE_API_URL

ARG VITE_AUTH_MODE=supabase
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
# Embedded Signup (public values; empty disables "Conectar WhatsApp").
ARG VITE_META_APP_ID
ARG VITE_META_EMBEDDED_SIGNUP_CONFIG_ID
ARG VITE_META_GRAPH_API_VERSION=v26.0
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_META_APP_ID=$VITE_META_APP_ID \
    VITE_META_EMBEDDED_SIGNUP_CONFIG_ID=$VITE_META_EMBEDDED_SIGNUP_CONFIG_ID \
    VITE_META_GRAPH_API_VERSION=$VITE_META_GRAPH_API_VERSION

# Errors to Sentry (empty DSN = off); the release is the commit, like the API's.
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT=production
ARG GIT_COMMIT=unknown
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_SENTRY_ENVIRONMENT=$VITE_SENTRY_ENVIRONMENT \
    VITE_RELEASE=$GIT_COMMIT
# Source maps go to Sentry only with the sentry_auth_token build secret (CI); they are deleted
# after the upload and never reach the image. The secret is never stored in a layer.
ARG SENTRY_ORG
ARG SENTRY_PROJECT
RUN --mount=type=secret,id=sentry_auth_token,required=false \
    SENTRY_AUTH_TOKEN="$(cat /run/secrets/sentry_auth_token 2>/dev/null || true)" \
    SENTRY_ORG="$SENTRY_ORG" SENTRY_PROJECT="$SENTRY_PROJECT" \
    corepack pnpm --filter @inmo24x7/web build \
    && ! find apps/inmo24x7/web/dist -name '*.map' | grep -q .

FROM nginx:alpine

COPY apps/inmo24x7/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/inmo24x7/web/dist /usr/share/nginx/html

EXPOSE 80
