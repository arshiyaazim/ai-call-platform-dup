# ============================================================
# Conversation Agent — Handles direct voice/text conversation
# Uses fast or full LLM pipeline based on query complexity
# ============================================================
import json
import logging
from typing import AsyncIterator

import httpx

from .base import BaseAgent, AgentContext, AgentResult
from persona_engine import _get_governance_prompt

logger = logging.getLogger("fazle-agents.conversation")


class ConversationAgent(BaseAgent):
    name = "conversation"
    description = "Handles direct conversational responses via LLM"

    def __init__(self, ollama_url: str, voice_fast_model: str, llm_gateway_url: str):
        self.ollama_url = ollama_url
        self.voice_fast_model = voice_fast_model
        self.llm_gateway_url = llm_gateway_url

    async def can_handle(self, ctx: AgentContext) -> bool:
        return True  # Conversation agent is the default fallback

    async def execute(self, ctx: AgentContext) -> AgentResult:
        """Generate a conversational response via gateway (non-streaming)."""
        messages = self._build_messages(ctx)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.llm_gateway_url}/generate",
                    json={
                        "messages": messages,
                        "caller": "fazle-conversation-agent",
                        "temperature": 0.7,
                        "max_tokens": 80,
                        "request_type": "user_chat",
                    },
                )
                resp.raise_for_status()
                content = resp.json().get("content", "")
                return AgentResult(content=content)
        except Exception as e:
            logger.error(f"Conversation agent failed: {e}")
            return AgentResult(
                content="I'm having trouble right now. Give me a moment.",
                error=str(e),
            )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """Stream conversational response tokens via gateway."""
        messages = self._build_messages(ctx)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.llm_gateway_url}/generate",
                    json={
                        "messages": messages,
                        "caller": "fazle-conversation-agent-stream",
                        "temperature": 0.7,
                        "stream": True,
                        "max_tokens": 40,
                        "request_type": "user_chat",
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            chunk_str = line[6:].strip()
                            if chunk_str == "[DONE]":
                                break
                            try:
                                data = json.loads(chunk_str)
                                # Ollama-style: {"content": "...", "done": ...}
                                if "content" in data:
                                    chunk = data.get("content", "")
                                    if chunk:
                                        yield chunk
                                    if data.get("done", False):
                                        break
                                # OpenAI-style: {"choices": [{"delta": {"content": "..."}}]}
                                elif "choices" in data:
                                    delta = data["choices"][0].get("delta", {})
                                    text = delta.get("content", "")
                                    if text:
                                        yield text
                            except (json.JSONDecodeError, IndexError, KeyError):
                                if chunk_str:
                                    yield chunk_str
        except Exception as e:
            logger.error(f"Conversation stream failed: {e}")
            yield "Sorry, I'm having trouble right now."

    def _build_system_prompt(self, ctx: AgentContext) -> str:
        memory_context = ""
        if ctx.memories:
            memory_lines = [f"- {m.get('text', '')}" for m in ctx.memories[:3]]
            memory_context = "\n\nRelevant memories:\n" + "\n".join(memory_lines)

        # Inject governance canonical facts (cached in Redis, ~1ms)
        gov_context = ""
        gov_prompt = _get_governance_prompt()
        if gov_prompt:
            gov_context = "\n" + gov_prompt

        return (
            f"You are Azim's personal AI assistant speaking to {ctx.user_name}. "
            "Respond naturally in 1-3 sentences. Be concise, warm, and direct. "
            f"Plain text only.{gov_context}{memory_context}"
        )

    def _build_messages(self, ctx: AgentContext) -> list[dict]:
        return [
            {"role": "system", "content": self._build_system_prompt(ctx)},
            {"role": "user", "content": ctx.message},
        ]
