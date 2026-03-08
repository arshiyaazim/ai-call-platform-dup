# ============================================================
# Fazle API Gateway — Central entry point for Fazle system
# Routes requests to Brain, Memory, Tasks, and Tools services
# ============================================================
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
import httpx
import logging
from typing import Optional
from datetime import datetime

from schemas import (
    ChatRequest, ChatResponse,
    DecisionRequest, DecisionResponse,
    MemoryStoreRequest, MemorySearchRequest,
    KnowledgeIngestRequest,
    TaskCreateRequest,
    WebSearchRequest,
    TrainRequest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-api")


class Settings(BaseSettings):
    fazle_api_key: str = ""
    brain_url: str = "http://fazle-brain:8200"
    memory_url: str = "http://fazle-memory:8300"
    task_url: str = "http://fazle-task-engine:8400"
    tools_url: str = "http://fazle-web-intelligence:8500"
    trainer_url: str = "http://fazle-trainer:8600"

    class Config:
        env_prefix = "FAZLE_"


settings = Settings()

app = FastAPI(
    title="Fazle Personal AI — API Gateway",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iamazim.com", "https://fazle.iamazim.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if not settings.fazle_api_key or settings.fazle_api_key == "":
        raise HTTPException(status_code=500, detail="FAZLE_API_KEY not configured")
    if x_api_key != settings.fazle_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-api", "timestamp": datetime.utcnow().isoformat()}


# ── Decision endpoint (Dograh integration) ──────────────────
@app.post("/fazle/decision", response_model=DecisionResponse, dependencies=[Depends(verify_api_key)])
async def make_decision(request: DecisionRequest):
    """Dograh calls this endpoint to get AI decisions for voice interactions."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.brain_url}/decide",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return DecisionResponse(**resp.json())
        except httpx.HTTPError as e:
            logger.error(f"Brain service error: {e}")
            raise HTTPException(status_code=502, detail="Brain service unavailable")


# ── Chat endpoint ───────────────────────────────────────────
@app.post("/fazle/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    """Text chat with Fazle."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.brain_url}/chat",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return ChatResponse(**resp.json())
        except httpx.HTTPError as e:
            logger.error(f"Brain service error: {e}")
            raise HTTPException(status_code=502, detail="Brain service unavailable")


# ── Memory proxy ────────────────────────────────────────────
@app.post("/fazle/memory", dependencies=[Depends(verify_api_key)])
async def store_memory(request: MemoryStoreRequest):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/store",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


@app.post("/fazle/memory/search", dependencies=[Depends(verify_api_key)])
async def search_memory(request: MemorySearchRequest):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


# ── Knowledge ingestion proxy ───────────────────────────────
@app.post("/fazle/knowledge/ingest", dependencies=[Depends(verify_api_key)])
async def ingest_knowledge(request: KnowledgeIngestRequest):
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/ingest",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


# ── Task proxy ──────────────────────────────────────────────
@app.post("/fazle/tasks", dependencies=[Depends(verify_api_key)])
async def create_task(request: TaskCreateRequest):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.task_url}/tasks",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Task service error: {e}")
            raise HTTPException(status_code=502, detail="Task service unavailable")


@app.get("/fazle/tasks", dependencies=[Depends(verify_api_key)])
async def list_tasks():
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.task_url}/tasks")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Task service error: {e}")
            raise HTTPException(status_code=502, detail="Task service unavailable")


# ── Web intelligence proxy ──────────────────────────────────
@app.post("/fazle/web/search", dependencies=[Depends(verify_api_key)])
async def web_search(request: WebSearchRequest):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.tools_url}/search",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Web intelligence error: {e}")
            raise HTTPException(status_code=502, detail="Web intelligence service unavailable")


# ── Training proxy ──────────────────────────────────────────
@app.post("/fazle/train", dependencies=[Depends(verify_api_key)])
async def train(request: TrainRequest):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.trainer_url}/train",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Trainer service error: {e}")
            raise HTTPException(status_code=502, detail="Trainer service unavailable")


# ── Service status ──────────────────────────────────────────
@app.get("/fazle/status", dependencies=[Depends(verify_api_key)])
async def system_status():
    services = {
        "brain": settings.brain_url,
        "memory": settings.memory_url,
        "tasks": settings.task_url,
        "tools": settings.tools_url,
        "trainer": settings.trainer_url,
    }
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in services.items():
            try:
                resp = await client.get(f"{url}/health")
                results[name] = "healthy" if resp.status_code == 200 else "unhealthy"
            except Exception:
                results[name] = "unreachable"
    return {"services": results, "timestamp": datetime.utcnow().isoformat()}
