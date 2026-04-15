# ============================================================
# WBOM Agent — WhatsApp Business Operations Manager
# Domain agent for business operations: contacts, escorts,
# billing, salary, payments, WhatsApp message processing
# ============================================================
import logging
import httpx
from .base import BaseAgent, AgentContext, AgentResult
from .identity_core import IdentityProfile

logger = logging.getLogger("fazle-agents.wbom")

# Keywords that trigger WBOM routing
_WBOM_KEYWORDS = frozenset([
    # English - business operations
    "contact", "contacts", "client", "vendor", "employee", "employees",
    "escort", "escort program", "security guard", "guards",
    "vessel", "lighter", "mother vessel", "lighter vessel",
    "salary", "billing", "invoice", "payment", "bill",
    "program", "shift", "day shift", "night shift",
    "advance", "deduction", "cash", "cash flow",
    "whatsapp message", "template", "message template",
    "outstanding", "receivable", "payable",
    # Bangla - business terms
    "বেতন", "এসকর্ট", "জাহাজ", "লাইটার", "গার্ড",
    "বিল", "পেমেন্ট", "কন্টাক্ট", "কর্মচারী",
    "চালান", "হিসাব", "টাকা", "অগ্রিম",
    # Business-specific
    "al-aqsa", "alaqsa", "security service",
])


class WBOMAgent(BaseAgent):
    """Handles business operations via the WBOM microservice."""

    name = "wbom"
    description = "WhatsApp Business Operations Manager — contacts, escort programs, billing, salary, message processing"

    def __init__(self, wbom_url: str, identity: IdentityProfile):
        self.wbom_url = wbom_url.rstrip("/")
        self.identity = identity

    async def can_handle(self, ctx: AgentContext) -> bool:
        """Check if message relates to business operations."""
        msg_lower = ctx.message.lower()
        return any(kw in msg_lower for kw in _WBOM_KEYWORDS)

    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Process business operation request via WBOM service."""
        try:
            msg_lower = ctx.message.lower()

            # Determine which WBOM capability is needed
            context_parts = []
            wbom_data = {}

            # Try to get relevant data from WBOM service
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Search across WBOM data for context
                try:
                    resp = await client.get(
                        f"{self.wbom_url}/api/subagent/wbom/search",
                        params={"search_type": "programs", "query": ctx.message[:200], "limit": 5},
                    )
                    if resp.status_code == 200:
                        search = resp.json()
                        if search.get("total", 0) > 0:
                            wbom_data["search_results"] = search.get("results", {})
                except Exception as e:
                    logger.debug(f"WBOM search failed: {e}")

                # If message mentions a WhatsApp number, process it
                if "message" in msg_lower or "whatsapp" in msg_lower:
                    try:
                        resp = await client.get(
                            f"{self.wbom_url}/api/subagent/wbom/search",
                            params={"search_type": "contacts", "query": ctx.message[:200], "limit": 5},
                        )
                        if resp.status_code == 200:
                            wbom_data["recent_messages"] = resp.json()[:5]
                    except Exception:
                        pass

            # Build system prompt with WBOM context
            identity_prompt = self.identity.get_identity_prompt("social")

            wbom_context = self._build_wbom_context(wbom_data)

            system_prompt = (
                f"{identity_prompt}\n\n"
                "You are handling a business operations query. "
                "You have access to the WBOM (WhatsApp Business Operations Manager) system "
                "which manages contacts, escort programs, billing, salary, and WhatsApp messages "
                "for a security personnel service business.\n\n"
                f"{wbom_context}"
            )

            ctx.metadata["wbom_active"] = True
            ctx.metadata["identity_enforced"] = True

            return AgentResult(
                content=system_prompt,
                metadata={
                    "agent": self.name,
                    "system_prompt": system_prompt,
                    "wbom_data": wbom_data,
                },
            )
        except Exception as e:
            logger.error(f"WBOM agent error: {e}")
            return AgentResult(error=str(e))

    def _build_wbom_context(self, data: dict) -> str:
        """Build context string from WBOM data."""
        parts = []
        if data.get("search_results"):
            results = data["search_results"]
            for table, rows in results.items():
                if rows:
                    parts.append(f"[{table}]: {len(rows)} matching records found")

        if data.get("recent_messages"):
            parts.append(f"Recent messages: {len(data['recent_messages'])} available")

        if parts:
            return "WBOM Data Context:\n" + "\n".join(parts)
        return ""
