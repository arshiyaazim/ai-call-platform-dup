# ============================================================
# Response Playbooks + Confusion Handling Engine
# Role-based reply policies and structured escalation ladders
# ============================================================
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import redis

logger = logging.getLogger("fazle-brain.playbooks")

_REDIS_URL = os.getenv("REDIS_URL", "redis://:redissecret@redis:6379/1")

_CONFUSION_PREFIX = "fazle:confusion:"
_CONFUSION_TTL = 3600  # 1 hour per conversation confusion state


# ── Role-based Response Playbooks ────────────────────────────

@dataclass(frozen=True)
class Playbook:
    role: str
    tone: str
    max_reply_length: int  # chars
    language_default: str
    greeting_style: str
    escalation_threshold: int  # confusion count before escalate
    allowed_topics: tuple[str, ...]
    restricted_topics: tuple[str, ...]
    reply_rules: str  # injected into system prompt


PLAYBOOKS: dict[str, Playbook] = {
    "client": Playbook(
        role="client",
        tone="professional, respectful, Bangla-first with আপনি form",
        max_reply_length=300,
        language_default="bn",
        greeting_style="আসসালামু আলাইকুম, কিভাবে সাহায্য করতে পারি?",
        escalation_threshold=3,
        allowed_topics=(
            "services", "pricing", "security_guard", "manpower",
            "survey_scout", "office_location", "contact_info",
            "job_application", "qualification",
        ),
        restricted_topics=(
            "internal_operations", "employee_salary", "owner_personal",
            "financial_details", "competitor_info",
        ),
        reply_rules="""CLIENT REPLY RULES (MANDATORY):
- Be concise: max 2-3 sentences per reply
- Answer service questions directly with specific details
- For pricing: give ranges or say "অফিসে যোগাযোগ করুন বিস্তারিত জানতে"
- Qualify leads: collect name, phone, interest, location naturally
- Push toward WhatsApp contact or office visit for conversion
- Never discuss internal operations, employee salaries, or financials
- If confused about what they want: ask ONE clarifying question
- Bangla-first. Switch to English only if they write in English.""",
    ),

    "job_seeker": Playbook(
        role="job_seeker",
        tone="helpful but structured, screening-focused",
        max_reply_length=400,
        language_default="bn",
        greeting_style="আসসালামু আলাইকুম। আল-আকসায় স্বাগতম। কোন পদে আগ্রহী?",
        escalation_threshold=3,
        allowed_topics=(
            "job_vacancies", "qualification", "salary_range",
            "application_process", "office_location", "training",
            "work_schedule", "categories",
        ),
        restricted_topics=(
            "exact_salary_of_others", "internal_politics",
            "owner_personal", "financial_details",
        ),
        reply_rules="""JOB SEEKER REPLY RULES (MANDATORY):
- Screen systematically: collect নাম (name), বয়স (age), শিক্ষাগত যোগ্যতা (qualification), অভিজ্ঞতা (experience)
- Available positions: Security Guard, Survey Scout, Supervisor, Office Staff, Driver, Helper
- Give clear next steps: "অফিসে আসুন CV নিয়ে" or "WhatsApp-এ CV পাঠান"
- Answer salary questions with ranges, not exact figures
- If they're qualified: express interest and invite to office
- If they're not qualified: be honest but gentle, suggest alternative positions
- Collect contact info for follow-up
- Never promise specific salary — say "অভিজ্ঞতা ও পদ অনুযায়ী বেতন নির্ধারণ হয়"
- Ask ONE question at a time during screening""",
    ),

    "employee": Playbook(
        role="employee",
        tone="direct, professional, authority-maintaining",
        max_reply_length=250,
        language_default="bn",
        greeting_style="হ্যাঁ, বলুন।",
        escalation_threshold=2,
        allowed_topics=(
            "work_schedule", "duty_assignment", "leave_request",
            "salary_query", "office_procedures", "training",
            "reporting", "complaint",
        ),
        restricted_topics=(
            "other_employee_salary", "owner_personal",
            "financial_details", "client_details", "business_strategy",
        ),
        reply_rules="""EMPLOYEE REPLY RULES (MANDATORY):
- Be direct and clear. No unnecessary pleasantries
- For duty/schedule queries: give specific answers
- For leave requests: note it and say "বসকে জানাচ্ছি" (flagging for owner)
- For salary queries: "বেতন সংক্রান্ত বিষয়ে অফিসে যোগাযোগ করুন"
- For complaints: listen, acknowledge, flag for owner review
- Maintain authority — you represent the boss
- Never share other employees' information
- If they ask something you can't answer: "এটা বসের সাথে কথা বলে জানাব"
- Flag unusual requests for owner review""",
    ),

    "family": Playbook(
        role="family",
        tone="warm, caring, relationship-aware",
        max_reply_length=500,
        language_default="mixed",
        greeting_style="কেমন আছেন?",
        escalation_threshold=5,
        allowed_topics=("personal", "family", "health", "plans", "memories", "support"),
        restricted_topics=("business_financials",),
        reply_rules="""FAMILY REPLY RULES (MANDATORY):
- Be warm, natural, and caring
- Match their language (Bangla/English/mixed)
- Remember personal details and reference them naturally
- For wife: loving, attentive, supportive tone
- For children: encouraging, patient, age-appropriate
- For parents: respectful, caring, attentive
- For siblings: casual, natural, brotherly
- Offer help proactively if they seem troubled
- Never be robotic or formal with family
- Keep conversation natural — no corporate speak""",
    ),

    "friend": Playbook(
        role="friend",
        tone="casual, warm, natural",
        max_reply_length=400,
        language_default="mixed",
        greeting_style="ভাই, কী খবর?",
        escalation_threshold=4,
        allowed_topics=("personal", "casual", "plans", "business_general"),
        restricted_topics=("business_financials", "employee_details"),
        reply_rules="""FRIEND REPLY RULES (MANDATORY):
- Be casual and natural — tui/tumi form
- Use humor when appropriate
- If they ask about business: answer generally, no financial details
- If they need help: be genuinely helpful
- Banter is welcome""",
    ),

    "unknown": Playbook(
        role="unknown",
        tone="polite, safe, discovery-mode",
        max_reply_length=200,
        language_default="bn",
        greeting_style="আসসালামু আলাইকুম। কিভাবে সাহায্য করতে পারি?",
        escalation_threshold=2,
        allowed_topics=(
            "services", "contact_info", "office_location",
            "general_inquiry",
        ),
        restricted_topics=(
            "internal_operations", "employee_details", "owner_personal",
            "financial_details", "pricing_details",
        ),
        reply_rules="""UNKNOWN CONTACT REPLY RULES (MANDATORY):
- Be polite but cautious — you don't know this person
- Provide basic service information only
- Try to identify their intent: client? job seeker? spam?
- Ask who they are and what they need
- If they seem like a client: warm up and help
- If they seem like a job seeker: direct to application process
- If suspicious or abusive: "ধন্যবাদ, অফিসে সরাসরি যোগাযোগ করুন" and disengage
- Do NOT share any internal information
- Do NOT discuss pricing until identity is clearer
- Max 1-2 sentences per reply until you understand who they are""",
    ),
}


# ── Confusion Handling ───────────────────────────────────────

@dataclass
class ConfusionState:
    count: int  # how many times confused in this conversation
    last_question: str  # last clarifying question asked
    escalated: bool  # whether already escalated to owner
    marked_for_review: bool


class ConfusionHandler:
    """Track and handle confusion per conversation with structured escalation."""

    def __init__(self, redis_url: str = None):
        self._redis_url = redis_url or _REDIS_URL
        self._redis: Optional[redis.Redis] = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _key(self, platform: str, sender_id: str) -> str:
        return f"{_CONFUSION_PREFIX}{platform}:{sender_id}"

    def get_state(self, platform: str, sender_id: str) -> ConfusionState:
        try:
            r = self._get_redis()
            raw = r.get(self._key(platform, sender_id))
            if raw:
                d = json.loads(raw)
                return ConfusionState(**d)
        except Exception:
            pass
        return ConfusionState(count=0, last_question="", escalated=False, marked_for_review=False)

    def _save_state(self, platform: str, sender_id: str, state: ConfusionState):
        try:
            r = self._get_redis()
            r.setex(
                self._key(platform, sender_id),
                _CONFUSION_TTL,
                json.dumps({
                    "count": state.count,
                    "last_question": state.last_question,
                    "escalated": state.escalated,
                    "marked_for_review": state.marked_for_review,
                }),
            )
        except Exception:
            pass

    def reset(self, platform: str, sender_id: str):
        try:
            self._get_redis().delete(self._key(platform, sender_id))
        except Exception:
            pass

    def handle_confusion(
        self, platform: str, sender_id: str, role: str, message: str,
    ) -> dict:
        """Handle a confused interaction. Returns action dict.

        Returns:
            {
                "action": "clarify" | "narrow" | "escalate" | "review",
                "prompt_addition": str,  # inject into system prompt
                "reply_override": str | None,  # forced reply if escalating
                "confusion_count": int,
            }
        """
        state = self.get_state(platform, sender_id)
        playbook = PLAYBOOKS.get(role, PLAYBOOKS["unknown"])
        threshold = playbook.escalation_threshold

        state.count += 1

        if state.count == 1:
            # First confusion: clarify politely
            state.last_question = message
            self._save_state(platform, sender_id, state)
            return {
                "action": "clarify",
                "prompt_addition": (
                    "\n--- CONFUSION HANDLING ---\n"
                    "The user's message is unclear. Ask ONE specific clarifying question.\n"
                    "Be polite. Don't repeat yourself. Ask about the specific part that's unclear.\n"
                    "Example: 'আপনি কি সিকিউরিটি গার্ডের কাজ সম্পর্কে জানতে চাইছেন?'\n"
                    "--- END CONFUSION HANDLING ---"
                ),
                "reply_override": None,
                "confusion_count": state.count,
            }

        elif state.count <= threshold:
            # Still within threshold: ask narrower follow-up
            self._save_state(platform, sender_id, state)
            return {
                "action": "narrow",
                "prompt_addition": (
                    "\n--- CONFUSION HANDLING (NARROWING) ---\n"
                    f"User has been unclear {state.count} times. Previous attempt to clarify didn't work.\n"
                    "This time, offer 2-3 SPECIFIC options for what they might want.\n"
                    "Example: 'আপনি কি (১) চাকরি খুঁজছেন, (২) সিকিউরিটি গার্ড ভাড়া নিতে চাইছেন, নাকি (৩) অন্য কিছু?'\n"
                    "Keep it SHORT. Bangla-first. No long explanations.\n"
                    "--- END CONFUSION HANDLING ---"
                ),
                "reply_override": None,
                "confusion_count": state.count,
            }

        elif not state.escalated:
            # Escalate to owner
            state.escalated = True
            self._save_state(platform, sender_id, state)

            if role == "employee":
                reply = "এই বিষয়ে বসের সাথে কথা বলে জানাচ্ছি। একটু অপেক্ষা করুন।"
            elif role == "client":
                reply = "আপনার প্রশ্নটা ঠিকমতো বুঝতে পারছি না। আমি আমার সিনিয়রকে জানাচ্ছি, শীঘ্রই যোগাযোগ করবেন। ধন্যবাদ।"
            elif role == "job_seeker":
                reply = "আপনার জিজ্ঞাসা ভালোভাবে বুঝতে পারছি না। অফিসে সরাসরি এসে কথা বললে ভালো হবে। ঠিকানা: ভিক্টোরিয়া গেইট, একে খান মোড়, পাহাড়তলী, চট্টগ্রাম।"
            elif role == "family":
                reply = "একটু ঠিকমতো বুঝতে পারছি না। আবার বলো?"
            else:
                reply = "দুঃখিত, আপনার কথা ভালোভাবে বুঝতে পারছি না। অফিসে যোগাযোগ করুন: 01958-122300"

            return {
                "action": "escalate",
                "prompt_addition": "",
                "reply_override": reply,
                "confusion_count": state.count,
            }

        else:
            # Already escalated, mark for review
            state.marked_for_review = True
            self._save_state(platform, sender_id, state)
            return {
                "action": "review",
                "prompt_addition": "",
                "reply_override": "ধন্যবাদ। আপনার বিষয়টি রিভিউতে আছে। শীঘ্রই যোগাযোগ করা হবে।",
                "confusion_count": state.count,
            }

    def is_confused(self, message: str, reply: str) -> bool:
        """Heuristic: detect if the AI reply indicates confusion.

        Checks for confusion markers in the AI's intended reply.
        """
        confusion_markers_bn = [
            "বুঝতে পারছি না", "ঠিকমতো বুঝতে", "আবার বলুন",
            "কী বলতে চাইছেন", "আরেকটু পরিষ্কার", "বুঝাতে পারবেন",
        ]
        confusion_markers_en = [
            "don't understand", "could you clarify",
            "not sure what you mean", "please explain",
            "can you rephrase",
        ]
        reply_lower = reply.lower()
        for marker in confusion_markers_bn + confusion_markers_en:
            if marker in reply_lower:
                return True

        # Also check if the message is nonsensical (very short random chars)
        if len(message.strip()) < 3 and not message.strip().isdigit():
            return True

        return False


def build_playbook_prompt(role: str) -> str:
    """Build the role-specific playbook prompt block for system prompt injection."""
    playbook = PLAYBOOKS.get(role, PLAYBOOKS["unknown"])
    return (
        f"\n━━━ RESPONSE PLAYBOOK [{role.upper()}] ━━━\n"
        f"TONE: {playbook.tone}\n"
        f"MAX LENGTH: {playbook.max_reply_length} chars\n"
        f"LANGUAGE: {playbook.language_default}\n"
        f"\n{playbook.reply_rules}\n"
        f"\nRESTRICTED TOPICS (NEVER discuss): {', '.join(playbook.restricted_topics)}\n"
        f"━━━ END PLAYBOOK ━━━"
    )


# ── Reply Safety Classifier ─────────────────────────────────

# Keywords that indicate the AI reply contains restricted/sensitive content
_RESTRICTED_KEYWORDS = (
    # Financial
    "টাকা পেয়েছ", "বেতন দিয়েছ", "advance", "payment details",
    "হিসাব", "ব্যালেন্স", "profit", "loss", "revenue", "expense",
    "লাভ", "ক্ষতি", "আয়", "ব্যয়",
    # Vessel / operational secrets
    "vessel name", "ship name", "জাহাজের নাম", "route details",
    "cargo details", "consignment", "lc number", "bl number",
    # Employee private data
    "employee salary", "কর্মীর বেতন", "nid number", "passport",
    "bank account", "ব্যাংক একাউন্ট",
    # Owner personal
    "owner personal", "বসের ব্যক্তিগত",
)

# Patterns that indicate the reply is safe to auto-send
_SAFE_PATTERNS = (
    # Job inquiry responses (from Auto_reply_sample.txt)
    "survey scout", "সার্ভে স্কট", "সিকিউরিটি গার্ড",
    "চাকরি", "job", "vacancy", "পদ", "নিয়োগ",
    "আবেদন", "application", "apply",
    "যোগ্যতা", "qualification", "experience", "অভিজ্ঞতা",
    "প্রশিক্ষণ", "training",
    "অফিসে আসুন", "অফিসে এসে",
    "cv পাঠান", "cv নিয়ে",
    # Salary ranges (public info, not private)
    "১২,০০০", "১৫,০০০", "১৮,০০০", "12,000", "15,000", "18,000",
    # Greetings / pleasantries
    "আসসালামু আলাইকুম", "ওয়ালাইকুম", "ধন্যবাদ", "স্বাগতম",
    "কিভাবে সাহায্য", "how can i help",
    # Office info (public)
    "ভিক্টোরিয়া গেইট", "পাহাড়তলী", "চট্টগ্রাম",
    "01958", "office",
    # Service inquiries
    "সিকিউরিটি সার্ভিস", "security service", "manpower",
    "guard", "গার্ড",
    # Complaints / general
    "অভিযোগ", "complaint", "সমস্যা",
    "বুঝতে পারছি না", "আবার বলুন",
)


def classify_reply_safety(message: str, reply: str, relation: str = "unknown") -> str:
    """Classify whether an AI-generated reply is safe to auto-send.

    Returns:
        "safe"       — reply can be sent automatically
        "restricted" — reply must be stored as draft for owner approval
    """
    reply_lower = reply.lower()
    msg_lower = message.lower()

    # Priority 1: Owner/family always gets auto-reply
    if relation in ("owner", "family"):
        return "safe"

    # Priority 2: Check for restricted content in the reply
    for kw in _RESTRICTED_KEYWORDS:
        if kw in reply_lower:
            logger.info(f"Reply classified RESTRICTED — matched '{kw}'")
            return "restricted"

    # Priority 3: Job seekers with safe content → auto-send
    if relation == "job_seeker":
        return "safe"

    # Priority 4: Known safe patterns in reply or message
    safe_score = 0
    for pat in _SAFE_PATTERNS:
        if pat in reply_lower or pat in msg_lower:
            safe_score += 1
    if safe_score >= 2:
        return "safe"

    # Priority 5: Short greetings / acknowledgments → safe
    if len(reply.strip()) < 100 and any(
        g in reply_lower for g in ("আসসালামু", "ধন্যবাদ", "স্বাগতম", "হ্যাঁ", "জি")
    ):
        return "safe"

    # Priority 6: Clients with safe content → safe
    if relation == "client" and safe_score >= 1:
        return "safe"

    # Priority 7: Employee messages → draft (sensitive context)
    if relation == "employee":
        return "restricted"

    # Priority 8: Unknown contacts with no safe signals → draft
    if relation == "unknown" and safe_score == 0:
        return "restricted"

    # Default: safe (most general inquiries)
    return "safe"
