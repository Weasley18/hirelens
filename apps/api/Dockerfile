# API, worker and migration images from one build. Build from the repository root:
#   docker build -f apps/api/Dockerfile --target runtime -t hirelens-api .
#   docker build -f apps/api/Dockerfile --target migrate -t hirelens-migrate .
# The same runtime image runs the API (default) or the worker (`node dist/worker.js`).

FROM node:22-slim AS build
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
# Prisma's query engine links against OpenSSL.
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN npm ci --no-audit --no-fund
COPY packages/shared packages/shared
COPY apps/api apps/api
RUN npx prisma generate --schema apps/api/prisma/schema.prisma \
    && npm run build --workspace apps/api

# One-off release step: apply migrations, then exit.
FROM build AS migrate
CMD ["npx", "prisma", "migrate", "deploy", "--schema", "apps/api/prisma/schema.prisma"]

FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Chromium renders PDF reports (Puppeteer's own Chrome download has no Linux ARM build).
# Liberation and DejaVu give the report Helvetica/Arial-metric fonts and broad Unicode coverage.
RUN apt-get update && apt-get install -y --no-install-recommends openssl ca-certificates \
       chromium fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV CHROMIUM_PATH=/usr/bin/chromium
COPY package.json package-lock.json ./
COPY apps/api/package.json apps/api/
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
# Production dependencies for the API and the shared contract only (no web/test tooling).
RUN npm ci --omit=dev --no-audit --no-fund --workspace apps/api --workspace packages/shared \
    && npm cache clean --force
# The shared package ships TypeScript source; Node >=22.18 strips types natively. Its real path
# is outside node_modules (workspace symlink), which Node's type stripping requires.
COPY packages/shared packages/shared
COPY --from=build /app/node_modules/.prisma node_modules/.prisma
COPY --from=build /app/apps/api/dist apps/api/dist
COPY apps/api/prisma apps/api/prisma
WORKDIR /app/apps/api
USER node
EXPOSE 3000
CMD ["node", "dist/server.js"]
