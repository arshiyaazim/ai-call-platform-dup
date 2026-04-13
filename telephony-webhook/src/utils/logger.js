const crypto = require("crypto");

const LOG_LEVEL = (process.env.LOG_LEVEL || "info").toLowerCase();
const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const threshold = LEVELS[LOG_LEVEL] ?? 1;

function emit(level, message, meta = {}) {
  if ((LEVELS[level] ?? 1) < threshold) return;
  const entry = {
    ts: new Date().toISOString(),
    level,
    msg: message,
    service: "telephony-webhook",
    ...meta,
  };
  const out = level === "error" ? process.stderr : process.stdout;
  out.write(JSON.stringify(entry) + "\n");
}

function requestId() {
  return crypto.randomUUID();
}

module.exports = {
  debug: (msg, meta) => emit("debug", msg, meta),
  info: (msg, meta) => emit("info", msg, meta),
  warn: (msg, meta) => emit("warn", msg, meta),
  error: (msg, meta) => emit("error", msg, meta),
  requestId,
};
