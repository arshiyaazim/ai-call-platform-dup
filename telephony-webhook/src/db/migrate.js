const db = require("./client");
const logger = require("../utils/logger");

async function main() {
  try {
    await db.migrate();
    logger.info("Migration successful");
    process.exit(0);
  } catch (err) {
    logger.error("Migration failed", { error: err.message });
    process.exit(1);
  }
}

main();
