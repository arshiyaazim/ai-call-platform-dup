# ============================================================
# Phase 1A: Owner Command Taxonomy
# Authoritative classification of every owner command/intent
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class CommandCategory(str, Enum):
    QUERY = "query"              # Read-only data retrieval
    TEACH = "teach"              # Teach AI new knowledge / identity
    CORRECT = "correct"          # Fix wrong AI behaviour or data
    INSTRUCT = "instruct"        # Standing operational instructions
    APPROVE = "approve"          # Approve/reject pending actions
    DESTRUCTIVE = "destructive"  # Delete data, disable features
    INTEGRATION = "integration"  # External system connections


class RiskLevel(str, Enum):
    LOW = "low"           # Silent execution, no side-effects
    MEDIUM = "medium"     # Needs confirmation
    HIGH = "high"         # Needs confirmation + may affect users
    CRITICAL = "critical" # Needs confirmation + VPS password


class Enforcement(str, Enum):
    CODE = "code_enforced"   # Logic enforced in Python
    PROMPT = "prompt_only"   # Relies on LLM following the prompt
    HYBRID = "hybrid"        # Code triggers action, LLM shapes output


@dataclass(frozen=True)
class CommandDef:
    intent: str
    category: CommandCategory
    risk: RiskLevel
    enforcement: Enforcement
    needs_confirmation: bool
    needs_password: bool
    description_bn: str
    description_en: str
    redis_key: Optional[str] = None
    db_table: Optional[str] = None
    examples: tuple[str, ...] = field(default_factory=tuple)


# ── Authoritative registry ──────────────────────────────────
OWNER_COMMANDS: dict[str, CommandDef] = {

    # ─── QUERY ──────────────────────────────────────────────
    "query_info": CommandDef(
        intent="query_info",
        category=CommandCategory.QUERY,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=False,
        needs_password=False,
        description_bn="তথ্য জানতে চাওয়া — কে মেসেজ করেছে, স্ট্যাটাস ইত্যাদি",
        description_en="Ask for information — who messaged, status, stats",
        examples=(
            "কে কে মেসেজ করেছে?",
            "আজকের লিড কয়টা?",
            "last 5 conversations দেখাও",
        ),
    ),
    "generate_report": CommandDef(
        intent="generate_report",
        category=CommandCategory.QUERY,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=False,
        needs_password=False,
        description_bn="রিপোর্ট তৈরি — দৈনিক/সাপ্তাহিক পরিসংখ্যান",
        description_en="Generate report — daily/weekly statistics",
        examples=("আজকের রিপোর্ট দাও", "weekly summary"),
    ),

    # ─── TEACH ──────────────────────────────────────────────
    "update_profile": CommandDef(
        intent="update_profile",
        category=CommandCategory.TEACH,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="এআই-কে মালিকের পরিচয়/ব্যক্তিত্ব শেখানো",
        description_en="Teach AI owner identity, personality, language",
        redis_key="fazle:azim:profile",
        examples=(
            "আমার নাম Azim",
            "আমি চট্টগ্রামে থাকি",
        ),
    ),
    "set_permanent_memory": CommandDef(
        intent="set_permanent_memory",
        category=CommandCategory.TEACH,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="স্থায়ী তথ্য মনে রাখতে বলা",
        description_en="Tell AI to permanently remember a fact",
        examples=(
            "এটা মনে রাখো — অফিস সকাল ৯টায় খোলে",
            "মনে রাখো আমাদের ৩টা অফিস আছে",
        ),
    ),

    # ─── CORRECT ────────────────────────────────────────────
    "correction_learning": CommandDef(
        intent="correction_learning",
        category=CommandCategory.CORRECT,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="ভুল তথ্য সংশোধন করা",
        description_en="Correct wrong AI response or knowledge",
        db_table="fazle_owner_feedback",
        examples=(
            "এটা ভুল ছিল, সঠিক উত্তর হলো...",
            "ট্রেনিং ৪৫ দিন না, ৪৫–৯০ দিন",
        ),
    ),

    # ─── INSTRUCT ───────────────────────────────────────────
    "set_instruction": CommandDef(
        intent="set_instruction",
        category=CommandCategory.INSTRUCT,
        risk=RiskLevel.MEDIUM,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=True,
        needs_password=False,
        description_bn="স্থায়ী নির্দেশনা দেওয়া — এখন থেকে এভাবে করো",
        description_en="Set standing instruction — change AI behaviour",
        redis_key="fazle:owner:instructions",
        examples=(
            "এখন থেকে সবাইকে অফিসে আসতে বলো",
            "রাত ১০টার পর auto reply বন্ধ রাখো",
        ),
    ),
    "hiring_update": CommandDef(
        intent="hiring_update",
        category=CommandCategory.INSTRUCT,
        risk=RiskLevel.HIGH,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=True,
        needs_password=False,
        description_bn="নিয়োগ সংক্রান্ত আপডেট",
        description_en="Hiring process update — affects active recruitment",
        examples=(
            "আপাতত নিয়োগ বন্ধ",
            "আজ থেকে সার্ভে স্কট নিয়োগ চালু",
        ),
    ),
    "operation_update": CommandDef(
        intent="operation_update",
        category=CommandCategory.INSTRUCT,
        risk=RiskLevel.HIGH,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=True,
        needs_password=False,
        description_bn="অপারেশনাল আপডেট — ডিউটি, শিফট, পরিবর্তন",
        description_en="Operational update — duty, shift changes affecting staff",
        examples=(
            "কাল ২০ জন ডিউটিতে যাবে",
            "ইস্পাহানি পয়েন্টে ৫ জন বাড়াও",
        ),
    ),
    "staff_issue": CommandDef(
        intent="staff_issue",
        category=CommandCategory.INSTRUCT,
        risk=RiskLevel.MEDIUM,
        enforcement=Enforcement.HYBRID,
        needs_confirmation=True,
        needs_password=False,
        description_bn="কর্মচারী সমস্যা রিপোর্ট/সমাধান",
        description_en="Staff issue report or resolution",
        examples=(
            "রাশেদ আজ ডিউটিতে আসেনি",
            "01712345678 কে ব্ল্যাকলিস্ট করো",
        ),
    ),

    # ─── APPROVE ────────────────────────────────────────────
    "set_relation": CommandDef(
        intent="set_relation",
        category=CommandCategory.APPROVE,
        risk=RiskLevel.MEDIUM,
        enforcement=Enforcement.CODE,
        needs_confirmation=True,
        needs_password=False,
        description_bn="কন্টাক্টের সম্পর্ক নির্ধারণ — client, employee",
        description_en="Tag contact relation — client, employee, friend",
        examples=(
            "01711234567 is client",
            "এই নাম্বারটা ক্লায়েন্ট",
        ),
    ),
    "set_priority": CommandDef(
        intent="set_priority",
        category=CommandCategory.APPROVE,
        risk=RiskLevel.MEDIUM,
        enforcement=Enforcement.CODE,
        needs_confirmation=True,
        needs_password=False,
        description_bn="VIP / প্রায়োরিটি নির্ধারণ",
        description_en="Mark contact as VIP or priority",
        examples=(
            "01711234567 is VIP",
            "এই নাম্বারকে VIP করো",
        ),
    ),
    "approve_action": CommandDef(
        intent="approve_action",
        category=CommandCategory.APPROVE,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="পেন্ডিং অ্যাকশন অনুমোদন",
        description_en="Approve a pending autonomous action",
        redis_key="fazle:owner:pending_action",
        examples=("হ্যাঁ করো", "approved", "yes"),
    ),
    "reject_action": CommandDef(
        intent="reject_action",
        category=CommandCategory.APPROVE,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="পেন্ডিং অ্যাকশন বাতিল",
        description_en="Reject a pending autonomous action",
        redis_key="fazle:owner:pending_action",
        examples=("না", "বাতিল", "reject"),
    ),

    # ─── DESTRUCTIVE ────────────────────────────────────────
    "delete_data": CommandDef(
        intent="delete_data",
        category=CommandCategory.DESTRUCTIVE,
        risk=RiskLevel.CRITICAL,
        enforcement=Enforcement.CODE,
        needs_confirmation=True,
        needs_password=True,
        description_bn="ডাটা মুছে ফেলা — ইউজার, কনভারসেশন",
        description_en="Delete data — user records, conversations",
        examples=(
            "01711234567 এর সব ডাটা মুছে দাও",
            "delete all conversations",
        ),
    ),
    "system_control": CommandDef(
        intent="system_control",
        category=CommandCategory.DESTRUCTIVE,
        risk=RiskLevel.CRITICAL,
        enforcement=Enforcement.CODE,
        needs_confirmation=True,
        needs_password=True,
        description_bn="সিস্টেম কন্ট্রোল — AI বন্ধ/চালু, auto-reply বন্ধ",
        description_en="System control — disable AI, toggle auto-reply",
        examples=(
            "AI বন্ধ করো",
            "auto reply off",
        ),
    ),

    # ─── INTEGRATION ────────────────────────────────────────
    "web_search": CommandDef(
        intent="web_search",
        category=CommandCategory.INTEGRATION,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.CODE,
        needs_confirmation=False,
        needs_password=False,
        description_bn="ওয়েব সার্চ — ইন্টারনেটে তথ্য খোঁজা",
        description_en="Web search — look up information online",
        examples=(
            "Chittagong port schedule খুঁজে দাও",
            "Google এ সার্চ করো",
        ),
    ),

    # ─── PROMPT-ONLY (behaviour shaping, no code guard) ────
    "tone_adaptation": CommandDef(
        intent="tone_adaptation",
        category=CommandCategory.INSTRUCT,
        risk=RiskLevel.LOW,
        enforcement=Enforcement.PROMPT,
        needs_confirmation=False,
        needs_password=False,
        description_bn="টোন পরিবর্তন — নির্দিষ্ট কন্ট্যাক্টের সাথে ভাষার ধরন",
        description_en="Adapt tone for a specific contact — strict, friendly, formal",
        examples=(
            "01711234567 is strict",
            "এই নাম্বারের সাথে formal কথা বলো",
        ),
    ),
}


# ── Helpers ──────────────────────────────────────────────────

def get_command(intent: str) -> Optional[CommandDef]:
    """Return command definition by intent name."""
    return OWNER_COMMANDS.get(intent)


def commands_by_category(cat: CommandCategory) -> list[CommandDef]:
    """Return all commands in a given category."""
    return [c for c in OWNER_COMMANDS.values() if c.category == cat]


def commands_needing_password() -> list[CommandDef]:
    """Return commands that require VPS password."""
    return [c for c in OWNER_COMMANDS.values() if c.needs_password]


def commands_needing_confirmation() -> list[CommandDef]:
    """Return commands that require owner confirmation."""
    return [c for c in OWNER_COMMANDS.values() if c.needs_confirmation]


def prompt_only_commands() -> list[CommandDef]:
    """Return commands enforced only via prompt (no code guard)."""
    return [c for c in OWNER_COMMANDS.values()
            if c.enforcement == Enforcement.PROMPT]


def taxonomy_summary() -> dict:
    """Return a JSON-serialisable taxonomy summary for debugging."""
    return {
        "total_commands": len(OWNER_COMMANDS),
        "by_category": {
            cat.value: len(commands_by_category(cat))
            for cat in CommandCategory
        },
        "by_risk": {
            risk.value: len([c for c in OWNER_COMMANDS.values()
                             if c.risk == risk])
            for risk in RiskLevel
        },
        "by_enforcement": {
            enf.value: len([c for c in OWNER_COMMANDS.values()
                            if c.enforcement == enf])
            for enf in Enforcement
        },
        "password_protected": len(commands_needing_password()),
        "confirmation_required": len(commands_needing_confirmation()),
    }
