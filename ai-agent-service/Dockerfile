FROM node:20-alpine

WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY package.json package-lock.json* ./
RUN npm install --omit=dev && npm cache clean --force

COPY *.js ./

USER appuser

EXPOSE 3200

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
  CMD wget -q -O /dev/null http://127.0.0.1:3200/health || exit 1

CMD ["node", "service.js"]
