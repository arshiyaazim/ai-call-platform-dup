const logger = require("../utils/logger");

const DOGRAH_API_URL =
  process.env.DOGRAH_API_URL || "http://dograh-api:8000/api/v1";

/**
 * Forward the inbound call to Dograh's existing workflow engine.
 * This bridges our idempotent webhook layer to the real call handler.
 */
async function startWorkflow({ workflow_id, call_sid, from, to, payload }) {
  const url = `${DOGRAH_API_URL}/telephony/inbound/${workflow_id}`;

  logger.info("Starting workflow via Dograh API", {
    workflow_id,
    call_sid,
    url,
  });

  const body = new URLSearchParams({
    CallSid: call_sid,
    AccountSid: payload.AccountSid || "",
    From: from,
    To: to,
    CallStatus: payload.CallStatus || "ringing",
    Direction: payload.Direction || "inbound",
    ApiVersion: payload.ApiVersion || "2010-04-01",
    ...(payload.Caller && { Caller: payload.Caller }),
    ...(payload.Called && { Called: payload.Called }),
    ...(payload.FromCountry && { FromCountry: payload.FromCountry }),
    ...(payload.ToCountry && { ToCountry: payload.ToCountry }),
  });

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "TwilioProxy/1.1",
  };

  // Forward original Twilio headers if present in payload._headers
  if (payload._headers) {
    const fwd = ["x-twilio-signature", "i-twilio-idempotency-token", "x-home-region"];
    for (const h of fwd) {
      if (payload._headers[h]) headers[h] = payload._headers[h];
    }
  }

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: body.toString(),
    signal: AbortSignal.timeout(12000),
  });

  const text = await res.text();

  if (!res.ok) {
    throw new Error(`Dograh API returned ${res.status}: ${text.substring(0, 200)}`);
  }

  logger.info("Workflow started successfully", {
    workflow_id,
    call_sid,
    dograh_status: res.status,
  });

  return text; // TwiML from Dograh
}

module.exports = { startWorkflow };
