# ============================================================
# Fazle Brain — Knowledge Context Builder
# Fetches structured knowledge from API for prompt injection
# Includes text normalization, multi-intent detection, and
# conversation knowledge for intelligent reply generation.
# ============================================================
import logging
import time as _time
import httpx
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger("fazle-brain.context")

# API base URL — same network, internal call
_API_URL = "http://fazle-api:8100"

# ── Phase 4: Simple in-memory cache (TTL 120s) ──────────────
_CACHE: dict[str, tuple[str, float]] = {}  # key -> (reply, timestamp)
_CACHE_TTL = 120  # seconds
_MAX_CACHE = 200


def get_cached_context(key: str) -> Optional[str]:
    """Return cached context if still fresh."""
    entry = _CACHE.get(key)
    if entry and (_time.monotonic() - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def set_cached_context(key: str, value: str) -> None:
    """Cache a context value. Evict oldest if full."""
    if len(_CACHE) >= _MAX_CACHE:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][1])
        _CACHE.pop(oldest, None)
    _CACHE[key] = (value, _time.monotonic())

# ── Bangla fallback reply when no knowledge context found ────
KNOWLEDGE_FALLBACK_BN = "আপনি কি চাকরি, সিকিউরিটি সার্ভিস, নাকি অন্য কোনো বিষয়ে জানতে চাচ্ছেন?"


# ── Phase 1: Text Normalization ──────────────────────────────

_NORM_MAP = {
    "beton": "বেতন",
    "salary": "বেতন",
    "pay": "বেতন",
    "chakri": "চাকরি",
    "job": "চাকরি",
    "guard": "গার্ড",
    "security": "সিকিউরিটি",
    "problem": "অভিযোগ",
    "complain": "অভিযোগ",
    "complaint": "অভিযোগ",
    "replace": "রিপ্লেসমেন্ট",
    "bill": "বিল",
    "billing": "বিল",
    "emergency": "জরুরি",
    "urgent": "জরুরি",
    "training": "প্রশিক্ষণ",
    "monitor": "মনিটরিং",
    "contract": "চুক্তি",
    "service": "সার্ভিস",
    "lagbe": "লাগবে",
    "lagbe?": "লাগবে",
    "needed": "লাগবে",
    "need": "লাগবে",
    "hello": "হ্যালো",
    "hi ": "হ্যালো ",
    "ache": "আছে",
    "ache?": "আছে",
    "koto": "কত",
    "koto?": "কত",
    "office": "অফিস",
    "kothay": "কোথায়",
    "where": "কোথায়",
    "address": "ঠিকানা",
    "location": "লোকেশন",
    "rate": "রেট",
    "price": "দাম",
    "cost": "খরচ",
    "apnar": "আপনার",
    "apnader": "আপনাদের",
    "ki": "কি",
    "ase": "আছে",
    "chai": "চাই",
    "dorkar": "দরকার",
    "jante": "জানতে",
    "bolun": "বলুন",
    "thik": "ঠিক",
    "ha": "হ্যাঁ",
    "hae": "হ্যাঁ",
    "ji": "জি",
    "pore": "পরে",
    "dhonnobad": "ধন্যবাদ",
    "company": "কোম্পানি",
    "bochor": "বছর",
    "bochhor": "বছর",
    "year": "বছর",
    "event": "ইভেন্ট",
    "factory": "ফ্যাক্টরি",
    "korte": "করতে",
    "pathao": "পাঠান",
    "send": "পাঠান",
    "somossa": "সমস্যা",
    "problem": "সমস্যা",
    "ovijog": "অভিযোগ",
    "bill": "বিল",
    "report": "রিপোর্ট",
    "visit": "ভিজিট",
    "cancel": "বাতিল",
    "renew": "নবায়ন",
    "quotation": "কোটেশন",
    # ── New: Job FAQ keywords ──
    "experience": "অভিজ্ঞতা",
    "ovigota": "অভিজ্ঞতা",
    "fresher": "ফ্রেশার",
    "fresh": "ফ্রেশার",
    "notun": "নতুন",
    "new": "নতুন",
    "certificate": "সার্টিফিকেট",
    "education": "শিক্ষা",
    "porasona": "পড়াশোনা",
    "lekhapora": "পড়াশোনা",
    "ssc": "এসএসসি",
    "apply": "আবেদন",
    "abedon": "আবেদন",
    "joining": "জয়েনিং",
    "join": "জয়েনিং",
    "fee": "ফি",
    "deposit": "ডিপোজিট",
    "resign": "রিজাইন",
    "chharte": "ছাড়তে",
    "leave": "ছুটি",
    "chutti": "ছুটি",
    "off day": "অফ ডে",
    "duty": "ডিউটি",
    "shift": "শিফট",
    "hour": "ঘণ্টা",
    "ghonta": "ঘণ্টা",
    "overtime": "ওভারটাইম",
    "release": "রিলিজ",
    "slip": "স্লিপ",
    "bkash": "বিকাশ",
    "nagad": "নগদ",
    # ── New: Marine / Vessel keywords ──
    "vessel": "ভেসেল",
    "jahaj": "জাহাজ",
    "jahaaj": "জাহাজ",
    "ship": "জাহাজ",
    "jetty": "জেটি",
    "marine": "মেরিন",
    "escort": "এসকর্ট",
    "cargo": "কার্গো",
    "lighterage": "লাইটারেজ",
    "port": "পোর্ট",
    # ── New: VIP keywords ──
    "vip": "ভিআইপি",
    "bodyguard": "বডিগার্ড",
    "personal": "পার্সোনাল",
    "executive": "এক্সিকিউটিভ",
    # ── New: Specific service keywords ──
    "garments": "গার্মেন্টস",
    "mall": "মল",
    "construction": "নির্মাণ",
    "warehouse": "গুদামঘর",
    "cctv": "সিসিটিভি",
    # ── New: Complaint sub-type keywords ──
    "ghumay": "ঘুমায়",
    "phone e thake": "ফোনে",
    "absent": "অনুপস্থিত",
    "lazy": "অলস",
    "rude": "রূঢ়",
    "jhogra": "ঝগড়া",
    "churi": "চুরি",
    "theft": "চুরি",
    "suspicious": "সন্দেহজনক",
    # ── New: Contract keywords ──
    "renewal": "নবায়ন",
    "cancellation": "বাতিল",
    "supervisor": "সুপারভাইজার",
    # ── Others ──
    "vacancy": "ভ্যাকেন্সি",
    "niyog": "নিয়োগ",
    "kaj": "কাজ",
    "thaka": "থাকা",
    "khaowa": "খাওয়া",
    "website": "ওয়েবসাইট",
    "facebook": "ফেসবুক",
    "phone": "ফোন",
    "call": "কল",
}


def normalize_text(text: str) -> str:
    """Normalize mixed English/Bangla text for intent matching."""
    text = text.lower().strip()
    for eng, bn in _NORM_MAP.items():
        text = text.replace(eng, bn)
    return text


# ── Phase 2: Multi-Intent Detection ─────────────────────────

def detect_intents(message: str) -> list[str]:
    """Detect one or more intents from a user message.

    Returns a list of intent strings that map to knowledge subcategories.
    """
    msg = normalize_text(message)

    intents = []

    if any(w in msg for w in ["চাকরি", "নিয়োগ", "আবেদন", "vacancy", "apply", "ভ্যাকেন্সি", "কাজ"]):
        intents.append("job_seeker")

    if any(w in msg for w in ["অভিজ্ঞতা", "ফ্রেশার", "নতুন", "সার্টিফিকেট", "পড়াশোনা", "শিক্ষা"]):
        intents.append("job_seeker")

    if any(w in msg for w in ["জয়েনিং", "ফি", "জামানত", "ডিপোজিট"]):
        intents.append("job_seeker")

    if any(w in msg for w in ["রিজাইন", "ছাড়তে", "ছুটি", "অফ ডে"]):
        intents.append("job_seeker")

    if any(w in msg for w in ["ডিউটি", "শিফট", "রিলিজ", "ডিউটি স্লিপ"]):
        intents.append("job_seeker")

    if any(w in msg for w in ["গার্ড", "সিকিউরিটি", "সার্ভিস", "নিরাপত্তা"]):
        intents.append("client_service")

    if any(w in msg for w in ["ফ্যাক্টরি", "কারখানা", "গার্মেন্টস", "মল", "নির্মাণ"]):
        intents.append("client_service")

    if any(w in msg for w in ["মেরিন", "জেটি", "ভেসেল", "জাহাজ", "লাইটারেজ", "কার্গো", "এসকর্ট"]):
        intents.append("client_service")

    if any(w in msg for w in ["ইভেন্ট", "অনুষ্ঠান", "বিবাহ", "কনসার্ট"]):
        intents.append("client_service")

    if any(w in msg for w in ["ভিআইপি", "বডিগার্ড", "পার্সোনাল", "এক্সিকিউটিভ"]):
        intents.append("client_service")

    if any(w in msg for w in ["অভিযোগ", "সমস্যা", "অনুপস্থিত", "অলস", "চুরি", "রূঢ়", "ঝগড়া", "সন্দেহজনক"]):
        intents.append("complaint")

    if any(w in msg for w in ["বেতন", "টাকা", "মাসিক", "বেতন কত"]):
        intents.append("salary")

    if any(w in msg for w in ["জরুরি", "বিপদ", "attack", "threat", "danger"]):
        intents.append("emergency")

    if any(w in msg for w in ["রিপ্লেসমেন্ট", "পরিবর্তন", "বদলি", "change guard"]):
        intents.append("replacement")

    if any(w in msg for w in ["বিল", "পেমেন্ট", "invoice", "payment"]):
        intents.append("billing")

    if any(w in msg for w in ["চুক্তি", "নবায়ন", "বাতিল", "renewal", "cancel"]):
        intents.append("contract")

    if any(w in msg for w in ["প্রশিক্ষণ", "ট্রেনিং"]):
        intents.append("training")

    if any(w in msg for w in ["মনিটরিং", "রিপোর্ট", "তদারকি", "supervision"]):
        intents.append("monitoring")

    if any(w in msg for w in ["সুপারভাইজার", "ভিজিট"]):
        intents.append("supervisor")

    if not intents:
        intents.append("fallback")

    return intents


# ── Phase 3: Smart Knowledge Fetch (optimized: 2s timeout) ──

async def _fetch_knowledge(
    query: str,
    caller_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 3,
    api_url: Optional[str] = None,
) -> list[dict]:
    """Fetch knowledge entries from the API. Returns list of result dicts."""
    base = api_url or _API_URL
    params: dict = {"q": query[:100], "limit": limit}
    if category:
        params["category"] = category
    if caller_id:
        params["caller_id"] = caller_id
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base}/knowledge/search", params=params)
            results = resp.json().get("results", []) if resp.status_code == 200 else []
            logger.info(f"Knowledge fetch: q='{query[:40]}' cat={category} -> {len(results)} results")
            return results
    except Exception as e:
        logger.warning(f"Knowledge fetch failed for q={query[:40]}: {e}")
    return []


# ── Phase 4: Context Builder (Core Engine) ───────────────────

async def build_conversation_context(
    message: str,
    caller_id: Optional[str] = None,
    api_url: Optional[str] = None,
) -> str:
    """Build conversation knowledge context using intent detection.

    Searches the 'conversation' category for relevant knowledge entries
    based on detected intents. Returns concise context for LLM injection.
    Optimized: single intent, max 2 direct + 2 intent results, cap 300 chars.
    """
    base = api_url or _API_URL
    seen_keys: set[str] = set()
    context_parts: list[str] = []

    # 1. Direct search — use normalized (Bangla) text to match DB entries
    normalized = normalize_text(message)
    direct_results = await _fetch_knowledge(
        normalized, caller_id=caller_id, category="conversation",
        limit=2, api_url=base,
    )
    for item in direct_results[:2]:
        k = item.get("key", "")
        if k not in seen_keys:
            seen_keys.add(k)
            context_parts.append(item["value"])

    # 2. Single-intent search (Phase 2: only first intent)
    intents = detect_intents(message)[:1]
    for intent in intents:
        if intent == "fallback":
            continue
        intent_results = await _fetch_knowledge(
            intent, caller_id=caller_id, category="conversation",
            limit=2, api_url=base,
        )
        for item in intent_results[:2]:
            k = item.get("key", "")
            if k not in seen_keys:
                seen_keys.add(k)
                context_parts.append(item["value"])

    # Cap at 4 entries, max 300 chars total
    result = "\n".join(context_parts[:4])
    if len(result) > 300:
        result = result[:300].rsplit("।", 1)[0] + "।"
    return result


# ── Original personal/business knowledge fetch (preserved) ───

async def build_knowledge_context(
    message: str,
    caller_id: Optional[str] = None,
    caller_role: Optional[str] = None,
    api_url: Optional[str] = None,
) -> str:
    """Fetch knowledge context from the API service.

    Searches personal/business categories (access-controlled) AND
    conversation category (public, intent-based).
    Returns a context string to inject into the system prompt.
    Optimized: cached, max 300 chars, single API call per category.
    """
    # Phase 4: Check cache first
    cache_key = f"{normalize_text(message)[:60]}:{caller_role}"
    cached = get_cached_context(cache_key)
    if cached is not None:
        logger.info(f"Knowledge context from cache: {len(cached)} chars")
        return cached

    base = api_url or _API_URL
    msg_lower = message.lower()

    context_parts = []

    # ── Conversation knowledge (always searched) ─────────
    try:
        conv_ctx = await build_conversation_context(
            message, caller_id=caller_id, api_url=base,
        )
        if conv_ctx:
            context_parts.append("\n--- CONVERSATION KNOWLEDGE ---")
            context_parts.append(conv_ctx)
            context_parts.append("--- END CONVERSATION KNOWLEDGE ---")
    except Exception as e:
        logger.warning(f"Conversation context skipped: {e}")

    # ── Personal / Business knowledge (only if triggered) ─
    personal_triggers = [
        "nid", "passport", "জাতীয় পরিচয়", "পাসপোর্ট", "birthday",
        "জন্মদিন", "blood", "রক্ত", "address", "ঠিকানা",
        "father", "mother", "বাবা", "মা", "wife", "স্ত্রী",
        "name", "নাম", "born", "জন্ম",
    ]
    business_triggers = [
        "company", "business", "কোম্পানি", "tin", "টিন",
        "bank", "ব্যাংক", "account", "একাউন্ট", "al-aqsa",
        "security", "logistics", "guard", "গার্ড",
    ]

    category = None
    if any(t in msg_lower for t in personal_triggers):
        category = "personal"
    elif any(t in msg_lower for t in business_triggers):
        category = "business"

    if category:
        try:
            results = await _fetch_knowledge(
                normalize_text(message)[:100], caller_id=caller_id,
                category=category, limit=3, api_url=base,
            )
            if results:
                label = category.upper()
                context_parts.append(f"\n--- {label} DATA ---")
                for r in results[:2]:
                    context_parts.append(f"  {r['key']}: {r['value']}")
                context_parts.append(f"--- END {label} DATA ---")
        except Exception as e:
            logger.warning(f"Knowledge context fetch failed: {e}")

    result = "\n".join(context_parts) if context_parts else ""

    # Phase 4: Store in cache
    set_cached_context(cache_key, result)
    return result


async def lookup_user_context(phone: str, api_url: Optional[str] = None) -> Optional[dict]:
    """Lookup a knowledge user by phone for caller identification."""
    base = api_url or _API_URL
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base}/knowledge/user/{phone}")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.debug(f"User lookup failed for {phone}: {e}")
    return None
