// ============================================================
// AI Agent Service — LiveKit Client
// Wraps LiveKit Server SDK for webhook validation, agent
// dispatch, and room monitoring. This is the integration layer
// between Twilio-originated LiveKit rooms and fazle-voice.
// ============================================================

"use strict";

const {
  WebhookReceiver,
  RoomServiceClient,
  AgentDispatchClient,
  AccessToken,
} = require("livekit-server-sdk");
const { config } = require("./config");
const log = require("./logger");

// ── Webhook Receiver ───────────────────────────────────────

let _receiver = null;

function getWebhookReceiver() {
  if (!_receiver) {
    _receiver = new WebhookReceiver(
      config.livekit.apiKey,
      config.livekit.apiSecret
    );
  }
  return _receiver;
}

/**
 * Validate and parse a LiveKit webhook event.
 * @param {string} body  Raw request body (string)
 * @param {string} auth  Authorization header value
 * @returns {object|null} Parsed WebhookEvent or null if invalid
 */
async function parseWebhook(body, auth) {
  try {
    const receiver = getWebhookReceiver();
    return await receiver.receive(body, auth);
  } catch (err) {
    log.warn("Webhook validation failed", { error: err.message });
    return null;
  }
}

// ── Room Service Client ────────────────────────────────────

let _roomClient = null;

function getRoomClient() {
  if (!_roomClient) {
    _roomClient = new RoomServiceClient(
      config.livekit.host,
      config.livekit.apiKey,
      config.livekit.apiSecret
    );
  }
  return _roomClient;
}

/**
 * List participants in a LiveKit room.
 * @param {string} roomName
 * @returns {Array} participants
 */
async function listParticipants(roomName) {
  try {
    const client = getRoomClient();
    const participants = await client.listParticipants(roomName);
    return participants;
  } catch (err) {
    log.error("Failed to list participants", {
      room: roomName,
      error: err.message,
    });
    return [];
  }
}

/**
 * Check if an AI agent is already present in a room.
 * Agent participants have kind=4 (AGENT) or identity starting with "agent-".
 */
async function hasAgentInRoom(roomName) {
  const participants = await listParticipants(roomName);
  return participants.some(
    (p) =>
      p.kind === 4 || // AGENT kind
      (p.identity && p.identity.startsWith("agent-"))
  );
}

// ── Agent Dispatch ─────────────────────────────────────────

let _dispatchClient = null;

function getDispatchClient() {
  if (!_dispatchClient) {
    _dispatchClient = new AgentDispatchClient(
      config.livekit.host,
      config.livekit.apiKey,
      config.livekit.apiSecret
    );
  }
  return _dispatchClient;
}

/**
 * Generate a server-to-server JWT for LiveKit API calls.
 */
async function generateServerToken() {
  const token = new AccessToken(
    config.livekit.apiKey,
    config.livekit.apiSecret,
    { identity: "ai-agent-service", ttl: "5m" }
  );
  token.addGrant({ roomAdmin: true, roomCreate: true });
  return await token.toJwt();
}

/**
 * Dispatch the fazle-voice agent to a LiveKit room.
 * Uses the SDK's AgentDispatchClient for proper auth.
 *
 * @param {string} roomName  Target room
 * @param {object} metadata  Optional metadata to pass to agent
 * @returns {boolean} true if dispatch succeeded
 */
async function dispatchAgent(roomName, metadata = {}) {
  const startMs = Date.now();

  // Check if agent is already in the room
  const alreadyPresent = await hasAgentInRoom(roomName);
  if (alreadyPresent) {
    log.info("Agent already in room, skipping dispatch", { room: roomName });
    return true;
  }

  try {
    const client = getDispatchClient();
    const metaStr = Object.keys(metadata).length > 0
      ? JSON.stringify(metadata)
      : undefined;

    const dispatch = await client.createDispatch(roomName, "", {
      metadata: metaStr,
    });

    const latencyMs = Date.now() - startMs;
    log.info("Agent dispatched successfully", {
      room: roomName,
      dispatch_id: dispatch?.agentName || dispatch?.id || "unknown",
      latency_ms: latencyMs,
    });
    return true;
  } catch (err) {
    const latencyMs = Date.now() - startMs;

    // If dispatch fails, fazle-voice auto-dispatch should still pick up the room
    log.warn("Explicit agent dispatch failed — relying on auto-dispatch", {
      room: roomName,
      error: err.message,
      latency_ms: latencyMs,
    });
    return false;
  }
}

/**
 * Detect if a participant is a SIP/phone caller (Twilio-originated).
 * SIP participants: kind=3, or identity matching sip_* / phone_* / +*
 */
function isSipParticipant(participant) {
  if (!participant) return false;
  // LiveKit protocol: kind 3 = SIP
  if (participant.kind === 3) return true;
  const id = (participant.identity || "").toLowerCase();
  if (id.startsWith("sip_") || id.startsWith("sip:")) return true;
  if (id.startsWith("phone_") || id.startsWith("phone:")) return true;
  // Phone number pattern: starts with +
  if (/^\+\d{7,}/.test(participant.identity || "")) return true;
  return false;
}

/**
 * Extract call metadata from a SIP participant.
 */
function extractCallMetadata(participant, room) {
  const identity = participant.identity || "";
  // Try to extract phone number from identity
  const phoneMatch = identity.match(/\+\d+/);
  const phone = phoneMatch ? phoneMatch[0] : identity;

  // Try to parse metadata
  let meta = {};
  try {
    meta = JSON.parse(participant.metadata || "{}");
  } catch {
    // SIP metadata may not be JSON
  }

  return {
    call_sid: meta.call_sid || meta.callSid || room.name || "",
    from_number: meta.from || phone,
    to_number: meta.to || "",
    room_name: room.name || "",
    room_sid: room.sid || "",
    participant_sid: participant.sid || "",
    participant_identity: identity,
    relationship: "social", // Phone callers default to social
    dispatched_at: new Date().toISOString(),
  };
}

module.exports = {
  parseWebhook,
  listParticipants,
  hasAgentInRoom,
  dispatchAgent,
  isSipParticipant,
  extractCallMetadata,
  generateServerToken,
  getRoomClient,
};
