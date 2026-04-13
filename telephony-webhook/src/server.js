const express = require("express");
const logger = require("./utils/logger");
const { migrate } = require("./db/client");
const webhookRouter = require("./routes/webhook");

const PORT = parseInt(process.env.PORT || "3100", 10);
const app = express();

// ─── Middleware ──────────────────────────────────────────────
// Twilio POSTs x-www-form-urlencoded
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

// Request logging
app.use((req, _res, next) => {
  if (req.path !== "/health" && req.path !== "/api/v1/telephony/health") {
    logger.info("HTTP request", {
      method: req.method,
      path: req.path,
      ip: req.ip,
      user_agent: req.headers["user-agent"],
    });
  }
  next();
});

// ─── Routes ─────────────────────────────────────────────────
app.use("/api/v1/telephony", webhookRouter);

// Root health
app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "telephony-webhook" });
});

// 404 fallback
app.use((_req, res) => {
  res.status(404).json({ error: "Not found" });
});

// Global error handler — never crash
app.use((err, _req, res, _next) => {
  logger.error("Unhandled error", { error: err.message, stack: err.stack });
  res.status(500).json({ error: "Internal server error" });
});

// ─── Start ──────────────────────────────────────────────────
async function start() {
  try {
    logger.info("Running DB migration...");
    await migrate();
    logger.info("DB migration complete");
  } catch (err) {
    logger.error("DB migration failed — starting anyway", { error: err.message });
  }

  app.listen(PORT, "0.0.0.0", () => {
    logger.info("Telephony webhook server started", { port: PORT });
  });
}

start();

// Graceful shutdown
process.on("SIGTERM", () => {
  logger.info("SIGTERM received, shutting down");
  process.exit(0);
});

process.on("uncaughtException", (err) => {
  logger.error("Uncaught exception", { error: err.message, stack: err.stack });
});

process.on("unhandledRejection", (reason) => {
  logger.error("Unhandled rejection", { error: String(reason) });
});
