FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY tsconfig.json ./
COPY src/ ./src/
COPY migrations/ ./migrations/
RUN npm run build

FROM node:20-alpine
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 opscore && \
    adduser --system --uid 1001 opscore
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/migrations ./migrations

USER opscore
EXPOSE 9850
CMD ["node", "dist/server.js"]
