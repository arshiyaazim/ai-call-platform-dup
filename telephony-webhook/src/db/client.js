const fs = require("fs");
const path = require("path");
const { Pool } = require("pg");
const logger = require("../utils/logger");

const pool = new Pool({
  host: process.env.DB_HOST || "ai-postgres",
  port: parseInt(process.env.DB_PORT || "5432", 10),
  user: process.env.DB_USER || "postgres",
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || "postgres",
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

pool.on("error", (err) => {
  logger.error("Unexpected DB pool error", { error: err.message });
});

async function query(text, params) {
  const start = Date.now();
  try {
    const result = await pool.query(text, params);
    logger.debug("DB query", {
      query: text.substring(0, 80),
      duration_ms: Date.now() - start,
      rows: result.rowCount,
    });
    return result;
  } catch (err) {
    logger.error("DB query failed", {
      query: text.substring(0, 80),
      duration_ms: Date.now() - start,
      error: err.message,
    });
    throw err;
  }
}

async function migrate() {
  const schema = fs.readFileSync(
    path.join(__dirname, "schema.sql"),
    "utf-8"
  );
  await pool.query(schema);
  logger.info("DB migration completed");
}

module.exports = { pool, query, migrate };
