# ============================================================
# Fazle Voice Agent — LiveKit-based voice interface
# Joins rooms, transcribes speech, queries Brain, speaks reply
# Uses OpenAI Realtime or Whisper STT + TTS pipeline
# ============================================================
import logging
import os

import httpx
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero
from pydantic_settings import BaseSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-voice")


class Settings(BaseSettings):
    openai_api_key: str = ""
    brain_url: str = "http://fazle-brain:8200"
    tts_voice: str = "alloy"
    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    class Config:
        env_prefix = "FAZLE_VOICE_"


settings = Settings()

# Also read from common env vars
OPENAI_API_KEY = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
BRAIN_URL = settings.brain_url or os.getenv("FAZLE_BRAIN_URL", "http://fazle-brain:8200")


async def query_brain(message: str, user_id: str, user_name: str, relationship: str) -> str:
    """Send transcribed text to Fazle Brain and get a response."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{BRAIN_URL}/chat",
                json={
                    "message": message,
                    "user": user_name,
                    "user_id": user_id,
                    "user_name": user_name,
                    "relationship": relationship,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("reply", "I didn't catch that. Could you say it again?")
        except Exception as e:
            logger.error(f"Brain query failed: {e}")
            return "Sorry, I'm having trouble thinking right now. Give me a moment."


class FazleLLM(llm.LLM):
    """Custom LLM adapter that routes through Fazle Brain instead of direct OpenAI."""

    def __init__(self):
        super().__init__()
        self._user_id = ""
        self._user_name = "User"
        self._relationship = "self"

    def set_user_context(self, user_id: str, user_name: str, relationship: str):
        self._user_id = user_id
        self._user_name = user_name
        self._relationship = relationship

    async def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        **kwargs,
    ) -> "llm.LLMStream":
        # Extract the last user message
        last_message = ""
        for msg in reversed(chat_ctx.messages):
            if msg.role == "user" and msg.content:
                last_message = msg.content
                break

        reply = await query_brain(
            last_message,
            self._user_id,
            self._user_name,
            self._relationship,
        )

        return _SingleResponseStream(reply, chat_ctx)


class _SingleResponseStream(llm.LLMStream):
    """Wraps a single string response as an LLM stream."""

    def __init__(self, text: str, chat_ctx: llm.ChatContext):
        super().__init__(chat_ctx=chat_ctx)
        self._text = text
        self._sent = False

    async def __anext__(self) -> llm.ChatChunk:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        delta = llm.ChoiceDelta(role="assistant", content=self._text)
        choice = llm.Choice(delta=delta, index=0)
        return llm.ChatChunk(choices=[choice])

    async def aclose(self):
        pass


def prewarm(proc: JobProcess):
    """Preload VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    """Main entrypoint for each voice session."""
    logger.info(f"Voice agent joining room: {ctx.room.name}")

    # Extract user context from participant metadata
    # The token endpoint sets: identity=user_id, name=user_name, metadata=relationship
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    user_id = participant.identity or "unknown"
    user_name = participant.name or "User"
    relationship = participant.metadata or "self"

    logger.info(f"Voice session: user={user_name}, relationship={relationship}, id={user_id}")

    # Build the voice pipeline
    fazle_llm = FazleLLM()
    fazle_llm.set_user_context(user_id, user_name, relationship)

    initial_ctx = llm.ChatContext()
    initial_ctx.append(
        role="system",
        text=(
            f"You are Azim speaking to {user_name} (your {relationship}). "
            "Keep responses concise and natural for voice conversation. "
            "Speak warmly and directly."
        ),
    )

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=openai.STT(api_key=OPENAI_API_KEY),
        llm=fazle_llm,
        tts=openai.TTS(api_key=OPENAI_API_KEY, voice=settings.tts_voice),
        chat_ctx=initial_ctx,
        min_endpointing_delay=0.5,
    )

    agent.start(ctx.room, participant)

    # Greet the user
    greeting = f"Hey {user_name}, what's up?" if relationship != "self" else "Hey, what do you need?"
    await agent.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            api_key=settings.livekit_api_key or os.getenv("LIVEKIT_API_KEY", ""),
            api_secret=settings.livekit_api_secret or os.getenv("LIVEKIT_API_SECRET", ""),
            ws_url=settings.livekit_url or os.getenv("LIVEKIT_URL", "ws://livekit:7880"),
        ),
    )
