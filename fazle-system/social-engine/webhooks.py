# ============================================================
# Fazle Social Engine — Webhook Handlers
# Processes incoming WhatsApp & Facebook webhook events
# Owner conversational control + training data capture
# ============================================================
import logging
import random
import uuid
from datetime import datetime, timezone

import httpx
import psycopg2.extras

from whatsapp import parse_incoming_message, download_media
from facebook import parse_webhook_entry
import base64

logger = logging.getLogger("fazle-social-engine")

# ── Instant ACK variations for WhatsApp ─────────────────────
_ACK_VARIATIONS = [
    "একটু দেখছি...",
    "ঠিক আছে, দেখি...",
    "একটু সময় দিন...",
    "দেখছি একটু...",
    "হুম, দেখি...",
]


def _pick_ack_message(message_text: str) -> str:
    """Pick a context-aware instant acknowledgement message."""
    msg_lower = message_text.strip().lower()
    # Urgent messages get a faster-feeling ack
    if any(w in msg_lower for w in ["urgent", "emergency", "জরুরি", "দরকার", "help", "সাহায্য"]):
        return "এখনই দেখছি!"
    # Greeting gets a quick greeting-style ack
    if any(w in msg_lower for w in ["hi", "hello", "hey", "assalamu", "সালাম"]):
        return "হ্যাঁ বলুন..."
    return random.choice(_ACK_VARIATIONS)


async def _send_whatsapp_ack(get_creds_fn, sender_id: str, ack_text: str) -> bool:
    """Send an instant acknowledgement message via WhatsApp. Returns True if sent."""
    try:
        creds = get_creds_fn("whatsapp")
        if not creds:
            return False
        from whatsapp import send_message
        result = await send_message(
            creds.get("whatsapp_api_url", ""),
            creds.get("access_token", ""),
            creds.get("phone_number_id", ""),
            sender_id,
            ack_text,
        )
        return result.get("sent", False)
    except Exception as e:
        logger.warning(f"WhatsApp instant ACK failed: {e}")
        return False


def _is_owner(sender_id: str, owner_phone: str) -> bool:
    """Check if the sender is the owner (Azim).
    Normalises phone numbers by stripping leading '+' for comparison."""
    if not owner_phone:
        return False
    norm = lambda x: x.lstrip("+").strip()
    return norm(sender_id) == norm(owner_phone)


async def _get_last_customer_message(db_conn_fn, platform: str, owner_phone: str) -> dict | None:
    """Fetch the most recent incoming message from a NON-owner on this platform.
    Returns {contact_identifier, content} or None."""
    try:
        with db_conn_fn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                norm_owner = owner_phone.lstrip("+").strip()
                cur.execute(
                    """SELECT contact_identifier, content FROM fazle_social_messages
                       WHERE platform = %s AND direction = 'incoming'
                         AND contact_identifier != %s
                       ORDER BY created_at DESC LIMIT 1""",
                    (platform, norm_owner),
                )
                return cur.fetchone()
    except Exception as e:
        logger.warning(f"Failed to fetch last customer message: {e}")
    return None


async def _store_owner_training(
    learning_engine_url: str, memory_url: str,
    customer_msg: str, owner_reply: str,
    platform: str, sender_id: str,
):
    """Store owner reply as training data in both learning engine & memory service."""
    transcript = f"Customer: {customer_msg}\nOwner: {owner_reply}"
    training_text = f"When a customer says: {customer_msg}\nAzim (owner) replied: {owner_reply}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Send to learning engine for behavioral analysis
        try:
            await client.post(
                f"{learning_engine_url}/learn",
                json={
                    "transcript": transcript,
                    "user": "owner",
                    "conversation_id": f"owner-training-{platform}-{sender_id}",
                },
            )
            logger.info(f"Owner training stored in learning engine: {owner_reply[:60]}...")
        except Exception as e:
            logger.warning(f"Learning engine training failed: {e}")

        # 2. Store in Qdrant memory as 'knowledge' for retrieval during inference
        try:
            await client.post(
                f"{memory_url}/store",
                json={
                    "type": "knowledge",
                    "user": "owner",
                    "content": {
                        "kind": "owner_training",
                        "customer_message": customer_msg,
                        "owner_reply": owner_reply,
                        "platform": platform,
                    },
                    "text": training_text,
                },
            )
            logger.info("Owner training stored in memory service")
        except Exception as e:
            logger.warning(f"Memory store training failed: {e}")


async def handle_whatsapp_webhook(
    payload: dict, db_conn_fn, brain_url: str, get_creds_fn,
    owner_phone: str = "", learning_engine_url: str = "",
) -> dict:
    """Process an incoming WhatsApp webhook event.
    Flow: parse message → store → owner detection → call Brain OR store training."""
    messages = parse_incoming_message(payload)
    processed = 0

    for msg in messages:
        msg_type = msg.get("type", "text")
        has_text = bool(msg.get("text"))
        has_media = bool(msg.get("media_id"))

        if not has_text and not has_media:
            continue

        is_owner_msg = _is_owner(msg["sender_id"], owner_phone)

        # Determine content for DB storage
        db_content = msg["text"] or msg.get("caption", "") or f"[{msg_type}]"

        # Store incoming message
        with db_conn_fn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO fazle_social_messages
                       (platform, direction, contact_identifier, content, metadata, status)
                       VALUES ('whatsapp', 'incoming', %s, %s, %s, 'received')""",
                    (msg["sender_id"], db_content,
                     psycopg2.extras.Json({
                         "sender_name": msg["sender_name"],
                         "is_owner": is_owner_msg,
                         "type": msg_type,
                     })),
                )
                # Upsert contact
                cur.execute(
                    """INSERT INTO fazle_social_contacts (name, platform, identifier, metadata)
                       VALUES (%s, 'whatsapp', %s, '{}')
                       ON CONFLICT (platform, identifier) DO UPDATE SET name = EXCLUDED.name""",
                    (msg["sender_name"] or msg["sender_id"], msg["sender_id"]),
                )
            conn.commit()

        # ──────────── MEDIA MESSAGE (image/audio/video/document) ────────────
        if has_media and msg_type in ("image", "audio", "video", "document"):
            creds = get_creds_fn("whatsapp")
            if not creds:
                logger.warning("No WhatsApp creds for media download")
                processed += 1
                continue

            # Download media from WhatsApp
            media_bytes = await download_media(
                api_url=creds.get("whatsapp_api_url", ""),
                api_token=creds.get("access_token", ""),
                media_id=msg["media_id"],
            )
            if not media_bytes:
                logger.error(f"Failed to download media {msg['media_id']}")
                processed += 1
                continue

            media_b64 = base64.b64encode(media_bytes).decode("utf-8")

            # Route to brain /chat/multimodal
            multimodal_reply = await _call_brain_multimodal(
                brain_url=brain_url,
                media_type=msg_type if msg_type in ("image", "audio") else "image",
                media_base64=media_b64,
                caption=msg.get("caption", ""),
                sender_id=msg["sender_id"],
                sender_name=msg["sender_name"],
                platform="whatsapp",
                is_owner=is_owner_msg,
            )
            if multimodal_reply:
                from whatsapp import send_message
                result = await send_message(
                    creds.get("whatsapp_api_url", ""),
                    creds.get("access_token", ""),
                    creds.get("phone_number_id", ""),
                    msg["sender_id"],
                    multimodal_reply,
                )
                with db_conn_fn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO fazle_social_messages
                               (platform, direction, contact_identifier, content, metadata, status)
                               VALUES ('whatsapp', 'outgoing', %s, %s, %s, %s)""",
                            (msg["sender_id"], multimodal_reply,
                             psycopg2.extras.Json({"is_owner_reply": is_owner_msg, "media_type": msg_type}),
                             "sent" if result.get("sent") else "failed"),
                        )
                    conn.commit()
            processed += 1
            continue

        # ──────────── TEXT MESSAGE ────────────
        if not has_text:
            processed += 1
            continue

        if is_owner_msg:
            # OWNER MESSAGE — conversational control + optional training capture
            logger.info(f"Owner message detected from {msg['sender_id']}: {msg['text'][:80]}")

            # If owner is replying to a recent customer message, also store as training
            last_customer = await _get_last_customer_message(db_conn_fn, "whatsapp", owner_phone)
            if last_customer and not msg["text"].startswith("/"):
                memory_url = brain_url.replace("fazle-brain:8200", "fazle-memory:8300") if "fazle-brain" in brain_url else "http://fazle-memory:8300"
                await _store_owner_training(
                    learning_engine_url=learning_engine_url,
                    memory_url=memory_url,
                    customer_msg=last_customer["content"],
                    owner_reply=msg["text"],
                    platform="whatsapp",
                    sender_id=msg["sender_id"],
                )

            # Route to /chat/owner for conversational control
            owner_reply = await _call_brain_owner(
                brain_url, msg["text"], "whatsapp", msg["sender_id"]
            )
            if owner_reply:
                # Send AI reply back to owner on WhatsApp
                creds = get_creds_fn("whatsapp")
                if creds:
                    from whatsapp import send_message
                    result = await send_message(
                        creds.get("whatsapp_api_url", ""),
                        creds.get("access_token", ""),
                        creds.get("phone_number_id", ""),
                        msg["sender_id"],
                        owner_reply,
                    )
                    # Store outgoing reply to owner
                    with db_conn_fn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """INSERT INTO fazle_social_messages
                                   (platform, direction, contact_identifier, content, metadata, status)
                                   VALUES ('whatsapp', 'outgoing', %s, %s, %s, %s)""",
                                (msg["sender_id"], owner_reply,
                                 psycopg2.extras.Json({"is_owner_reply": True}),
                                 "sent" if result.get("sent") else "failed"),
                            )
                        conn.commit()
            processed += 1
            continue

        # ── INSTANT ACK + DELAYED FINAL RESPONSE ──
        # Step 1: Send instant acknowledgement (<1s perceived response)
        ack_text = _pick_ack_message(msg["text"])
        ack_sent = await _send_whatsapp_ack(get_creds_fn, msg["sender_id"], ack_text)
        if ack_sent:
            logger.info(f"Instant ACK sent to {msg['sender_id']}: {ack_text}")

        # Step 2: Process brain response (runs after ACK is already delivered)
        ai_reply = await _call_brain(brain_url, msg["text"], "whatsapp", msg["sender_name"], sender_id=msg["sender_id"], ack_sent=ack_sent)
        if ai_reply:
            # Step 3: Send final AI reply
            creds = get_creds_fn("whatsapp")
            if creds:
                from whatsapp import send_message
                result = await send_message(
                    creds.get("whatsapp_api_url", ""),
                    creds.get("access_token", ""),
                    creds.get("phone_number_id", ""),
                    msg["sender_id"],
                    ai_reply,
                )
                # Store outgoing reply (only the final reply, not the ACK)
                with db_conn_fn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO fazle_social_messages
                               (platform, direction, contact_identifier, content, status)
                               VALUES ('whatsapp', 'outgoing', %s, %s, %s)""",
                            (msg["sender_id"], ai_reply, "sent" if result.get("sent") else "failed"),
                        )
                    conn.commit()
        processed += 1

    return {"processed": processed, "total_messages": len(messages)}


async def handle_facebook_webhook(
    payload: dict, db_conn_fn, brain_url: str, get_creds_fn,
    owner_phone: str = "", learning_engine_url: str = "",
) -> dict:
    """Process an incoming Facebook webhook event.
    Flow: parse event → if comment → sentiment analysis → auto-reply."""
    events = parse_webhook_entry(payload)
    processed = 0

    for event in events:
        if event["field"] == "feed" and event["verb"] in ("add", "edited") and event["message"]:
            # Store incoming message/comment
            with db_conn_fn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO fazle_social_messages
                           (platform, direction, contact_identifier, content, metadata, status)
                           VALUES ('facebook', 'incoming', %s, %s, %s, 'received')""",
                        (event["sender_id"], event["message"],
                         psycopg2.extras.Json({"sender_name": event["sender_name"], "post_id": event["post_id"]})),
                    )
                conn.commit()

            # Auto-reply with AI if it's a comment
            if event["item"] == "comment" and event["comment_id"]:
                ai_reply = await _call_brain(
                    brain_url, event["message"], "facebook",
                    event["sender_name"],
                    sender_id=event["sender_id"],
                    context="Facebook public comment reply. Keep it very short (1-2 lines). Redirect to WhatsApp/inbox for details."
                )
                if ai_reply:
                    creds = get_creds_fn("facebook")
                    if creds:
                        from facebook import reply_to_comment
                        result = await reply_to_comment(
                            event["comment_id"],
                            creds.get("page_access_token", ""),
                            ai_reply,
                        )
                        with db_conn_fn() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """INSERT INTO fazle_social_messages
                                       (platform, direction, contact_identifier, content, status)
                                       VALUES ('facebook', 'outgoing', %s, %s, %s)""",
                                    (event["sender_id"], ai_reply, "sent" if result.get("sent") else "failed"),
                                )
                            conn.commit()
            processed += 1

    return {"processed": processed, "total_events": len(events)}


async def _call_brain_owner(brain_url: str, message: str, platform: str,
                            sender_id: str) -> str:
    """Call Brain /chat/owner endpoint for owner conversational control."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{brain_url}/chat/owner",
                json={
                    "message": message,
                    "sender_id": sender_id,
                    "platform": platform,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("reply", "")
                intent = data.get("intent")
                if intent:
                    logger.info(f"Owner intent detected: {intent}, action_taken: {data.get('action_taken')}")
                return reply
    except Exception as e:
        logger.error(f"Brain owner API call failed: {e}")
    return ""


async def _call_brain(brain_url: str, message: str, platform: str,
                      sender: str, sender_id: str = "", context: str = "",
                      ack_sent: bool = False) -> str:
    """Call Fazle Brain API to generate a persona-aware response.
    Uses stable conversation_id per user (platform:sender_id) for continuity."""
    try:
        # Stable conversation_id per user — NOT random UUID
        # This ensures Redis conversation history persists across messages
        stable_id = sender_id or sender or uuid.uuid4().hex[:8]
        payload = {
            "message": message,
            "user": sender or "Social Bot",
            "relationship": "social",
            "conversation_id": f"social-{platform}-{stable_id}",
            "ack_sent": ack_sent,
        }
        if context:
            payload["context"] = context
        else:
            payload["context"] = f"Platform: {platform}. Reply naturally."
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{brain_url}/chat",
                json=payload,
            )
            if resp.status_code == 200:
                return resp.json().get("reply", "")
    except Exception as e:
        logger.error(f"Brain API call failed: {e}")
    return ""


async def _call_brain_multimodal(
    brain_url: str, media_type: str, media_base64: str,
    caption: str, sender_id: str, sender_name: str,
    platform: str, is_owner: bool,
) -> str:
    """Call Brain /chat/multimodal endpoint for image/audio processing."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{brain_url}/chat/multimodal",
                json={
                    "media_type": media_type,
                    "media_base64": media_base64,
                    "caption": caption,
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "platform": platform,
                    "is_owner": is_owner,
                    "conversation_id": f"social-{platform}-{sender_id}",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("reply", "")
            logger.error(f"Brain multimodal returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Brain multimodal API call failed: {e}")
    return ""
