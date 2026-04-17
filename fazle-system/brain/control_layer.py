# ============================================================
# Fazle Brain — Unified Control Layer
# SINGLE DECISION ENGINE for all incoming messages.
#
# Pipeline:
#   1. Global fail-safe
#   2. Rate limit / spam control
#   3. Context memory (last 3 messages)
#   4. Intent detection (scored)
#   5. Role-based routing
#   6. Route execution (WBOM / owner / client / job_seeker)
#   7. Multi-intent handling
#   8. Universal fallback
#   9. Response formatting
#  10. Structured logging
# ============================================================

import json
import logging
import re
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import httpx
import redis

logger = logging.getLogger("fazle-brain.control")

# ── Redis setup (lazy) ──────────────────────────────────────
_REDIS_URL: str = ""
_redis: Optional[redis.Redis] = None


def init_control_layer(redis_url: str):
    """Call once at app startup to configure Redis URL."""
    global _REDIS_URL
    _REDIS_URL = redis_url


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(_REDIS_URL, decode_responses=True)
    return _redis


# ═══════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════

@dataclass
class IncomingMessage:
    """Unified input envelope."""
    user_id: str
    message: str
    sender_role: str          # employee | client | job_seeker | owner | admin | social_unknown
    phone: str = ""
    timestamp: str = ""
    source: str = "whatsapp"
    conversation_id: str = ""
    context: str = ""


@dataclass
class ControlResult:
    """Unified output envelope."""
    reply: str
    intent: str = "unknown"
    confidence: float = 0.0
    route: str = "safe_fallback"
    status: str = "success"       # success | fallback | error
    sender_role: str = ""
    secondary_intents: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    reason: list[str] = field(default_factory=list)
    # Owner command flow
    needs_confirmation: bool = False
    draft: str = ""


# ═══════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════

_SAFE_FALLBACK_BN = "দুঃখিত, সাময়িক সমস্যা হচ্ছে। আবার চেষ্টা করুন।"
_RATE_LIMIT_BN = "দয়া করে একটু ধীরে লিখুন।"
_CLARIFY_BN = "আপনার প্রশ্নটি একটু পরিষ্কার করে বলবেন?"
_WBOM_ERROR_BN = "আপনার তথ্য আনতে সমস্যা হচ্ছে। একটু পরে আবার চেষ্টা করুন।"
_DATA_PROCESSED_BN = "আপনার তথ্য প্রক্রিয়া হয়েছে।"

# Rate-limit: 1 message per 2 seconds per user
_RATE_LIMIT_SECONDS = 2
# Context memory: keep last N messages per user
_CONTEXT_DEPTH = 3
_CONTEXT_TTL = 600  # 10 minutes

# Priority order (lower = higher priority)
ROLE_PRIORITY = {
    "owner": 0,
    "admin": 1,
    "client": 2,
    "employee": 3,
    "job_seeker": 4,
    "social_unknown": 5,
}


# ═══════════════════════════════════════════════════════════
# STEP 2 — Rate Limit
# ═══════════════════════════════════════════════════════════

def _check_rate_limit(user_id: str) -> bool:
    """Return True if user is rate-limited (should be rejected)."""
    r = _get_redis()
    key = f"ctrl:rate:{user_id}"
    if r.exists(key):
        return True
    r.setex(key, _RATE_LIMIT_SECONDS, "1")
    return False


# ═══════════════════════════════════════════════════════════
# STEP 3 — Context Memory (short-term)
# ═══════════════════════════════════════════════════════════

def _push_context(user_id: str, message: str):
    """Store latest message in per-user context ring-buffer (Redis list)."""
    r = _get_redis()
    key = f"ctrl:ctx:{user_id}"
    r.lpush(key, message)
    r.ltrim(key, 0, _CONTEXT_DEPTH - 1)
    r.expire(key, _CONTEXT_TTL)


def _get_context(user_id: str) -> list[str]:
    """Return last N messages (newest first)."""
    r = _get_redis()
    key = f"ctrl:ctx:{user_id}"
    return r.lrange(key, 0, _CONTEXT_DEPTH - 1)


# ═══════════════════════════════════════════════════════════
# STEP 5 — Owner Command Detection
# ═══════════════════════════════════════════════════════════

# Patterns for owner financial commands (Bangla natural language)
_OWNER_SEND_MONEY_PATTERNS = [
    # "করিমকে ১০০০ টাকা পাঠাও"
    re.compile(
        r"(.+?)(?:কে|কেই)\s+([\d,\.০-৯]+)\s*টাকা\s*(?:পাঠাও|দাও|পাঠিয়ে|পাঠা|দিও|দিয়ে)",
        re.IGNORECASE,
    ),
    # "রহিমের স্যালারি পাঠাও"
    re.compile(
        r"(.+?)(?:র|এর)\s+(?:স্যালারি|বেতন|salary)\s*(?:পাঠাও|দাও|পাঠিয়ে|দিয়ে)",
        re.IGNORECASE,
    ),
    # "জামালের খাবার + ভাড়া পাঠাও"
    re.compile(
        r"(.+?)(?:র|এর)\s+(.+?)\s*(?:পাঠাও|দাও|পাঠিয়ে|দিয়ে)",
        re.IGNORECASE,
    ),
]

# Bangla digits to ASCII
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _parse_bangla_number(s: str) -> float | None:
    """Convert Bangla/mixed numeric string to float."""
    s = s.translate(_BN_DIGITS).replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class OwnerCommand:
    employee_name: str
    amount: float | None = None
    tx_type: str = "general"    # salary | advance | expense | general


def detect_owner_command(message: str) -> OwnerCommand | None:
    """Try to extract a financial command from the owner's message."""
    for pat in _OWNER_SEND_MONEY_PATTERNS:
        m = pat.search(message)
        if not m:
            continue
        name = m.group(1).strip()
        # Determine amount and type
        groups = m.groups()
        amount = None
        tx_type = "general"
        if len(groups) >= 2:
            maybe_amount = _parse_bangla_number(groups[1])
            if maybe_amount and maybe_amount > 0:
                amount = maybe_amount
                tx_type = "advance"
            else:
                # second group is a text category (খাবার, ভাড়া, etc.)
                cat = groups[1].strip().lower()
                if any(k in cat for k in ("স্যালারি", "বেতন", "salary")):
                    tx_type = "salary"
                elif any(k in cat for k in ("খাবার", "food", "ভাড়া", "conveyance", "transport")):
                    tx_type = "expense"
                else:
                    tx_type = "advance"
        # Check for salary keyword in full message
        if "স্যালারি" in message or "বেতন" in message or "salary" in message.lower():
            tx_type = "salary"
        return OwnerCommand(employee_name=name, amount=amount, tx_type=tx_type)
    return None


# ═══════════════════════════════════════════════════════════
# STEP 6 — WBOM HTTP helpers
# ═══════════════════════════════════════════════════════════

async def _wbom_employee_message(wbom_url: str, phone: str, message: str) -> str | None:
    """POST /self-service/message — employee self-service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{wbom_url}/self-service/message",
                json={"sender_number": phone, "message_body": message},
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("recognized"):
                    return data.get("response", "")
    except Exception as exc:
        logger.warning(f"WBOM self-service failed: {exc}")
    return None


async def _wbom_search_employee(wbom_url: str, query: str) -> dict | None:
    """GET /employees/search/{query} — find employee by name."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(f"{wbom_url}/employees/search/{query}", params={"limit": 1})
            if r.status_code == 200:
                rows = r.json()
                if rows:
                    return rows[0]
    except Exception as exc:
        logger.warning(f"WBOM employee search failed: {exc}")
    return None


async def _wbom_employee_transactions(wbom_url: str, employee_id: int) -> list[dict]:
    """GET /transactions/by-employee/{id} — transaction history."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(f"{wbom_url}/transactions/by-employee/{employee_id}")
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        logger.warning(f"WBOM transactions fetch failed: {exc}")
    return []


async def _wbom_initiate_payment(
    wbom_url: str,
    employee_id: int,
    amount: float,
    tx_type: str = "Advance",
    payment_method: str = "Bkash",
    source: str = "whatsapp",
    idempotency_key: str | None = None,
) -> dict | None:
    """POST /payment/initiate — stage a payment for approval."""
    import uuid as _uuid
    idem_key = idempotency_key or f"owner-{_uuid.uuid4().hex[:16]}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                f"{wbom_url}/payment/initiate",
                json={
                    "employee_id": employee_id,
                    "amount": str(amount),
                    "transaction_type": tx_type,
                    "payment_method": payment_method,
                    "source": source,
                    "idempotency_key": idem_key,
                },
            )
            if r.status_code in (200, 201):
                return r.json()
    except Exception as exc:
        logger.warning(f"WBOM initiate payment failed: {exc}")
    return None


async def _wbom_approve_and_execute(
    wbom_url: str, staging_id: int, approved_by: str = "owner",
) -> dict | None:
    """Approve then execute a staged payment in two calls."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            # Step 1: approve
            r1 = await c.post(
                f"{wbom_url}/payment/approve",
                json={"staging_id": staging_id, "approved_by": approved_by},
            )
            if r1.status_code != 200:
                logger.warning("Approve failed: %s", r1.text)
                return None
            # Step 2: execute
            r2 = await c.post(
                f"{wbom_url}/payment/execute/{staging_id}",
                params={"executed_by": approved_by},
            )
            if r2.status_code == 200:
                return r2.json()
    except Exception as exc:
        logger.warning(f"WBOM approve+execute failed: {exc}")
    return None


async def _wbom_salary_report(wbom_url: str, employee_id: int, month: int, year: int) -> dict | None:
    """GET /reports/salary/{employee_id}/{month}/{year}."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(f"{wbom_url}/reports/salary/{employee_id}/{month}/{year}")
            if r.status_code == 200:
                return r.json()
    except Exception as exc:
        logger.warning(f"WBOM salary report failed: {exc}")
    return None


# ═══════════════════════════════════════════════════════════
# STEP 9 — Response Formatter
# ═══════════════════════════════════════════════════════════

def format_response(raw: str) -> str:
    """Clean and normalise any outgoing reply."""
    if not raw or not raw.strip():
        return _DATA_PROCESSED_BN
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return "\n".join(lines)


def _build_owner_draft(
    emp: dict, cmd: OwnerCommand, salary_report: dict | None,
) -> str:
    """Build a human-readable confirmation draft for the owner."""
    name = emp.get("employee_name", cmd.employee_name)
    eid = emp.get("employee_id", "?")
    designation = emp.get("designation", "")
    basic = emp.get("basic_salary") or 0

    parts: list[str] = [f"👤 {name} ({designation}) — ID #{eid}"]

    if salary_report:
        net = salary_report.get("net_salary") or salary_report.get("salary_summary", {}).get("net_salary") or 0
        paid = salary_report.get("total_paid") or 0
        due = float(net) - float(paid) if net else 0
        parts.append(f"💰 পাওনা: ৳{due:,.0f} (নেট: ৳{float(net):,.0f}, পেয়েছে: ৳{float(paid):,.0f})")
    else:
        parts.append(f"💰 বেসিক: ৳{float(basic):,.0f}")

    if cmd.amount:
        parts.append(f"📤 আপনি পাঠাতে চান: ৳{cmd.amount:,.0f} ({cmd.tx_type})")
    else:
        parts.append(f"📤 পুরো বেতন পাঠাতে চান ({cmd.tx_type})")

    parts.append("")
    parts.append("নিশ্চিত করবেন? (হ্যাঁ / সম্পাদনা / বাতিল)")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
# Owner pending-action state (Redis-backed)
# ═══════════════════════════════════════════════════════════

_OWNER_PENDING_TTL = 1800  # 30 min (spec requirement)


def _store_owner_pending(user_id: str, data: dict):
    r = _get_redis()
    r.setex(f"ctrl:owner_pending:{user_id}", _OWNER_PENDING_TTL, json.dumps(data, default=str))


def _get_owner_pending(user_id: str) -> dict | None:
    r = _get_redis()
    raw = r.get(f"ctrl:owner_pending:{user_id}")
    if raw:
        return json.loads(raw)
    return None


def _clear_owner_pending(user_id: str):
    r = _get_redis()
    r.delete(f"ctrl:owner_pending:{user_id}")


# ═══════════════════════════════════════════════════════════
# MASTER PIPELINE — process_message()
# ═══════════════════════════════════════════════════════════

async def process_message(
    msg: IncomingMessage,
    *,
    wbom_url: str,
    intent_fn,       # process_social_intent_scored(message, conv_id, role)
    lead_capture_fn,  # try_capture_lead(message, intent, conv_id, reply)
) -> ControlResult:
    """
    Unified control layer entry-point.

    Parameters
    ----------
    msg : IncomingMessage
        Normalised incoming message.
    wbom_url : str
        Base URL for WBOM service.
    intent_fn : callable
        ``process_social_intent_scored(message, conv_id, sender_role)``
    lead_capture_fn : callable
        ``try_capture_lead(message, intent, conv_id, reply)``
    """

    # ── STEP 2: Rate limit ──
    if _check_rate_limit(msg.user_id):
        return ControlResult(
            reply=_RATE_LIMIT_BN, intent="rate_limited",
            route="rate_limit", status="fallback",
            sender_role=msg.sender_role,
        )

    # ── STEP 3: Context memory ──
    _push_context(msg.user_id, msg.message)
    recent = _get_context(msg.user_id)

    # ── STEP 5: Role-based routing ──

    # ---- OWNER ROUTE ----
    if msg.sender_role == "owner":
        return await _handle_owner(msg, wbom_url=wbom_url, recent=recent)

    # ---- EMPLOYEE ROUTE ----
    if msg.sender_role == "employee":
        return await _handle_employee(msg, wbom_url=wbom_url, intent_fn=intent_fn)

    # ---- CLIENT ROUTE ----
    if msg.sender_role == "client":
        return await _handle_client(msg, intent_fn=intent_fn)

    # ---- JOB SEEKER ROUTE ----
    if msg.sender_role == "job_seeker":
        return await _handle_job_seeker(msg, intent_fn=intent_fn, lead_capture_fn=lead_capture_fn)

    # ---- UNKNOWN / DEFAULT ----
    return await _handle_social_unknown(msg, intent_fn=intent_fn, lead_capture_fn=lead_capture_fn)


# ═══════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════

async def _handle_owner(
    msg: IncomingMessage, *, wbom_url: str, recent: list[str],
) -> ControlResult:
    """Owner command engine — draft → approve → execute."""

    norm = msg.message.strip().lower()

    # ── Check for pending action confirmation ──
    pending = _get_owner_pending(msg.user_id)
    if pending:
        if norm in ("হ্যাঁ", "yes", "ok", "confirm", "approve", "ঠিক আছে"):
            # APPROVE → execute transaction
            result = await _execute_owner_pending(pending, wbom_url)
            _clear_owner_pending(msg.user_id)
            return result
        elif norm in ("বাতিল", "cancel", "না", "no"):
            _clear_owner_pending(msg.user_id)
            return ControlResult(
                reply="বাতিল করা হয়েছে।",
                intent="owner_cancel", route="owner_command",
                status="success", sender_role="owner",
            )
        elif norm in ("সম্পাদনা", "edit", "change"):
            _clear_owner_pending(msg.user_id)
            return ControlResult(
                reply="নতুন নির্দেশনা দিন। (যেমন: 'করিমকে ২০০০ টাকা পাঠাও')",
                intent="owner_edit", route="owner_command",
                status="success", sender_role="owner",
            )

    # ── Try to detect financial command ──
    cmd = detect_owner_command(msg.message)
    if cmd:
        return await _handle_owner_financial(msg, cmd, wbom_url)

    # ── Not a financial command → pass through to existing owner endpoint ──
    # Return None-like result so caller knows to delegate
    return ControlResult(
        reply="", intent="owner_passthrough", route="owner_passthrough",
        status="success", sender_role="owner",
    )


async def _handle_owner_financial(
    msg: IncomingMessage, cmd: OwnerCommand, wbom_url: str,
) -> ControlResult:
    """Owner financial command: search employee → build draft → await confirm."""
    # 1. Search employee in WBOM
    emp = await _wbom_search_employee(wbom_url, cmd.employee_name)
    if not emp:
        return ControlResult(
            reply=f"'{cmd.employee_name}' নামে কোনো কর্মী পাওয়া যায়নি। নাম ঠিক আছে?",
            intent="owner_employee_not_found", route="owner_command",
            status="fallback", sender_role="owner",
        )

    employee_id = emp["employee_id"]

    # 2. Fetch salary report for current month
    now = datetime.now()
    salary_report = await _wbom_salary_report(wbom_url, employee_id, now.month, now.year)

    # 3. Build confirmation draft
    draft = _build_owner_draft(emp, cmd, salary_report)

    # 4. Store pending action
    _store_owner_pending(msg.user_id, {
        "employee_id": employee_id,
        "employee_name": emp.get("employee_name", cmd.employee_name),
        "amount": cmd.amount,
        "tx_type": cmd.tx_type,
        "draft": draft,
    })

    return ControlResult(
        reply=draft, intent="owner_financial_draft",
        route="owner_command", status="success",
        sender_role="owner", needs_confirmation=True,
        draft=draft,
    )


async def _execute_owner_pending(pending: dict, wbom_url: str) -> ControlResult:
    """Execute a confirmed owner financial command via WBOM staging flow.
    Flow: initiate (stage) → approve → execute (creates real transaction)."""
    employee_id = pending["employee_id"]
    name = pending["employee_name"]
    amount = pending.get("amount")
    tx_type = pending.get("tx_type", "Advance")

    # Map tx_type to WBOM transaction_type enum
    wbom_type_map = {
        "salary": "Salary",
        "advance": "Advance",
        "expense": "Other",
        "general": "Advance",
    }
    wbom_type = wbom_type_map.get(tx_type, "Advance")

    if not amount or amount <= 0:
        return ControlResult(
            reply=f"{name}-এর জন্য নির্দিষ্ট পরিমাণ উল্লেখ করুন। (যেমন: '{name}কে ৫০০০ টাকা পাঠাও')",
            intent="owner_amount_needed", route="owner_command",
            status="fallback", sender_role="owner",
        )

    # Step 1: Initiate (creates staging payment with idempotency)
    staged = await _wbom_initiate_payment(
        wbom_url, employee_id, amount,
        tx_type=wbom_type, source="whatsapp",
    )
    if not staged:
        return ControlResult(
            reply=f"❌ {name}-এর পেমেন্ট স্টেজ করা যায়নি। আবার চেষ্টা করুন।",
            intent="owner_staging_failed", route="owner_command",
            status="error", sender_role="owner",
        )

    staging_id = staged.get("staging_id")

    # Step 2+3: Approve + Execute in one go (owner is approver)
    result = await _wbom_approve_and_execute(wbom_url, staging_id, approved_by="owner")
    if result and result.get("status") in ("executed", "duplicate"):
        tx_id = result.get("transaction_id", "?")
        return ControlResult(
            reply=f"✅ {name}-কে ৳{amount:,.0f} ({tx_type}) পাঠানো হয়েছে।\nTransaction #{tx_id}",
            intent="owner_transaction_done", route="owner_command",
            status="success", sender_role="owner",
        )

    return ControlResult(
        reply=f"❌ {name}-এর লেনদেন প্রক্রিয়া ব্যর্থ। আবার চেষ্টা করুন।",
        intent="owner_transaction_failed", route="owner_command",
        status="error", sender_role="owner",
    )


# ──────────────────────────────────────────────────────────
# EMPLOYEE route
# ──────────────────────────────────────────────────────────

async def _handle_employee(
    msg: IncomingMessage, *, wbom_url: str, intent_fn,
) -> ControlResult:
    """Employee → intent engine → if WBOM route, call WBOM; else return intent reply."""
    result = intent_fn(msg.message, msg.conversation_id, msg.sender_role)

    if result.route == "wbom_employee_message" and msg.phone:
        wbom_reply = await _wbom_employee_message(wbom_url, msg.phone, msg.message)
        if wbom_reply:
            reply = format_response(wbom_reply)
        else:
            reply = _WBOM_ERROR_BN
    elif result.route != "ai_fallback" or result.confidence >= 0.40:
        reply = result.reply or _CLARIFY_BN
    else:
        reply = result.reply or _CLARIFY_BN

    # Multi-intent hint
    if result.secondary_intents and result.needs_clarification:
        topics = ", ".join(result.secondary_intents[:3])
        reply += f"\n\n(আপনি কি {topics} — কোনটি সম্পর্কে জানতে চাচ্ছেন?)"

    return ControlResult(
        reply=format_response(reply),
        intent=result.intent, confidence=result.confidence,
        route=result.route, status="success",
        sender_role=msg.sender_role,
        secondary_intents=result.secondary_intents,
        needs_clarification=result.needs_clarification,
        reason=result.reason,
    )


# ──────────────────────────────────────────────────────────
# CLIENT route
# ──────────────────────────────────────────────────────────

async def _handle_client(
    msg: IncomingMessage, *, intent_fn,
) -> ControlResult:
    """Client → intent engine only. No DB writes from client route."""
    result = intent_fn(msg.message, msg.conversation_id, msg.sender_role)
    reply = result.reply or _CLARIFY_BN

    if result.needs_clarification and result.secondary_intents:
        topics = ", ".join(result.secondary_intents[:3])
        reply += f"\n\n(আপনি কি {topics} — কোনটি সম্পর্কে জানতে চাচ্ছেন?)"

    return ControlResult(
        reply=format_response(reply),
        intent=result.intent, confidence=result.confidence,
        route="client_reply", status="success",
        sender_role=msg.sender_role,
        secondary_intents=result.secondary_intents,
        needs_clarification=result.needs_clarification,
        reason=result.reason,
    )


# ──────────────────────────────────────────────────────────
# JOB SEEKER route
# ──────────────────────────────────────────────────────────

async def _handle_job_seeker(
    msg: IncomingMessage, *, intent_fn, lead_capture_fn,
) -> ControlResult:
    """Job seeker → intent engine → lead capture pipeline."""
    result = intent_fn(msg.message, msg.conversation_id, msg.sender_role)
    reply = result.reply or _CLARIFY_BN

    # Lead capture: collect name, NID, experience, etc.
    if lead_capture_fn:
        reply = await lead_capture_fn(
            msg.message, result.intent, msg.conversation_id, reply,
        )

    if result.needs_clarification and result.secondary_intents:
        topics = ", ".join(result.secondary_intents[:3])
        reply += f"\n\n(আপনি কি {topics} — কোনটি সম্পর্কে জানতে চাচ্ছেন?)"

    return ControlResult(
        reply=format_response(reply),
        intent=result.intent, confidence=result.confidence,
        route="job_seeker_reply", status="success",
        sender_role=msg.sender_role,
        secondary_intents=result.secondary_intents,
        needs_clarification=result.needs_clarification,
        reason=result.reason,
    )


# ──────────────────────────────────────────────────────────
# SOCIAL UNKNOWN route
# ──────────────────────────────────────────────────────────

async def _handle_social_unknown(
    msg: IncomingMessage, *, intent_fn, lead_capture_fn,
) -> ControlResult:
    """Unknown role — intent engine + safe fallback. Never LLM."""
    result = intent_fn(msg.message, msg.conversation_id, msg.sender_role)

    if result.route != "ai_fallback" or result.confidence >= 0.40:
        reply = result.reply or _CLARIFY_BN
    else:
        reply = result.reply or _CLARIFY_BN

    # Lead capture for potential job seekers
    if lead_capture_fn and result.intent and result.intent.startswith("job_"):
        reply = await lead_capture_fn(
            msg.message, result.intent, msg.conversation_id, reply,
        )

    if result.needs_clarification and result.secondary_intents:
        topics = ", ".join(result.secondary_intents[:3])
        reply += f"\n\n(আপনি কি {topics} — কোনটি সম্পর্কে জানতে চাচ্ছেন?)"

    return ControlResult(
        reply=format_response(reply),
        intent=result.intent, confidence=result.confidence,
        route=result.route if result.route != "ai_fallback" else "safe_fallback",
        status="success" if result.confidence >= 0.40 else "fallback",
        sender_role=msg.sender_role,
        secondary_intents=result.secondary_intents,
        needs_clarification=result.needs_clarification,
        reason=result.reason,
    )


# ═══════════════════════════════════════════════════════════
# STEP 10 — Structured logging helper
# ═══════════════════════════════════════════════════════════

def log_result(msg: IncomingMessage, result: ControlResult):
    """Emit a single structured JSON log line per message."""
    logger.info(json.dumps({
        "event": "message_processed",
        "user_id": msg.user_id,
        "role": msg.sender_role,
        "intent": result.intent,
        "confidence": round(result.confidence, 2),
        "route": result.route,
        "status": result.status,
        "needs_clarification": result.needs_clarification,
        "reply_len": len(result.reply),
    }, ensure_ascii=False))
