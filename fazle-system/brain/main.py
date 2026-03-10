# ============================================================
# Fazle Brain — Core Reasoning Engine
# Orchestrates AI reasoning, memory retrieval, tool selection,
# and instruction generation for Dograh voice platform
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import httpx
import json
import logging
import uuid
from typing import Optional
import os
from datetime import datetime
from memory_manager import conversation_get, conversation_set
from persona_engine import build_system_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-brain")


class Settings(BaseSettings):
    openai_api_key: str = ""
    ollama_url: str = "http://ollama:11434"
    llm_provider: str = "openai"  # "openai" or "ollama"
    llm_model: str = "gpt-4o"
    ollama_model: str = "llama3.1"
    memory_url: str = "http://fazle-memory:8300"
    tools_url: str = "http://fazle-web-intelligence:8500"
    task_url: str = "http://fazle-task-engine:8400"

    class Config:
        env_prefix = ""


settings = Settings()

app = FastAPI(title="Fazle Brain — Reasoning Engine", version="1.0.0")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://fazle.iamazim.com,https://iamazim.com,http://localhost:3020").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default system prompt — used as fallback when no user context is provided
DEFAULT_SYSTEM_PROMPT = """You are Fazle, a personal AI assistant for Azim. You are intelligent, direct, and helpful.

Your capabilities:
- Remember personal preferences, contacts, and important information
- Make decisions about calls and meetings based on stored preferences
- Search the internet for information when needed
- Schedule tasks and reminders
- Learn from conversations to improve over time

Key personality traits:
- Professional but warm
- Proactive — anticipate needs
- Concise and clear in responses
- Respects user privacy
- Always honest about uncertainty

When the user says "Fazle, remember..." — extract the information and store it.
When making decisions about calls, always check stored preferences first.

Respond in JSON with these fields:
- "reply": your spoken/text response
- "memory_updates": array of objects to store (each with "type", "content", "text")
- "actions": array of actions to take (each with "type" and relevant fields)
"""


async def query_openai(messages: list[dict]) -> dict:
    """Call OpenAI API for reasoning."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"])


async def query_ollama(messages: list[dict]) -> dict:
    """Call local Ollama LLM for reasoning."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["message"]["content"])


async def query_llm(messages: list[dict]) -> dict:
    """Route to configured LLM provider."""
    if settings.llm_provider == "ollama":
        return await query_ollama(messages)
    return await query_openai(messages)


async def retrieve_memories(query: str, memory_type: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
    """Retrieve relevant memories from memory service, optionally filtered by user."""
    body: dict = {"query": query, "memory_type": memory_type, "limit": 5}
    if user_id:
        body["user_id"] = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search",
                json=body,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")
    return []


async def store_memory_updates(updates: list[dict], user_id: Optional[str] = None, user_name: str = "Azim"):
    """Store memory updates extracted by the LLM."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        for update in updates:
            try:
                body = {
                    "type": update.get("type", "personal"),
                    "user": user_name,
                    "content": update.get("content", {}),
                    "text": update.get("text", str(update.get("content", ""))),
                }
                if user_id:
                    body["user_id"] = user_id
                await client.post(
                    f"{settings.memory_url}/store",
                    json=body,
                )
            except Exception as e:
                logger.warning(f"Memory store failed: {e}")


async def execute_actions(actions: list[dict]):
    """Execute actions decided by the brain."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        for action in actions:
            action_type = action.get("type", "")
            try:
                if action_type == "web_search":
                    await client.post(
                        f"{settings.tools_url}/search",
                        json={"query": action.get("query", ""), "max_results": 5},
                    )
                elif action_type == "create_task":
                    await client.post(
                        f"{settings.task_url}/tasks",
                        json={
                            "title": action.get("title", ""),
                            "description": action.get("description", ""),
                            "scheduled_at": action.get("scheduled_at"),
                            "task_type": action.get("task_type", "reminder"),
                        },
                    )
            except Exception as e:
                logger.warning(f"Action execution failed ({action_type}): {e}")


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-brain", "timestamp": datetime.utcnow().isoformat()}


# ── Decision endpoint (called by Fazle API for Dograh) ──────
class DecisionRequest(BaseModel):
    caller: str
    intent: str
    conversation_context: str = ""
    metadata: dict = Field(default_factory=dict)


@app.post("/decide")
async def decide(request: DecisionRequest):
    """Make a decision for a voice call interaction."""
    # Retrieve relevant memories about the caller and intent
    caller_memories = await retrieve_memories(f"caller {request.caller}")
    intent_memories = await retrieve_memories(f"{request.intent} preferences")

    memory_context = ""
    if caller_memories or intent_memories:
        all_memories = caller_memories + intent_memories
        memory_context = "\n\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', str(m.get('content', '')))}" for m in all_memories
        )

    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"A call decision is needed.\n"
                f"Caller: {request.caller}\n"
                f"Intent: {request.intent}\n"
                f"Context: {request.conversation_context}\n"
                f"{memory_context}\n\n"
                f"Provide your decision as JSON with 'reply', 'memory_updates', and 'actions'."
            ),
        },
    ]

    try:
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=502, detail="LLM service unavailable")

    reply = result.get("reply", "I'll need to get back to you on that.")
    memory_updates = result.get("memory_updates", [])
    actions = result.get("actions", [])

    # Process side effects
    if memory_updates:
        await store_memory_updates(memory_updates)
    if actions:
        await execute_actions(actions)

    return {
        "response": reply,
        "confidence": 0.9,
        "actions": actions,
        "memory_updates": memory_updates,
    }


# ── Chat endpoint ───────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    user: str = "Azim"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    relationship: Optional[str] = None


@app.post("/chat")
async def chat(request: ChatRequest):
    """Interactive chat with Fazle."""
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Determine user context for persona
    user_name = request.user_name or request.user or "Azim"
    relationship = request.relationship or "self"
    user_id = request.user_id

    # Build persona-aware system prompt
    system_prompt = build_system_prompt(
        user_name=user_name,
        relationship=relationship,
        user_id=user_id,
    )

    # Retrieve relevant memories (filtered by user_id for privacy)
    memories = await retrieve_memories(request.message, user_id=user_id)
    memory_context = ""
    if memories:
        memory_context = "\n\nRelevant memories:\n" + "\n".join(
            f"- {m.get('text', str(m.get('content', '')))}" for m in memories
        )

    # Build conversation history
    history = conversation_get(conversation_id)
    messages = [
        {"role": "system", "content": system_prompt + memory_context},
        *history[-10:],  # Keep last 10 turns
        {"role": "user", "content": request.message},
    ]

    try:
        result = await query_llm(messages)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=502, detail="LLM service unavailable")

    reply = result.get("reply", "I'm not sure how to respond to that.")
    memory_updates = result.get("memory_updates", [])
    actions = result.get("actions", [])

    # Update conversation history in Redis
    history.append({"role": "user", "content": request.message})
    history.append({"role": "assistant", "content": reply})
    conversation_set(conversation_id, history)

    # Process side effects
    if memory_updates:
        await store_memory_updates(memory_updates, user_id=user_id, user_name=user_name)
    if actions:
        await execute_actions(actions)

    # Store conversation memory (tagged with user_id for privacy isolation)
    conv_body: dict = {
        "type": "conversation",
        "user": user_name,
        "content": {"message": request.message, "reply": reply, "conversation_id": conversation_id},
        "text": f"{user_name} said: {request.message}. Azim replied: {reply}",
    }
    if user_id:
        conv_body["user_id"] = user_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"{settings.memory_url}/store",
                json=conv_body,
            )
        except Exception:
            pass

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "memory_updates": memory_updates,
    }
