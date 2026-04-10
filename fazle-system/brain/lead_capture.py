# ============================================================
# Fazle Brain — Lead Capture Module
# Extracts name + phone from messages, posts to API
# ============================================================
import re
import logging
import httpx

logger = logging.getLogger("fazle-brain.lead")

_PHONE_RE = re.compile(r"01[3-9]\d{8}")

LEAD_INTENTS = {
    # Job seekers
    "job_inquiry", "job_no_experience", "job_no_education", "job_how_to_apply",
    "job_joining_fee", "job_resignation", "job_details", "job_duty_hours",
    "job_post_duty", "job_salary_payment", "job_leave", "job_accommodation",
    "salary_query",
    # Client / service requests
    "service_office", "service_factory", "service_marine", "service_event",
    "service_vip", "guard_request", "security_service", "rate_inquiry",
    # Complaints
    "complaint_absent", "complaint_lazy", "complaint_rude", "complaint_abandoned",
    "complaint_theft", "complaint",
    # Operations
    "replacement", "emergency", "billing",
}

PHONE_PROMPT = "\n\nআপনার নাম ও মোবাইল নাম্বারটি দিলে দ্রুত যোগাযোগ করা যাবে।"

_API_BASE = "http://fazle-api:8100"


def extract_lead_data(message: str) -> dict:
    """Extract phone and name from a message."""
    phone_match = _PHONE_RE.search(message)
    phone = phone_match.group() if phone_match else None

    name = None
    lower = message.lower()
    for marker in ["আমার নাম ", "নাম ", "name ", "ami ", "আমি "]:
        idx = lower.find(marker)
        if idx != -1:
            after = message[idx + len(marker):].strip()
            # Take first 2 words, skip phone numbers and common non-name words
            skip_words = {"guard", "er", "chakri", "chai", "korte", "lagbe", "der", "ta", "te", "job", "ki"}
            words = []
            for w in after.split()[:4]:
                if _PHONE_RE.match(w) or w.lower() in skip_words:
                    break
                words.append(w)
            candidate = " ".join(words).strip(",. ")
            if candidate and len(candidate) > 1:
                name = candidate
                break

    return {"phone": phone, "name": name}


async def try_capture_lead(
    message: str,
    intent: str | None,
    conv_id: str,
    reply: str,
) -> str:
    """Attempt lead capture. Returns reply (possibly with phone prompt appended)."""
    if not intent or intent not in LEAD_INTENTS:
        return reply

    data = extract_lead_data(message)

    # Fire-and-forget POST to API
    payload = {
        "name": data["name"],
        "phone": data["phone"],
        "message": message[:500],
        "intent": intent,
        "source": f"social:{conv_id}",
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(f"{_API_BASE}/leads/capture", json=payload)
            if resp.status_code == 200:
                logger.info(f"Lead captured: phone={data['phone']} intent={intent}")
            elif resp.status_code == 409:
                logger.info(f"Lead dedup: phone={data['phone']} already exists")
            else:
                logger.warning(f"Lead capture failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Lead capture error: {e}")

    # Append phone prompt if no phone detected
    if not data["phone"]:
        reply += PHONE_PROMPT

    return reply
