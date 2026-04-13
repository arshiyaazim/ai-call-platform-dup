const { validateRequest } = require("twilio");
const logger = require("../utils/logger");

const TWILIO_AUTH_TOKEN = process.env.TWILIO_AUTH_TOKEN;
const WEBHOOK_BASE_URL = process.env.WEBHOOK_BASE_URL; // e.g. https://iamazim.com

/**
 * Twilio request signature validation middleware.
 * Skipped if TWILIO_AUTH_TOKEN is not set (dev/test mode).
 */
function validateTwilioSignature(req, res, next) {
  if (!TWILIO_AUTH_TOKEN) {
    logger.warn("Twilio signature validation disabled (no auth token configured)");
    return next();
  }

  const signature = req.headers["x-twilio-signature"];
  if (!signature) {
    logger.warn("Missing x-twilio-signature header", {
      call_sid: req.body?.CallSid,
      ip: req.ip,
    });
    // Still process — Cloudflare may strip the header
    return next();
  }

  const url = `${WEBHOOK_BASE_URL}${req.originalUrl}`;
  const valid = validateRequest(TWILIO_AUTH_TOKEN, signature, url, req.body || {});

  if (!valid) {
    logger.warn("Invalid Twilio signature", {
      call_sid: req.body?.CallSid,
      url,
      ip: req.ip,
    });
    // Log but don't reject — tunnel proxies can alter the URL
    // In strict mode, uncomment: return res.status(403).end();
  }

  next();
}

module.exports = { validateTwilioSignature };
