# ── Build stage ───────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install

COPY . .
RUN npm run build

# ── Production stage ─────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3020
ENV PORT=3020
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
