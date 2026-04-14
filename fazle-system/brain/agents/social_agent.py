# ============================================================
# Social Agent — Handles social media messages (WhatsApp, FB, etc.)
# Wraps existing /chat social path with identity enforcement
# ============================================================
import logging
import httpx
from .base import BaseAgent, AgentContext, AgentResult
from .identity_core import IdentityProfile
from persona_engine import _get_governance_prompt

logger = logging.getLogger("fazle-agents.social")


class SocialAgent(BaseAgent):
    """Handles social channel interactions with conversion-driven persona."""

    name = "social"
    description = "Social media message handler with intent-driven engagement"

    def __init__(
        self,
        llm_gateway_url: str,
        memory_url: str,
        learning_engine_url: str,
        identity: IdentityProfile,
    ):
        self.llm_gateway_url = llm_gateway_url
        self.memory_url = memory_url
        self.learning_engine_url = learning_engine_url
        self.identity = identity

    async def can_handle(self, ctx: AgentContext) -> bool:
        """Social agent handles social-relationship messages."""
        return ctx.relationship == "social"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Process a social interaction with identity-enforced persona."""
        try:
            # Classify intent
            from persona_engine import classify_social_intent
            intent = classify_social_intent(ctx.message)

            # Build identity-aware context
            identity_prompt = self.identity.get_identity_prompt("social")
            social_context = f"user_intent: {intent}"

            # Retrieve user memories
            memories = await self._fetch_memories(ctx)

            # Build learning-enhanced persona
            from persona_engine import build_system_prompt_async
            system_prompt = await build_system_prompt_async(
                user_name=ctx.user_name,
                relationship="social",
                user_id=ctx.user_id,
                learning_engine_url=self.learning_engine_url,
                social_context=social_context,
            )

            # Skip identity_prompt prepend — BASE_IDENTITY in persona_engine covers it.
            # Saves ~460 chars (~150 tokens, ~6s on CPU).
            full_prompt = system_prompt

            # Inject governance canonical facts (cached in Redis, ~1ms)
            gov_prompt = _get_governance_prompt()
            if gov_prompt:
                full_prompt = full_prompt + "\n" + gov_prompt

            # Enrich context
            ctx.metadata["social_intent"] = intent
            ctx.metadata["identity_enforced"] = True
            ctx.memories.extend(memories)

            return AgentResult(
                content=full_prompt,
                metadata={
                    "social_intent": intent,
                    "system_prompt": full_prompt,
                    "agent": self.name,
                },
            )
        except Exception as e:
            logger.error(f"Social agent error: {e}")
            return AgentResult(error=str(e))

    async def _fetch_memories(self, ctx: AgentContext) -> list[dict]:
        """Fetch user-scoped memories for social interaction."""
        memories = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.memory_url}/search",
                    json={
                        "query": ctx.message,
                        "limit": 3,
                        "user_id": ctx.user_id,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    memories = data.get("results", data.get("memories", []))
        except Exception as e:
            logger.debug(f"Memory fetch failed: {e}")
        return memories
