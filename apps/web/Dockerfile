# syntax=docker/dockerfile:1

# deps: install once, cached independently of application source so an
# app-only change never re-runs `npm ci`.
FROM node:22-alpine AS deps
WORKDIR /app
# openapi-typescript is NOT a dependency of this package.json — it runs only
# through an isolated `npx --package` invocation from the root Makefile's
# `types` target (see apply-progress.md's Unit 10 fix-pass section), so its
# `typescript: ^5.x` peer range never touches this toolchain. `npm ci` on the
# dependency set below needs no `legacy-peer-deps` flag; verified clean.
COPY package.json package-lock.json ./
RUN npm ci

# builder: `NEXT_PUBLIC_*` vars are inlined into the client bundle at build
# time (design.md D5), so they MUST be present as build args before `next
# build` runs, not only as runtime env vars.
FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_PHRASE_MAX_LENGTH=280
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_PHRASE_MAX_LENGTH=$NEXT_PUBLIC_PHRASE_MAX_LENGTH \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# runner: `output: "standalone"` (next.config.mjs) traces only the
# dependencies the server actually needs, so the runtime stage never installs
# the full node_modules tree.
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Non-root runtime user, matching the official Next.js standalone-output
# Dockerfile example — the container must not run `node server.js` as root.
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
