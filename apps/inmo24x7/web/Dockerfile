FROM node:22-alpine AS builder

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/ui/package.json packages/ui/package.json
COPY packages/api-client-inmo24x7/package.json packages/api-client-inmo24x7/package.json
COPY apps/inmo24x7/web/package.json apps/inmo24x7/web/package.json
COPY apps/inmo24x7/backoffice/package.json apps/inmo24x7/backoffice/package.json

RUN corepack pnpm install --frozen-lockfile

COPY packages/ui packages/ui
COPY packages/api-client-inmo24x7 packages/api-client-inmo24x7
COPY apps/inmo24x7/web apps/inmo24x7/web

ARG VITE_API_URL
RUN test -n "$VITE_API_URL" || (echo "VITE_API_URL build argument is required." >&2; exit 1)
ENV VITE_API_URL=$VITE_API_URL

ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN corepack pnpm --filter @inmo24x7/web build

FROM nginx:alpine

COPY apps/inmo24x7/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/inmo24x7/web/dist /usr/share/nginx/html

EXPOSE 80
