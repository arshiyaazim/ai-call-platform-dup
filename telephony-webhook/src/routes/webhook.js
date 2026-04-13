const { Router } = require("express");
const db = require("../db/client");
const logger = require("../utils/logger");
const { startWorkflow } = require("../services/workflow");
const { validateTwilioSignature } = require("../middleware/security");

const router = Router();

const MAX_RETRIES = 3;
const LOCK_STALE_MS = 30_000; // 30s — consider lock stale after this
const PROCESSING_TIMEOUT_MS = 10_000; // 10s — workflow must finish within this

// ─── Metrics (in-memory counters) ───────────────────────────
const metrics = { total: 0, duplicates: 0, failed: 0, permanently_failed: 0 };

// ─── TwiML helpers ──────────────────────────────────────────
function twimlResponse(body) {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<Response>",
    `  ${body}`,
    "</Response>",
  ].join("\n");
}

const TWIML_CONNECTING = twimlResponse(
  '<Say voice="alice">Connecting your call. Please wait.</Say>'
);
const TWIML_HANGUP = twimlResponse("<Hangup/>");

function sendTwiml(res, xml, statusCode = 200) {
  res.status(statusCode).set("Content-Type", "text/xml").send(xml);
}

// ─── Atomic idempotent insert (race-safe) ───────────────────
async function atomicInsert(event) {
  const {
    call_sid, workflow_id, from_number, to_number,
    call_status, direction, payload, request_id,
  } = event;
  const result = await db.query(
    `INSERT INTO telephony_events
       (call_sid, workflow_id, from_number, to_number, call_status, direction, payload, request_id)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
     ON CONFLICT (call_sid) DO NOTHING
     RETURNING id`,
    [call_sid, workflow_id, from_number, to_number, call_status, direction, JSON.stringify(payload), request_id]
  );
  return result.rowCount > 0 ? { duplicate: false, id: result.rows[0].id } : { duplicate: true };
}

// ─── Processing lock (prevents concurrent processing) ───────
async function acquireLock(callSid) {
  const result = await db.query(
    `UPDATE telephony_events
     SET    locked_at = NOW(), status = 'processing'
     WHERE  call_sid = $1
       AND  (locked_at IS NULL OR locked_at < NOW() - INTERVAL '${Math.floor(LOCK_STALE_MS / 1000)} seconds')
       AND  status NOT IN ('completed', 'permanently_failed')
     RETURNING id`,
    [callSid]
  );
  return result.rowCount > 0;
}

async function releaseLock(callSid, status, errorMessage = null) {
  await db.query(
    `UPDATE telephony_events
     SET    status = $1, error_message = $2, locked_at = NULL
     WHERE  call_sid = $3`,
    [status, errorMessage, callSid]
  );
}

async function incrementRetry(callSid) {
  const result = await db.query(
    `UPDATE telephony_events
     SET    retry_count = retry_count + 1
     WHERE  call_sid = $1
     RETURNING retry_count`,
    [callSid]
  );
  return result.rows[0]?.retry_count ?? 0;
}

// ─── Timeout wrapper ────────────────────────────────────────
function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Timeout after ${ms}ms`)), ms);
    promise.then(
      (v) => { clearTimeout(timer); resolve(v); },
      (e) => { clearTimeout(timer); reject(e); }
    );
  });
}

// ─── Background processor with lock + retry + dead-letter ───
async function processCallInBackground(event) {
  const { call_sid, workflow_id, from_number, to_number, payload, request_id } = event;
  const ctx = { call_sid, workflow_id, request_id };

  // Acquire lock (atomic — only one processor wins)
  const locked = await acquireLock(call_sid);
  if (!locked) {
    logger.info("Skipped — already locked or terminal", ctx);
    return;
  }

  logger.info("Processing started", ctx);

  try {
    await withTimeout(
      startWorkflow({
        workflow_id,
        call_sid,
        from: from_number,
        to: to_number,
        payload,
      }),
      PROCESSING_TIMEOUT_MS
    );

    await releaseLock(call_sid, "completed");
    logger.info("Call processing completed", ctx);
  } catch (err) {
    const retryCount = await incrementRetry(call_sid);

    if (retryCount > MAX_RETRIES) {
      // Dead letter
      await releaseLock(call_sid, "permanently_failed", err.message);
      metrics.permanently_failed++;
      logger.error("DEAD LETTER — max retries exceeded", {
        ...ctx,
        retry_count: retryCount,
        error: err.message,
      });
    } else {
      await releaseLock(call_sid, "failed", err.message);
      metrics.failed++;
      logger.error("Call processing failed (will retry)", {
        ...ctx,
        retry_count: retryCount,
        max_retries: MAX_RETRIES,
        error: err.message,
      });
    }
  }
}

// ─── POST /api/v1/telephony/inbound/:workflow_id ────────────
router.post(
  "/inbound/:workflow_id",
  validateTwilioSignature,
  async (req, res) => {
    const startTime = Date.now();
    const request_id = logger.requestId();
    const workflow_id = parseInt(req.params.workflow_id, 10);

    // Extract Twilio fields
    const call_sid = req.body.CallSid;
    const from_number = req.body.From || req.body.Caller || "";
    const to_number = req.body.To || req.body.Called || "";
    const call_status = req.body.CallStatus || "";
    const direction = (req.body.Direction || "inbound").toLowerCase();

    const ctx = { request_id, call_sid, workflow_id, from: from_number, to: to_number };

    metrics.total++;

    // Validate required fields
    if (!call_sid) {
      logger.warn("Webhook missing CallSid", ctx);
      return sendTwiml(res, TWIML_HANGUP);
    }

    if (isNaN(workflow_id) || workflow_id < 1) {
      logger.warn("Invalid workflow_id", ctx);
      return sendTwiml(res, TWIML_HANGUP);
    }

    logger.info("Webhook received", { ...ctx, call_status, direction, payload_keys: Object.keys(req.body) });

    try {
      // Build payload snapshot (forward safe headers)
      const payload = { ...req.body, _headers: {} };
      const headerForward = [
        "x-twilio-signature",
        "i-twilio-idempotency-token",
        "x-home-region",
        "user-agent",
      ];
      for (const h of headerForward) {
        if (req.headers[h]) payload._headers[h] = req.headers[h];
      }

      const event = {
        call_sid, workflow_id, from_number, to_number,
        call_status, direction, payload, request_id,
      };

      // Atomic idempotent insert (race-safe: only 1 row wins)
      const { duplicate, id } = await atomicInsert(event);

      if (duplicate) {
        metrics.duplicates++;
        logger.info("Duplicate webhook ignored", { ...ctx, latency_ms: Date.now() - startTime });
        return sendTwiml(res, TWIML_CONNECTING);
      }

      logger.info("New call event created", { ...ctx, event_id: id });

      // Respond immediately — Twilio is waiting
      sendTwiml(res, TWIML_CONNECTING);

      // Fire-and-forget background processing
      setImmediate(() => {
        processCallInBackground(event).catch((err) => {
          logger.error("Background processor crash", { ...ctx, error: err.message });
        });
      });

      logger.info("Webhook responded", { ...ctx, latency_ms: Date.now() - startTime });
    } catch (err) {
      // NEVER crash — always return valid TwiML
      metrics.failed++;
      logger.error("Webhook handler error", {
        ...ctx,
        latency_ms: Date.now() - startTime,
        error: err.message,
        stack: err.stack,
      });
      sendTwiml(res, TWIML_CONNECTING);
    }
  }
);

// ─── GET /api/v1/telephony/health ───────────────────────────
router.get("/health", async (_req, res) => {
  try {
    const dbStart = Date.now();
    await db.query("SELECT 1");
    res.json({
      status: "ok",
      service: "telephony-webhook",
      db: "connected",
      db_latency_ms: Date.now() - dbStart,
      uptime_s: Math.floor(process.uptime()),
    });
  } catch (err) {
    res.status(503).json({ status: "degraded", db: "disconnected", error: err.message });
  }
});

// ─── GET /api/v1/telephony/metrics ──────────────────────────
router.get("/metrics", async (_req, res) => {
  try {
    const result = await db.query(
      `SELECT
         COUNT(*) AS total,
         COUNT(*) FILTER (WHERE status = 'completed') AS completed,
         COUNT(*) FILTER (WHERE status = 'failed') AS failed,
         COUNT(*) FILTER (WHERE status = 'permanently_failed') AS dead_letter,
         COUNT(*) FILTER (WHERE status = 'processing') AS in_flight
       FROM telephony_events`
    );
    const row = result.rows[0];
    res.json({
      db: row,
      runtime: {
        total_requests: metrics.total,
        duplicates_caught: metrics.duplicates,
        failures: metrics.failed,
        dead_letters: metrics.permanently_failed,
      },
      uptime_s: Math.floor(process.uptime()),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─── GET /api/v1/telephony/events/:call_sid ─────────────────
router.get("/events/:call_sid", async (req, res) => {
  try {
    const result = await db.query(
      `SELECT id, call_sid, workflow_id, status, from_number, to_number,
              retry_count, request_id, locked_at, error_message,
              created_at, updated_at
       FROM telephony_events WHERE call_sid = $1`,
      [req.params.call_sid]
    );
    if (result.rows.length === 0) {
      return res.status(404).json({ error: "Event not found" });
    }
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
