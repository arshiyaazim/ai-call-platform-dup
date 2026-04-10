# ============================================================
# Phase 1C: Capability Boundary Definition
# Frozen production capability matrix — what the system can do
# ============================================================
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class CapStatus(str, Enum):
    IMPLEMENTED = "implemented"  # Fully working in production
    PARTIAL = "partial"          # Works but limited / feature-gated
    MISSING = "missing"          # Not yet built
    DISALLOWED = "disallowed"    # Intentionally blocked


class ConnectorType(str, Enum):
    INTERNAL = "internal"        # Brain ↔ Memory / DB
    EXTERNAL = "external"        # Calls third-party API
    INTEGRATION = "integration"  # Connects external platform


class AuthRequirement(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    VPS_PASSWORD = "vps_password"
    JWT = "jwt"


@dataclass(frozen=True)
class Capability:
    name: str
    status: CapStatus
    connector: ConnectorType
    auth: AuthRequirement
    description: str
    service: str                        # Which micro-service owns it
    limitations: Optional[str] = None
    depends_on: tuple[str, ...] = field(default_factory=tuple)


# ── Production Capability Matrix ─────────────────────────────
# Frozen as of Phase 1 baseline.  Changes require owner approval.

CAPABILITIES: dict[str, Capability] = {

    # ─── CHAT & CONVERSATION ────────────────────────────────
    "whatsapp_chat": Capability(
        name="WhatsApp Chat",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTEGRATION,
        auth=AuthRequirement.API_KEY,
        description="Receive & reply to WhatsApp messages via social-engine",
        service="social-engine",
    ),
    "facebook_chat": Capability(
        name="Facebook Messenger Chat",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTEGRATION,
        auth=AuthRequirement.API_KEY,
        description="Receive & reply to Facebook messages via social-engine",
        service="social-engine",
    ),
    "facebook_comment_reply": Capability(
        name="Facebook Comment Auto-Reply",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTEGRATION,
        auth=AuthRequirement.API_KEY,
        description="Auto-reply to comments on Facebook posts",
        service="social-engine",
    ),
    "owner_chat": Capability(
        name="Owner Direct Chat",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Owner communicates with AI via /chat/owner endpoint",
        service="brain",
    ),
    "owner_password_challenge": Capability(
        name="Owner Password Verification",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.VPS_PASSWORD,
        description="Critical owner actions require VPS password",
        service="brain",
    ),

    # ─── MEMORY & KNOWLEDGE ─────────────────────────────────
    "conversation_memory": Capability(
        name="Conversation Memory",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Per-user conversation history via Redis + PostgreSQL",
        service="memory",
        depends_on=("redis", "postgresql"),
    ),
    "tree_memory": Capability(
        name="Tree Memory (Long-term)",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Owner identity, business facts, structured memory tree",
        service="memory",
    ),
    "qdrant_vector_search": Capability(
        name="Qdrant Vector Search",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Semantic similarity search across stored knowledge",
        service="memory",
        depends_on=("qdrant",),
    ),
    "knowledge_governance": Capability(
        name="Knowledge Governance",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.JWT,
        description="Canonical facts, phrasing rules, correction audit trail — injected into every LLM call",
        service="api",
    ),

    # ─── OWNER CONTROL ──────────────────────────────────────
    "owner_instructions": Capability(
        name="Owner Standing Instructions",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Owner sets instructions via WhatsApp; stored in Redis",
        service="brain",
        limitations="Prompt-only enforcement — LLM must choose to follow",
    ),
    "contact_tagging": Capability(
        name="Contact Tagging",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Owner tags contacts as client/employee/VIP via WhatsApp",
        service="social-engine",
    ),
    "correction_learning": Capability(
        name="Correction / Feedback Learning",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Owner corrects AI; stored as feedback + quality scoring",
        service="brain",
        depends_on=("postgresql",),
    ),
    "command_taxonomy": Capability(
        name="Owner Command Taxonomy",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Structured classification of all owner commands with risk/enforcement",
        service="brain",
    ),

    # ─── LEAD CAPTURE ───────────────────────────────────────
    "lead_capture": Capability(
        name="Automated Lead Capture",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Extract name/phone/interest from conversations, store in DB",
        service="brain",
        depends_on=("postgresql",),
    ),

    # ─── VOICE ──────────────────────────────────────────────
    "voice_tts": Capability(
        name="Voice TTS (Text-to-Speech)",
        status=CapStatus.PARTIAL,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Generate voice replies using ElevenLabs / Kokoro",
        service="api",
        limitations="Works but TTFB needs optimization; voice cloning partial",
    ),
    "voice_stt": Capability(
        name="Voice STT (Speech-to-Text)",
        status=CapStatus.PARTIAL,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Transcribe voice messages via Whisper",
        service="brain",
        limitations="WhatsApp voice messages transcribed; quality varies",
    ),
    "livekit_voice": Capability(
        name="LiveKit Real-time Voice",
        status=CapStatus.PARTIAL,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Real-time voice calls via LiveKit",
        service="api",
        limitations="Infrastructure ready; agent pipeline incomplete",
    ),

    # ─── WEB INTELLIGENCE ───────────────────────────────────
    "web_search": Capability(
        name="Web Search",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Search the web via SearxNG or Brave",
        service="web-intelligence",
    ),

    # ─── LLM GATEWAY ───────────────────────────────────────
    "ollama_inference": Capability(
        name="Ollama Local LLM",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="Local LLM inference via Ollama (qwen2.5:3b)",
        service="llm-gateway",
    ),
    "openai_fallback": Capability(
        name="OpenAI Fallback",
        status=CapStatus.IMPLEMENTED,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Fallback to OpenAI when local model fails/slow",
        service="llm-gateway",
    ),

    # ─── AUTONOMY ───────────────────────────────────────────
    "autonomous_actions": Capability(
        name="Autonomous Action Engine",
        status=CapStatus.PARTIAL,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="AI proposes actions for owner approval",
        service="autonomy-engine",
        limitations="Sandbox mode; all actions require owner approval",
    ),
    "self_learning": Capability(
        name="Self-Learning Engine",
        status=CapStatus.PARTIAL,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="AI learns from owner corrections and interaction patterns",
        service="self-learning",
        limitations="Pattern extraction works; autonomous improvement gated",
    ),

    # ─── NOT IMPLEMENTED ────────────────────────────────────
    "google_drive": Capability(
        name="Google Drive Integration",
        status=CapStatus.MISSING,
        connector=ConnectorType.INTEGRATION,
        auth=AuthRequirement.OAUTH,
        description="Read/write Google Drive files",
        service="tool-engine",
    ),
    "email_send": Capability(
        name="Email (Send)",
        status=CapStatus.MISSING,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Send emails on behalf of owner",
        service="tool-engine",
    ),
    "sms_send": Capability(
        name="SMS Send",
        status=CapStatus.MISSING,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.API_KEY,
        description="Send SMS notifications",
        service="tool-engine",
    ),
    "mobile_app": Capability(
        name="Mobile App Access",
        status=CapStatus.MISSING,
        connector=ConnectorType.INTEGRATION,
        auth=AuthRequirement.JWT,
        description="Owner mobile app for control plane",
        service="frontend",
    ),
    "owner_ui_dashboard": Capability(
        name="Owner UI Dashboard",
        status=CapStatus.MISSING,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.JWT,
        description="Web dashboard for owner operations & settings",
        service="frontend",
    ),

    # ─── INTENTIONALLY BLOCKED ──────────────────────────────
    "direct_db_query": Capability(
        name="Direct Database Query",
        status=CapStatus.DISALLOWED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="AI never runs raw SQL — only parameterised, pre-approved queries",
        service="brain",
    ),
    "external_api_call": Capability(
        name="Arbitrary External API Call",
        status=CapStatus.DISALLOWED,
        connector=ConnectorType.EXTERNAL,
        auth=AuthRequirement.NONE,
        description="AI cannot call arbitrary URLs — only approved integrations",
        service="tool-engine",
    ),
    "file_system_write": Capability(
        name="File System Write",
        status=CapStatus.DISALLOWED,
        connector=ConnectorType.INTERNAL,
        auth=AuthRequirement.NONE,
        description="AI cannot write to server filesystem except designated upload dirs",
        service="brain",
    ),
}


# ── Helpers ──────────────────────────────────────────────────

def get_capability(name: str) -> Optional[Capability]:
    return CAPABILITIES.get(name)


def capabilities_by_status(status: CapStatus) -> list[Capability]:
    return [c for c in CAPABILITIES.values() if c.status == status]


def capabilities_by_service(service: str) -> list[Capability]:
    return [c for c in CAPABILITIES.values() if c.service == service]


def matrix_summary() -> dict:
    """Return a JSON-serialisable capability matrix summary."""
    return {
        "total": len(CAPABILITIES),
        "by_status": {
            s.value: len(capabilities_by_status(s))
            for s in CapStatus
        },
        "by_service": {
            svc: len(caps)
            for svc, caps in _group_by_service().items()
        },
        "implemented": [
            c.name for c in capabilities_by_status(CapStatus.IMPLEMENTED)
        ],
        "partial": [
            {"name": c.name, "limitations": c.limitations}
            for c in capabilities_by_status(CapStatus.PARTIAL)
        ],
        "missing": [c.name for c in capabilities_by_status(CapStatus.MISSING)],
        "disallowed": [c.name for c in capabilities_by_status(CapStatus.DISALLOWED)],
    }


def _group_by_service() -> dict[str, list[Capability]]:
    groups: dict[str, list[Capability]] = {}
    for c in CAPABILITIES.values():
        groups.setdefault(c.service, []).append(c)
    return groups
