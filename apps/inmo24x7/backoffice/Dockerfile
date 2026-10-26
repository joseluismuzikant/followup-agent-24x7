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
COPY apps/inmo24x7/backoffice apps/inmo24x7/backoffice

ARG VITE_API_URL=http://localhost:8001
ENV VITE_API_URL=$VITE_API_URL

RUN corepack pnpm --filter @inmo24x7/backoffice build

FROM nginx:alpine

COPY apps/inmo24x7/backoffice/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/apps/inmo24x7/backoffice/dist /usr/share/nginx/html

EXPOSE 80
