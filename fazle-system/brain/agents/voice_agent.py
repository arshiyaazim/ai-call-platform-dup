# ============================================================
# Voice Agent — Handles voice call interactions
# Ultra-low latency path with identity enforcement
# ============================================================
import logging
import httpx
from .base import BaseAgent, AgentContext, AgentResult
from .identity_core import IdentityProfile

logger = logging.getLogger("fazle-agents.voice")


class VoiceAgent(BaseAgent):
    """Handles voice interactions with minimal latency and identity consistency."""

    name = "voice"
    description = "Voice call handler — ultra-fast, identity-enforced"

    def __init__(
        self,
        ollama_url: str,
        voice_fast_model: str,
        llm_gateway_url: str,
        learning_engine_url: str,
        identity: IdentityProfile,
    ):
        self.ollama_url = ollama_url
        self.voice_fast_model = voice_fast_model
        self.llm_gateway_url = llm_gateway_url
        self.learning_engine_url = learning_engine_url
        self.identity = identity

    async def can_handle(self, ctx: AgentContext) -> bool:
        """Voice agent handles voice-source messages."""
        return ctx.metadata.get("source") == "voice"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Build voice-optimized prompt with identity core."""
        try:
            from persona_engine import build_voice_system_prompt
            voice_prompt = await build_voice_system_prompt(
                user_name=ctx.user_name,
                relationship=ctx.relationship,
                user_id=ctx.user_id,
                learning_engine_url=self.learning_engine_url,
            )

            # Inject identity core (compact for voice latency)
            style = self.identity.get_style_for(ctx.relationship)
            identity_hint = (
                f"[IDENTITY: {self.identity.name} | "
                f"tone={style.get('tone', 'warm')} | "
                f"lang={style.get('language', 'bangla')}]"
            )

            full_prompt = f"{identity_hint}\n{voice_prompt}"

            ctx.metadata["identity_enforced"] = True
            ctx.metadata["voice_model"] = self.voice_fast_model

            return AgentResult(
                content=full_prompt,
                metadata={
                    "system_prompt": full_prompt,
                    "agent": self.name,
                    "model": self.voice_fast_model,
                },
            )
        except Exception as e:
            logger.error(f"Voice agent error: {e}")
            return AgentResult(error=str(e))

    async def generate_fast(
        self,
        messages: list[dict],
        voice_fast_mode: bool = True,
    ) -> str:
        """Generate a voice reply via gateway (single entry point)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.llm_gateway_url}/generate",
                    json={
                        "messages": messages,
                        "caller": "fazle-voice-agent",
                        "temperature": 0.7,
                        "max_tokens": 80,
                        "request_type": "user_chat",
                    },
                )
                resp.raise_for_status()
                return resp.json().get("content", "").strip()
        except Exception as e:
            logger.error(f"Voice generation failed: {e}")
            return "দুঃখিত, একটু সমস্যা হচ্ছে।"
