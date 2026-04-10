# ============================================================
# Fazle Social Engine — Webhook Handlers
# Processes incoming WhatsApp & Facebook webhook events
# Owner conversational control + training data capture
# ============================================================
import logging
import random
import re
import time
import uuid
import io
import tempfile
from datetime import datetime, timezone

import httpx
import psycopg2.extras

from whatsapp import parse_incoming_message, download_media
from facebook import parse_webhook_entry
from redis_dedup import (
    is_duplicate_message as _is_duplicate_message,
    is_sender_locked as _is_sender_locked,
    lock_sender as _lock_sender,
    unlock_sender as _unlock_sender,
    push_to_dlq,
)
import base64

logger = logging.getLogger("fazle-social-engine")


# ── OCR: extract text from image using Tesseract ───────────
def _extract_text_from_image(image_bytes: bytes) -> tuple[str, float]:
    """Extract text from image bytes using Tesseract OCR (Bangla + English).
    Returns (text, confidence) where confidence is 0-100 average."""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes))
        # Get detailed data with confidence scores
        data = pytesseract.image_to_data(img, lang="ben+eng", output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in data["conf"] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        text = pytesseract.image_to_string(img, lang="ben+eng").strip()
        return text, avg_confidence
    except ImportError:
        logger.warning("pytesseract/Pillow not installed — OCR unavailable")
    except Exception as e:
        logger.warning(f"OCR extraction failed: {e}")
    return "", 0.0


# ── Whisper: transcribe audio locally ──────────────────────
def _transcribe_audio(audio_bytes: bytes) -> tuple[str, float]:
    """Transcribe audio bytes using faster-whisper (CTranslate2, lightweight).
    Returns (text, confidence) where confidence is average segment probability."""
    try:
        from faster_whisper import WhisperModel
        _whisper_model = getattr(_transcribe_audio, "_model", None)
        if _whisper_model is None:
            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            _transcribe_audio._model = _whisper_model
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as f:
            f.write(audio_bytes)
            f.flush()
            segments_list = []
            total_prob = 0.0
            segments, _info = _whisper_model.transcribe(f.name, language="bn")
            for seg in segments:
                segments_list.append(seg.text)
                total_prob += seg.avg_log_prob if hasattr(seg, "avg_log_prob") else -0.5
            text = " ".join(segments_list).strip()
            avg_prob = total_prob / len(segments_list) if segments_list else -1.0
            # Convert log prob to 0-1 confidence (rough approximation)
            confidence = max(0.0, min(1.0, 1.0 + avg_prob))
            return text, confidence
    except ImportError:
        logger.warning("faster-whisper not installed — local transcription unavailable")
    except Exception as e:
        logger.warning(f"Local Whisper transcription failed: {e}")
    return "", 0.0


# Low-confidence fallback messages
_OCR_LOW_CONFIDENCE_MSG = "ছবিটা ভালো করে পড়া যাচ্ছে না। আরেকটু পরিষ্কার ছবি পাঠাতে পারবেন? 🙏"
_WHISPER_LOW_CONFIDENCE_MSG = "অডিওটা ঠিকমতো শোনা যাচ্ছে না। আবার রেকর্ড করে পাঠাতে পারবেন? 🎤"
_OCR_CONFIDENCE_THRESHOLD = 40.0  # Tesseract 0-100 scale
_WHISPER_CONFIDENCE_THRESHOLD = 0.3  # 0-1 scale


def _auto_update_interest(db_conn_fn, phone: str, platform: str, message_text: str):
    """Auto-classify and update contact interest level based on message content."""
    text_lower = message_text.lower()
    # Hot signals
    hot_words = ["apply", "join", "interested", "চাই", "করতে চাই", "start", "শুরু", "ready", "confirm", "জয়েন"]
    warm_words = ["details", "salary", "বেতন", "কাজ", "location", "কোথায়", "info", "তথ্য", "জানতে"]
    risk_words = ["scam", "fake", "বাটপার", "fraud", "complain", "police"]

    interest = "unknown"
    if any(w in text_lower for w in hot_words):
        interest = "hot"
    elif any(w in text_lower for w in risk_words):
        interest = "risk"
    elif any(w in text_lower for w in warm_words):
        interest = "warm"
    else:
        return  # Don't update for unknown/cold

    try:
        from main import update_contact_interest
        update_contact_interest(db_conn_fn, phone, platform, interest)
        logger.info(f"Auto-updated interest for {phone} → {interest}")
    except Exception as e:
        logger.debug(f"Interest update failed: {e}")


# ── Owner contact update command parser ────────────────────
def _handle_owner_contact_command(text: str, db_conn_fn) -> bool:
    """Parse owner commands like 'এই নাম্বারটা client' or '01xxx is VIP'.
    Enhanced: supports personality_hint, company, and notes.
    Examples:
        '01711234567 is client'
        '01711234567 works at ABC Company'
        '01711234567 is strict' → sets personality_hint
        '01711234567 note: always asks for discount'
    """
    # Pattern: phone + relation assignment
    relation_patterns = [
        r"(01\d{9})\s+(?:is|হলো|হচ্ছে|ta)\s+(\w+)",
        r"(01\d{9})\s+(\w+)\s*$",
        r"নাম্বার(?:টা|)\s+(01\d{9})\s+(\w+)",
    ]

    # Pattern: phone + company assignment
    company_patterns = [
        r"(01\d{9})\s+(?:works?\s+at|কাজ\s+করে|company|কোম্পানি)\s+(.+)",
    ]

    # Pattern: phone + personality hint
    personality_patterns = [
        r"(01\d{9})\s+(?:is|হলো)\s+(strict|friendly|rude|polite|formal|informal|angry|calm|serious|casual|vip|important)\b",
        r"(01\d{9})\s+(?:personality|ব্যক্তিত্ব|hint)\s*[:=]\s*(.+)",
    ]

    # Pattern: phone + note
    note_patterns = [
        r"(01\d{9})\s+(?:note|নোট)\s*[:=]\s*(.+)",
    ]

    matched = False

    # Check personality hints first (before relation patterns — 'strict' is a hint, not a relation)
    for pat in personality_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            phone, hint = m.group(1), m.group(2).strip()
            try:
                from main import upsert_contact
                upsert_contact(db_conn_fn, phone, "", "whatsapp", personality_hint=hint)
                logger.info(f"Owner set personality_hint for {phone} → '{hint}'")
                return True
            except Exception as e:
                logger.warning(f"Personality hint update failed: {e}")

    # Check company assignment
    for pat in company_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            phone, company = m.group(1), m.group(2).strip()
            try:
                from main import upsert_contact
                upsert_contact(db_conn_fn, phone, "", "whatsapp", company=company)
                logger.info(f"Owner set company for {phone} → '{company}'")
                return True
            except Exception as e:
                logger.warning(f"Company update failed: {e}")

    # Check note assignment
    for pat in note_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            phone, note = m.group(1), m.group(2).strip()
            try:
                from main import upsert_contact
                upsert_contact(db_conn_fn, phone, "", "whatsapp", notes=note)
                logger.info(f"Owner added note for {phone}")
                return True
            except Exception as e:
                logger.warning(f"Note update failed: {e}")

    # Check relation assignment (standard)
    for pat in relation_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            phone, relation = m.group(1), m.group(2)
            try:
                from main import upsert_contact
                upsert_contact(db_conn_fn, phone, "", "whatsapp", relation.lower())
                logger.info(f"Owner updated contact {phone} → relation={relation}")
                return True
            except Exception as e:
                logger.warning(f"Contact update failed: {e}")

    return matched


# ── Owner Feedback Handler (Step 6) ─────────────────────────
_FEEDBACK_POSITIVE = ["good", "ভালো", "nice", "perfect", "👍", "★★★", "correct", "ঠিক", "right", "great"]
_FEEDBACK_NEGATIVE = ["wrong", "ভুল", "bad", "incorrect", "👎", "terrible", "stupid", "বাজে", "incorrect"]
_FEEDBACK_CORRECTION = ["should say", "বলো", "এভাবে বলো", "instead say", "reply should be", "correct reply"]


def _handle_owner_feedback(text: str, db_conn_fn, platform: str = "whatsapp") -> bool:
    """Detect owner feedback on AI replies and store it.
    Supports: positive ("good reply"), negative ("wrong"), correction ("should say X")."""
    text_lower = text.strip().lower()

    feedback_type = None
    rating = 0

    # Check correction first (highest priority)
    for pattern in _FEEDBACK_CORRECTION:
        if pattern in text_lower:
            feedback_type = "correction"
            rating = -1
            break

    if not feedback_type:
        for word in _FEEDBACK_NEGATIVE:
            if word in text_lower:
                feedback_type = "negative"
                rating = -1
                break

    if not feedback_type:
        for word in _FEEDBACK_POSITIVE:
            if word in text_lower:
                feedback_type = "positive"
                rating = 1
                break

    if not feedback_type:
        return False

    try:
        from main import save_owner_feedback
        # Get the last AI reply to know what's being rated
        last_ai_reply = ""
        last_customer_query = ""
        with db_conn_fn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT content FROM fazle_social_messages
                       WHERE platform = %s AND direction = 'outgoing'
                       ORDER BY created_at DESC LIMIT 1""",
                    (platform,),
                )
                row = cur.fetchone()
                if row:
                    last_ai_reply = row["content"]
                cur.execute(
                    """SELECT content FROM fazle_social_messages
                       WHERE platform = %s AND direction = 'incoming'
                       ORDER BY created_at DESC LIMIT 2""",
                    (platform,),
                )
                rows = cur.fetchall()
                if len(rows) > 1:
                    last_customer_query = rows[1]["content"]  # Skip the feedback msg itself

        correction = text if feedback_type == "correction" else ""
        save_owner_feedback(db_conn_fn, last_customer_query, last_ai_reply,
                            feedback_type=feedback_type, correction=correction,
                            rating=rating, platform=platform)

        # Boost or penalize cached reply quality based on feedback
        if last_customer_query:
            if rating > 0:
                from main import boost_reply_quality
                boost_reply_quality(db_conn_fn, last_customer_query, 0.15)
            elif rating < 0:
                from main import penalize_reply_quality
                penalize_reply_quality(db_conn_fn, last_customer_query, 0.25)

        logger.info(f"Owner feedback stored: {feedback_type} (rating={rating})")
        return True
    except Exception as e:
        logger.warning(f"Owner feedback processing failed: {e}")
        return False


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


def _normalize_phone(phone: str) -> str:
    """Normalize phone number: strip +, spaces, dashes. Add BD country code if needed."""
    p = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").lstrip("+").strip()
    # Add Bangladesh country code if starts with 0
    if p.startswith("0") and len(p) == 11:
        p = "88" + p
    return p


def _is_owner(sender_id: str, owner_phone: str) -> bool:
    """Check if the sender is the owner (Azim).
    Normalises phone numbers for consistent matching."""
    if not owner_phone:
        return False
    return _normalize_phone(sender_id) == _normalize_phone(owner_phone)


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

        # ── Dedup: skip if we already processed this message_id ──
        msg_id = msg.get("message_id", "")
        if _is_duplicate_message(msg_id):
            logger.info(f"Dedup: skipping duplicate message {msg_id} from {msg.get('sender_id', '?')}")
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

            # ── LOCAL PROCESSING: OCR for images, Whisper for audio ──
            local_text = ""
            if msg_type == "image":
                local_text, ocr_confidence = _extract_text_from_image(media_bytes)
                if local_text:
                    logger.info(f"OCR extracted {len(local_text)} chars (confidence={ocr_confidence:.1f})")
                    # Store multimodal learning (Step 15)
                    try:
                        from main import save_multimodal_learning
                        save_multimodal_learning(db_conn_fn, "image", local_text,
                                                 sender_phone=msg["sender_id"],
                                                 context=msg.get("caption", ""),
                                                 description=f"OCR confidence: {ocr_confidence:.1f}")
                    except Exception as e:
                        logger.debug(f"Multimodal learning save failed: {e}")
                    # Low confidence → ask user to resend clearer image
                    if ocr_confidence < _OCR_CONFIDENCE_THRESHOLD and len(local_text) < 20:
                        logger.info(f"OCR confidence too low ({ocr_confidence:.1f}), asking for clearer image")
                        creds_ocr = get_creds_fn("whatsapp")
                        if creds_ocr:
                            from whatsapp import send_message
                            await send_message(
                                creds_ocr.get("whatsapp_api_url", ""),
                                creds_ocr.get("access_token", ""),
                                creds_ocr.get("phone_number_id", ""),
                                msg["sender_id"],
                                _OCR_LOW_CONFIDENCE_MSG,
                            )
                        processed += 1
                        continue

            elif msg_type == "audio":
                local_text, whisper_confidence = _transcribe_audio(media_bytes)
                if local_text:
                    logger.info(f"Whisper transcribed {len(local_text)} chars (confidence={whisper_confidence:.2f})")
                    # Store multimodal learning (Step 15)
                    try:
                        from main import save_multimodal_learning
                        save_multimodal_learning(db_conn_fn, "audio", local_text,
                                                 sender_phone=msg["sender_id"],
                                                 description=f"Whisper confidence: {whisper_confidence:.2f}")
                    except Exception as e:
                        logger.debug(f"Multimodal learning save failed: {e}")
                    # Owner audio → save for style learning (Steps 13, 14)
                    if is_owner_msg:
                        try:
                            from main import save_owner_audio_profile
                            save_owner_audio_profile(db_conn_fn, local_text,
                                                     context="voice_message", tone="natural")
                            logger.info(f"Owner audio profile saved: {len(local_text)} chars")
                        except Exception as e:
                            logger.debug(f"Owner audio profile save failed: {e}")
                    # Low confidence or too short → ask to repeat
                    if (whisper_confidence < _WHISPER_CONFIDENCE_THRESHOLD or len(local_text.strip()) < 5):
                        logger.info(f"Whisper confidence too low ({whisper_confidence:.2f}), asking to repeat")
                        creds_wh = get_creds_fn("whatsapp")
                        if creds_wh:
                            from whatsapp import send_message
                            await send_message(
                                creds_wh.get("whatsapp_api_url", ""),
                                creds_wh.get("access_token", ""),
                                creds_wh.get("phone_number_id", ""),
                                msg["sender_id"],
                                _WHISPER_LOW_CONFIDENCE_MSG,
                            )
                        processed += 1
                        continue

            media_b64 = base64.b64encode(media_bytes).decode("utf-8")

            # Route to brain /chat/multimodal (with local_text hint to reduce token usage)
            multimodal_reply = await _call_brain_multimodal(
                brain_url=brain_url,
                media_type=msg_type if msg_type in ("image", "audio") else "image",
                media_base64=media_b64,
                caption=msg.get("caption", ""),
                sender_id=msg["sender_id"],
                sender_name=msg["sender_name"],
                platform="whatsapp",
                is_owner=is_owner_msg,
                local_extracted_text=local_text,
            )
            if not multimodal_reply:
                multimodal_reply = "\u09a6\u09c1\u0983\u0996\u09bf\u09a4, \u098f\u0987 \u09ae\u09bf\u09a1\u09bf\u09df\u09be \u098f\u0996\u09a8 \u09aa\u09cd\u09b0\u09b8\u09c7\u09b8 \u0995\u09b0\u09a4\u09c7 \u09aa\u09be\u09b0\u099b\u09bf \u09a8\u09be\u0964 \u098f\u0995\u099f\u09c1 \u09aa\u09b0\u09c7 \u0986\u09ac\u09be\u09b0 \u099a\u09c7\u09b7\u09cd\u099f\u09be \u0995\u09b0\u09c1\u09a8\u0964"
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

            # Check for contact update commands: "এই নাম্বারটা client" / "01xxx is client"
            _handle_owner_contact_command(msg["text"], db_conn_fn)

            # ── Owner Feedback Detection (Step 6) ──
            # Check if owner is correcting/rating the last AI reply
            _handle_owner_feedback(msg["text"], db_conn_fn, "whatsapp")

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
            if not owner_reply:
                owner_reply = "\u09ac\u09c1\u099d\u09c7\u099b\u09bf, Azim\u0964 \u098f\u0995\u099f\u09c1 \u09aa\u09b0\u09c7 \u0986\u09ac\u09be\u09b0 \u099a\u09c7\u09b7\u09cd\u099f\u09be \u0995\u09b0\u09c1\u09a8\u0964"
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
        # Step 0: Upsert contact in contact book + fetch contact data
        contact_data = None
        try:
            from main import upsert_contact, get_contact
            upsert_contact(db_conn_fn, msg["sender_id"], msg["sender_name"] or "", "whatsapp")
            contact_data = get_contact(db_conn_fn, msg["sender_id"], "whatsapp")
        except Exception as e:
            logger.warning(f"Contact upsert/fetch failed: {e}")

        # Determine if this is a priority contact (VIP/client get faster processing)
        is_priority = False
        contact_relation = ""
        if contact_data:
            contact_relation = (contact_data.get("relation") or "unknown").lower()
            is_priority = contact_relation in ("vip", "client")

        # ── FIX 1+10: NO ACK before brain — get AI reply FIRST, send ONCE ──
        # Step 1: Check reply reuse cache BEFORE calling LLM
        cached_reply = None
        if not is_priority:
            try:
                from main import find_cached_reply
                cached_reply = find_cached_reply(db_conn_fn, msg["text"], "whatsapp")
                if cached_reply:
                    logger.info(f"Reply reuse hit for {msg['sender_id']} — skipping LLM")
            except Exception as e:
                logger.debug(f"Reply cache check failed: {e}")

        if cached_reply:
            # Send cached reply directly — no ACK, no LLM
            creds = get_creds_fn("whatsapp")
            if creds:
                from whatsapp import send_message
                result = await send_message(
                    creds.get("whatsapp_api_url", ""),
                    creds.get("access_token", ""),
                    creds.get("phone_number_id", ""),
                    msg["sender_id"],
                    cached_reply,
                )
                with db_conn_fn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO fazle_social_messages
                               (platform, direction, contact_identifier, content, metadata, status)
                               VALUES ('whatsapp', 'outgoing', %s, %s, %s, %s)""",
                            (msg["sender_id"], cached_reply,
                             psycopg2.extras.Json({"source": "reply_cache"}),
                             "sent" if result.get("sent") else "failed"),
                        )
                    conn.commit()
            try:
                _auto_update_interest(db_conn_fn, msg["sender_id"], "whatsapp", msg["text"])
            except Exception:
                pass
            processed += 1
            continue

        # Step 2: Call brain for AI response — NO ACK sent yet
        # Rate-limit: skip if we're already processing a reply for this sender
        if _is_sender_locked(msg["sender_id"]):
            logger.info(f"Rate-limit: sender {msg['sender_id']} still in cooldown — skipping")
            processed += 1
            continue
        _lock_sender(msg["sender_id"])

        brain_context = ""
        if contact_data:
            brain_context += f"Contact: {contact_data.get('name', '')} ({contact_relation})"
            if contact_data.get("company"):
                brain_context += f" from {contact_data['company']}"
            if contact_data.get("personality_hint"):
                brain_context += f". Hint: {contact_data['personality_hint']}"
            brain_context += "\n"

        ai_reply = await _call_brain(
            brain_url, msg["text"], "whatsapp", msg["sender_name"],
            sender_id=msg["sender_id"], ack_sent=False,
            context=brain_context if brain_context else "",
        )
        _unlock_sender(msg["sender_id"])

        # FIX 1: Fallback ONLY if brain returned nothing
        if not ai_reply or not ai_reply.strip():
            ai_reply = "দুঃখিত, একটু সমস্যা হয়েছে। আবার বলবেন?"
            logger.warning(f"Brain returned empty for {msg['sender_id']} — using fallback")
            push_to_dlq(
                {"sender_id": msg["sender_id"], "text": msg["text"], "message_id": msg_id},
                "brain_returned_empty",
                platform="whatsapp",
            )

        # Step 3: Send the SINGLE AI reply (no ACK before it)
        # Save reply for future reuse
        try:
            from main import save_chat_reply
            save_chat_reply(db_conn_fn, msg["text"], ai_reply,
                            category=contact_relation or "unknown",
                            platform="whatsapp", source="llm")
        except Exception as e:
            logger.debug(f"Reply cache save failed: {e}")

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
            with db_conn_fn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO fazle_social_messages
                           (platform, direction, contact_identifier, content, status)
                           VALUES ('whatsapp', 'outgoing', %s, %s, %s)""",
                        (msg["sender_id"], ai_reply, "sent" if result.get("sent") else "failed"),
                    )
                conn.commit()

        try:
            _auto_update_interest(db_conn_fn, msg["sender_id"], "whatsapp", msg["text"])
        except Exception:
            pass
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
                if not ai_reply:
                    ai_reply = "\u09a7\u09a8\u09cd\u09af\u09ac\u09be\u09a6! \u0986\u09b0\u0993 \u099c\u09be\u09a8\u09a4\u09c7 WhatsApp-\u098f \u09ae\u09c7\u09b8\u09c7\u099c \u0995\u09b0\u09c1\u09a8\u0964"
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
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        async with httpx.AsyncClient(timeout=55.0) as client:
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
    platform: str, is_owner: bool, local_extracted_text: str = "",
) -> str:
    """Call Brain /chat/multimodal endpoint for image/audio processing."""
    try:
        async with httpx.AsyncClient(timeout=55.0) as client:
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
                    "local_extracted_text": local_extracted_text,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("reply", "")
            logger.error(f"Brain multimodal returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Brain multimodal API call failed: {e}")
    return ""
