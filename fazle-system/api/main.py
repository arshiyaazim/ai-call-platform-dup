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
    RegisterRequest, LoginRequest,
    TokenResponse, UserResponse, UpdateUserRequest,
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin, get_optional_user,
)
from database import (
    ensure_users_table, create_user, get_user_by_email,
    get_user_by_id, list_family_members, update_user, delete_user,
    count_users,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-api")


class Settings(BaseSettings):
    api_key: str = ""
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
    if not settings.api_key or settings.api_key == "":
        raise HTTPException(status_code=500, detail="FAZLE_API_KEY not configured")
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def verify_auth(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Accept either API key (X-API-Key header) or JWT (Authorization: Bearer)."""
    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        user = await get_current_user(authorization)
        return user

    # Fall back to API key
    if x_api_key:
        if not settings.api_key or settings.api_key == "":
            raise HTTPException(status_code=500, detail="FAZLE_API_KEY not configured")
        if x_api_key == settings.api_key:
            return {"id": "api-key", "email": "system", "name": "API Key", "role": "admin", "relationship_to_azim": "self"}
        raise HTTPException(status_code=401, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Authentication required")


@app.on_event("startup")
def startup():
    try:
        ensure_users_table()
        logger.info("Database tables ensured on startup")
    except Exception as e:
        logger.error(f"Failed to ensure database tables: {e}")


# ── Auth endpoints ──────────────────────────────────────────
@app.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, admin: dict = Depends(require_admin)):
    """Register a new family member. Admin only."""
    existing = get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = hash_password(request.password)
    user = create_user(
        email=request.email,
        hashed_password=hashed,
        name=request.name,
        relationship_to_azim=request.relationship_to_azim,
        role=request.role,
    )
    token = create_access_token({"sub": str(user["id"]), "role": user["role"], "rel": user["relationship_to_azim"]})
    return TokenResponse(access_token=token, user=UserResponse(**user))


@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Log in with email and password."""
    user = get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token({"sub": str(user["id"]), "role": user["role"], "rel": user["relationship_to_azim"]})
    user_resp = {k: v for k, v in user.items() if k != "hashed_password"}
    return TokenResponse(access_token=token, user=UserResponse(**user_resp))


@app.post("/auth/setup", response_model=TokenResponse)
async def setup_admin(request: RegisterRequest):
    """Initial admin setup — only works when no users exist."""
    if count_users() > 0:
        raise HTTPException(status_code=403, detail="Setup already completed")

    hashed = hash_password(request.password)
    user = create_user(
        email=request.email,
        hashed_password=hashed,
        name=request.name,
        relationship_to_azim="self",
        role="admin",
    )
    token = create_access_token({"sub": str(user["id"]), "role": "admin", "rel": "self"})
    return TokenResponse(access_token=token, user=UserResponse(**user))


@app.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get the current authenticated user."""
    return UserResponse(**user)


@app.get("/auth/family", response_model=list[UserResponse])
async def get_family(admin: dict = Depends(require_admin)):
    """List all family members. Admin only."""
    members = list_family_members()
    return [UserResponse(**m) for m in members]


@app.put("/auth/family/{user_id}", response_model=UserResponse)
async def update_family_member(user_id: str, request: UpdateUserRequest, admin: dict = Depends(require_admin)):
    """Update a family member. Admin only."""
    updated = update_user(user_id, **request.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**updated)


@app.delete("/auth/family/{user_id}")
async def delete_family_member(user_id: str, admin: dict = Depends(require_admin)):
    """Delete a family member. Admin only. Cannot delete yourself."""
    if str(admin["id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@app.get("/auth/setup-status")
async def setup_status():
    """Check if initial setup has been completed."""
    return {"setup_completed": count_users() > 0}


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-api", "timestamp": datetime.utcnow().isoformat()}


# ── Decision endpoint (Dograh integration) ──────────────────
@app.post("/fazle/decision", response_model=DecisionResponse, dependencies=[Depends(verify_auth)])
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
@app.post("/fazle/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    auth_user: dict = Depends(verify_auth),
):
    """Text chat with Fazle. Injects authenticated user context for persona engine."""
    body = request.model_dump()
    # Inject user context from JWT for persona-aware responses
    if isinstance(auth_user, dict) and auth_user.get("id") != "api-key":
        body["user_id"] = str(auth_user["id"])
        body["user_name"] = auth_user.get("name", "Azim")
        body["relationship"] = auth_user.get("relationship_to_azim", "self")
        body["user"] = auth_user.get("name", "Azim")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.brain_url}/chat",
                json=body,
            )
            resp.raise_for_status()
            return ChatResponse(**resp.json())
        except httpx.HTTPError as e:
            logger.error(f"Brain service error: {e}")
            raise HTTPException(status_code=502, detail="Brain service unavailable")


# ── Memory proxy ────────────────────────────────────────────
@app.post("/fazle/memory")
async def store_memory(request: MemoryStoreRequest, auth_user: dict = Depends(verify_auth)):
    body = request.model_dump()
    if isinstance(auth_user, dict) and auth_user.get("id") != "api-key":
        body["user_id"] = str(auth_user["id"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/store",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


@app.post("/fazle/memory/search")
async def search_memory(request: MemorySearchRequest, auth_user: dict = Depends(verify_auth)):
    body = request.model_dump()
    # Non-admin users can only see their own memories
    if isinstance(auth_user, dict) and auth_user.get("id") != "api-key" and auth_user.get("role") != "admin":
        body["user_id"] = str(auth_user["id"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


# ── Knowledge ingestion proxy ───────────────────────────────
@app.post("/fazle/knowledge/ingest", dependencies=[Depends(verify_auth)])
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
@app.post("/fazle/tasks", dependencies=[Depends(verify_auth)])
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


@app.get("/fazle/tasks", dependencies=[Depends(verify_auth)])
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
@app.post("/fazle/web/search", dependencies=[Depends(verify_auth)])
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
@app.post("/fazle/train", dependencies=[Depends(verify_auth)])
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
@app.get("/fazle/status", dependencies=[Depends(verify_auth)])
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
