# ============================================================
# Fazle API Gateway — Central entry point for Fazle system
# Routes requests to Brain, Memory, Tasks, and Tools services
# ============================================================
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_fastapi_instrumentator import Instrumentator
import hmac
import httpx
import logging
import os
import io
import base64
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
    ChangePasswordRequest, AdminResetPasswordRequest,
    RequestPasswordResetRequest, ResetPasswordConfirmRequest,
    UserManagementCreate, UserManagementUpdate,
)
from watchdog_routes import router as watchdog_router
from user_routes import router as user_router
from social_routes import router as social_router
from gdpr_routes import router as gdpr_router
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin, get_optional_user,
)
from database import (
    ensure_users_table, create_user, get_user_by_email,
    get_user_by_id, list_family_members, update_user, delete_user,
    count_users, save_message, get_user_conversations,
    get_conversation_messages, get_all_conversations,
    ensure_admin_tables, ensure_password_reset_table,
    update_user_password, create_password_reset_token,
    get_valid_reset_token, mark_reset_token_used,
    ensure_gdpr_tables, ensure_soft_delete_columns,
)
from audit import ensure_audit_table, log_action, get_audit_logs
from admin_routes import router as admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-api")

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif"}


class Settings(BaseSettings):
    api_key: str = ""
    brain_url: str = "http://fazle-brain:8200"
    memory_url: str = "http://fazle-memory:8300"
    task_url: str = "http://fazle-task-engine:8400"
    tools_url: str = "http://fazle-web-intelligence:8500"
    trainer_url: str = "http://fazle-trainer:8600"
    learning_engine_url: str = "http://fazle-learning-engine:8900"
    autonomy_engine_url: str = "http://fazle-autonomy-engine:9100"
    tool_engine_url: str = "http://fazle-tool-engine:9200"
    knowledge_graph_url: str = "http://fazle-knowledge-graph:9300"
    autonomous_runner_url: str = "http://fazle-autonomous-runner:9400"
    self_learning_url: str = "http://fazle-self-learning:9500"
    guardrail_url: str = "http://fazle-guardrail-engine:9600"
    workflow_engine_url: str = "http://fazle-workflow-engine:9700"
    social_engine_url: str = "http://fazle-social-engine:9900"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_url: str = "wss://livekit.iamazim.com"
    # Vision + MinIO
    openai_api_key: str = ""
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "fazle-multimodal"
    minio_secure: bool = False

    class Config:
        env_prefix = "FAZLE_"


settings = Settings()

app = FastAPI(
    title="Fazle Personal AI — API Gateway",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iamazim.com", "https://fazle.iamazim.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin_router)
app.include_router(watchdog_router)
app.include_router(user_router)
app.include_router(social_router)
app.include_router(gdpr_router)


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
    # Fail fast if API key not configured
    if not settings.api_key or not settings.api_key.strip():
        raise HTTPException(
            status_code=500,
            detail="FAZLE_API_KEY not configured on server"
        )

    # Try JWT first
    if authorization and authorization.startswith("Bearer "):
        user = await get_current_user(authorization)
        return user

    # Fall back to API key (timing-safe comparison)
    if x_api_key and hmac.compare_digest(x_api_key.strip(), settings.api_key.strip()):
        return {"id": "api-key", "email": "system", "name": "API Key", "role": "admin", "relationship_to_azim": "self"}

    if x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    raise HTTPException(status_code=401, detail="Authentication required")


@app.on_event("startup")
def startup():
    try:
        ensure_users_table()
        ensure_audit_table()
        ensure_admin_tables()
        ensure_password_reset_table()
        ensure_gdpr_tables()
        ensure_soft_delete_columns()
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
    log_action(admin, "register_user", target_type="user", target_id=str(user["id"]), detail=f"Registered {request.name} ({request.email}) as {request.relationship_to_azim}")
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
    log_action(user_resp, "login", target_type="user", target_id=str(user["id"]))
    return TokenResponse(access_token=token, user=UserResponse(**user_resp))


class DashboardLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


@app.post("/fazle/admin/login")
async def dashboard_login(request: DashboardLoginRequest):
    """Dashboard login — accepts username (email) and password, returns token + role."""
    email = request.username.strip().lower()
    user = get_user_by_email(email)
    if not user or not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token({"sub": str(user["id"]), "role": user["role"], "rel": user["relationship_to_azim"]})
    user_resp = {k: v for k, v in user.items() if k != "hashed_password"}
    log_action(user_resp, "login", target_type="user", target_id=str(user["id"]))
    return {"token": token, "role": user["role"]}


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


# ── Password Management endpoints ───────────────────────────
@app.post("/auth/change-password")
async def change_password(request: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """Change your own password. Requires current password."""
    # Fetch full user record with hashed_password
    full_user = get_user_by_email(user["email"])
    if not full_user or not verify_password(request.current_password, full_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = hash_password(request.new_password)
    update_user_password(str(user["id"]), new_hash)
    log_action(user, "change_password", target_type="user", target_id=str(user["id"]))
    return {"status": "password_changed"}


@app.post("/auth/admin/reset-password")
async def admin_reset_password(request: AdminResetPasswordRequest, admin: dict = Depends(require_admin)):
    """Admin resets another user's password."""
    target = get_user_by_id(request.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    new_hash = hash_password(request.new_password)
    update_user_password(request.user_id, new_hash)
    log_action(admin, "admin_reset_password", target_type="user", target_id=request.user_id,
               detail=f"Admin reset password for {target.get('email', 'unknown')}")
    return {"status": "password_reset"}


@app.post("/auth/request-password-reset")
async def request_password_reset(request: RequestPasswordResetRequest):
    """Request a password reset token. Always returns 200 to prevent email enumeration."""
    import secrets
    import hashlib
    from datetime import timedelta, timezone

    user = get_user_by_email(request.email)
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        create_password_reset_token(str(user["id"]), token_hash, expires)
        # In production, send email with raw_token. Log for now.
        logger.info(f"Password reset token generated for {request.email} (token: {raw_token})")

    # Always return same response to prevent email enumeration
    return {"status": "if_account_exists_reset_email_sent"}


@app.post("/auth/reset-password")
async def reset_password_confirm(request: ResetPasswordConfirmRequest):
    """Confirm password reset using token."""
    import hashlib

    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    token_record = get_valid_reset_token(token_hash)
    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    new_hash = hash_password(request.new_password)
    update_user_password(str(token_record["user_id"]), new_hash)
    mark_reset_token_used(str(token_record["id"]))

    user = get_user_by_id(str(token_record["user_id"]))
    if user:
        log_action(user, "reset_password_via_token", target_type="user", target_id=str(user["id"]))

    return {"status": "password_reset_successful"}


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
    log_action(admin, "update_user", target_type="user", target_id=user_id, detail=str(request.model_dump(exclude_unset=True)))
    return UserResponse(**updated)


@app.delete("/auth/family/{user_id}")
async def delete_family_member(user_id: str, admin: dict = Depends(require_admin)):
    """Delete a family member. Admin only. Cannot delete yourself."""
    if str(admin["id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    log_action(admin, "delete_user", target_type="user", target_id=user_id)
    return {"status": "deleted"}


@app.get("/auth/setup-status")
async def setup_status():
    """Check if initial setup has been completed."""
    return {"setup_completed": count_users() > 0}


# ── Voice (LiveKit token) ──────────────────────────────────
@app.post("/fazle/voice/token")
async def voice_token(auth_user: dict = Depends(verify_auth)):
    """Generate a LiveKit access token for authenticated users."""
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise HTTPException(status_code=503, detail="Voice service not configured")

    from livekit.api import AccessToken, VideoGrants

    user_id = str(auth_user.get("id", "anonymous"))
    user_name = auth_user.get("name", "User")
    relationship = auth_user.get("relationship_to_azim", "self")

    # Each user gets their own private room for voice chat with Azim
    room_name = f"fazle-voice-{user_id}"

    token = AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    token.with_identity(user_id)
    token.with_name(user_name)
    token.with_metadata(relationship)
    token.with_grants(VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    ))

    return {
        "token": token.to_jwt(),
        "url": settings.livekit_url,
        "room": room_name,
    }


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
            data = resp.json()

            # Persist chat history to DB
            user_id = str(auth_user["id"]) if isinstance(auth_user, dict) and auth_user.get("id") != "api-key" else None
            conv_id = data.get("conversation_id", "")
            if user_id and conv_id:
                try:
                    save_message(user_id, conv_id, "user", request.message, title=request.message[:200])
                    save_message(user_id, conv_id, "assistant", data.get("reply", ""))
                except Exception as e:
                    logger.warning(f"Chat history save failed: {e}")

            return ChatResponse(**data)
        except httpx.HTTPError as e:
            logger.error(f"Brain service error: {e}")
            raise HTTPException(status_code=502, detail="Brain service unavailable")


# ── Chat history ────────────────────────────────────────────
@app.get("/fazle/conversations")
async def list_conversations(auth_user: dict = Depends(verify_auth)):
    """List conversations for the current user (admin sees all)."""
    if auth_user.get("role") == "admin":
        return {"conversations": get_all_conversations()}
    return {"conversations": get_user_conversations(str(auth_user["id"]))}


@app.get("/fazle/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, auth_user: dict = Depends(verify_auth)):
    """Get messages for a specific conversation."""
    user_id = None if auth_user.get("role") == "admin" else str(auth_user["id"])
    messages = get_conversation_messages(conversation_id, user_id=user_id)
    if not messages and user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"messages": messages}


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


@app.delete("/fazle/memory/{memory_id}")
async def delete_memory(memory_id: str, auth_user: dict = Depends(verify_auth)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.delete(
                f"{settings.memory_url}/memories/{memory_id}",
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory service error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


@app.put("/fazle/memory/{memory_id}")
async def update_memory(memory_id: str, body: dict, auth_user: dict = Depends(verify_auth)):
    """Update a memory record via the memory service."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.put(
                f"{settings.memory_url}/memories/{memory_id}",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory update error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


@app.patch("/fazle/memory/{memory_id}/lock")
async def toggle_memory_lock(memory_id: str, auth_user: dict = Depends(verify_auth)):
    """Toggle lock status on a memory record."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.patch(
                f"{settings.memory_url}/memories/{memory_id}/lock",
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Memory lock toggle error: {e}")
            raise HTTPException(status_code=502, detail="Memory service unavailable")


@app.get("/fazle/health")
async def fazle_health():
    """Health check alias under /fazle/ prefix."""
    return {"status": "healthy", "service": "fazle-api", "timestamp": datetime.utcnow().isoformat()}


# ── Multimodal memory search proxy ──────────────────────────
@app.post("/fazle/memory/search-multimodal")
async def search_multimodal(request: MemorySearchRequest, auth_user: dict = Depends(verify_auth)):
    body = request.model_dump(exclude_none=True)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.memory_url}/search-multimodal",
                json=body,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Multimodal memory search error: {e}")
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


# ── File upload ─────────────────────────────────────────────
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}


async def _caption_image_gpt4o(image_bytes: bytes, filename: str) -> str:
    """Send image to GPT-4o vision for captioning."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext, "image/jpeg")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Describe this image in rich detail for a personal AI memory system. "
                                    "Include: what's in the scene, any text/OCR, people's apparent emotions, "
                                    "colors, objects, location clues, and anything notable. "
                                    "Be thorough but concise (2-4 sentences)."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                            },
                        ],
                    }
                ],
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _make_thumbnail(image_bytes: bytes, max_size: int = 256) -> bytes:
    """Create a JPEG thumbnail from image bytes."""
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _upload_to_minio(object_key: str, data: bytes, content_type: str) -> bool:
    """Upload bytes to MinIO bucket."""
    if not settings.minio_access_key or not settings.minio_secret_key:
        return False
    try:
        from minio import Minio
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        # Ensure bucket exists
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        client.put_object(
            settings.minio_bucket,
            object_key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return True
    except Exception as e:
        logger.error(f"MinIO upload failed for {object_key}: {e}")
        return False


@app.post("/fazle/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    auth_user: dict = Depends(verify_auth),
):
    """Upload a file (PDF, DOCX, TXT, images) for RAG ingestion.
    Images are captioned by GPT-4o, thumbnailed, stored in MinIO,
    and embedded into the multimodal Qdrant collection."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Size guard (20MB)
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 20MB)")

    user_id = str(auth_user["id"]) if isinstance(auth_user, dict) and auth_user.get("id") != "api-key" else None
    user_name = auth_user.get("name", "Azim") if isinstance(auth_user, dict) else "Azim"
    is_image = ext in IMAGE_EXTENSIONS

    if is_image:
        # ── Image pipeline: GPT-4o caption → thumbnail → MinIO → multimodal store ──
        # 1. Caption with GPT-4o vision
        caption = ""
        try:
            caption = await _caption_image_gpt4o(contents, file.filename or "image.jpg")
        except Exception as e:
            logger.error(f"GPT-4o vision captioning failed: {e}")
            caption = f"[Image: {file.filename} — captioning unavailable]"

        # 2. Generate thumbnail
        thumbnail_bytes = b""
        try:
            thumbnail_bytes = _make_thumbnail(contents)
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")

        # 3. Upload to MinIO
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = (file.filename or "image").replace(" ", "_")
        object_key = f"images/{ts}_{safe_name}"
        thumbnail_key = f"thumbnails/{ts}_{safe_name}.thumb.jpg" if thumbnail_bytes else ""

        mime_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext.lstrip("."), "image/jpeg")
        minio_ok = _upload_to_minio(object_key, contents, mime_type)
        if thumbnail_bytes and minio_ok:
            _upload_to_minio(thumbnail_key, thumbnail_bytes, "image/jpeg")

        # 4. Store in multimodal memory collection
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                store_body = {
                    "type": "image",
                    "user": user_name,
                    "caption": caption,
                    "object_key": object_key if minio_ok else "",
                    "thumbnail_key": thumbnail_key if minio_ok else "",
                    "original_filename": file.filename or "",
                    "content": {
                        "size": len(contents),
                        "mime_type": mime_type,
                        "minio_stored": minio_ok,
                    },
                }
                if user_id:
                    store_body["user_id"] = user_id
                    store_body["uploaded_by"] = user_id
                resp = await client.post(
                    f"{settings.memory_url}/store-multimodal",
                    json=store_body,
                )
                resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Multimodal memory store failed: {e}")

        return {
            "status": "uploaded",
            "filename": file.filename,
            "size": len(contents),
            "type": ext,
            "text_extracted": True,
            "caption": caption,
            "minio_stored": minio_ok,
            "object_key": object_key if minio_ok else None,
            "thumbnail_key": thumbnail_key if minio_ok else None,
        }

    # ── Text document pipeline (PDF, DOCX, TXT) — unchanged ──
    text_content = ""
    if ext == ".txt":
        text_content = contents.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(contents))
            text_content = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            text_content = f"[PDF file: {file.filename} - text extraction failed]"
    elif ext == ".docx":
        try:
            import docx
            doc = docx.Document(io.BytesIO(contents))
            text_content = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}")
            text_content = f"[DOCX file: {file.filename} - text extraction failed]"

    # Ingest extracted text into memory/knowledge
    if text_content.strip():
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                body = {
                    "text": text_content[:50000],
                    "source": f"upload:{file.filename}",
                    "title": file.filename,
                }
                if user_id:
                    body["user_id"] = user_id
                await client.post(
                    f"{settings.memory_url}/ingest",
                    json=body,
                )
            except Exception as e:
                logger.warning(f"Knowledge ingest after upload failed: {e}")

    return {
        "status": "uploaded",
        "filename": file.filename,
        "size": len(contents),
        "type": ext,
        "text_extracted": bool(text_content.strip()),
    }


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
        "learning_engine": settings.learning_engine_url,
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


# ── Audit log (admin only) ─────────────────────────────────
@app.get("/fazle/audit")
async def view_audit_log(
    limit: int = 100,
    action: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """View audit trail. Admin only."""
    logs = get_audit_logs(limit=min(limit, 500), action_filter=action)
    return {"logs": logs}


# ── Persona insights (admin only) ──────────────────────────
@app.get("/fazle/persona/insights")
async def persona_insights(admin: dict = Depends(require_admin)):
    """View persona evolution insights, emotional patterns, contradictions,
    and preference drifts from nightly reflections. Admin only."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                f"{settings.learning_engine_url}/persona/insights",
            )
            resp.raise_for_status()
            log_action(admin, "view_persona_insights", target_type="persona")
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Learning engine error: {e}")
            raise HTTPException(status_code=502, detail="Learning engine unavailable")


@app.post("/fazle/persona/reflect")
async def trigger_reflection(admin: dict = Depends(require_admin)):
    """Trigger a nightly reflection run manually. Admin only."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{settings.learning_engine_url}/reflect",
            )
            resp.raise_for_status()
            log_action(admin, "trigger_reflection", target_type="persona",
                       detail=f"Run ID: {resp.json().get('run_id', 'unknown')}")
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Reflection trigger error: {e}")
            raise HTTPException(status_code=502, detail="Learning engine unavailable")


# ── Phase-5: Autonomy Engine proxy ──────────────────────────

@app.post("/fazle/autonomy/plan", dependencies=[Depends(verify_auth)])
async def autonomy_plan(body: dict):
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{settings.autonomy_engine_url}/autonomy/plan", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomy engine error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unavailable")


@app.post("/fazle/autonomy/execute", dependencies=[Depends(verify_auth)])
async def autonomy_execute(body: dict):
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{settings.autonomy_engine_url}/autonomy/execute", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomy execute error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unavailable")


@app.get("/fazle/autonomy/plans", dependencies=[Depends(verify_auth)])
async def autonomy_plans(limit: int = 20):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.autonomy_engine_url}/autonomy/plans", params={"limit": limit})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomy list error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unavailable")


@app.get("/fazle/autonomy/plan/{plan_id}", dependencies=[Depends(verify_auth)])
async def autonomy_plan_detail(plan_id: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.autonomy_engine_url}/autonomy/plan/{plan_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomy plan detail error: {e}")
            raise HTTPException(status_code=502, detail="Autonomy engine unavailable")


# ── Phase-5: Tool Engine proxy ──────────────────────────────

@app.get("/fazle/tool-engine/list", dependencies=[Depends(verify_auth)])
async def tool_engine_list():
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.tool_engine_url}/tools/list")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Tool engine list error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.post("/fazle/tool-engine/execute", dependencies=[Depends(verify_auth)])
async def tool_engine_execute(body: dict):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.tool_engine_url}/tools/execute", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Tool engine execute error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.put("/fazle/tool-engine/{tool_name}/toggle", dependencies=[Depends(verify_auth)])
async def tool_engine_toggle(tool_name: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(f"{settings.tool_engine_url}/tools/{tool_name}/toggle")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Tool engine toggle error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


# ── Phase-5: Knowledge Graph proxy ──────────────────────────

@app.post("/fazle/knowledge-graph/query", dependencies=[Depends(verify_auth)])
async def kg_query(body: dict):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.knowledge_graph_url}/graph/query", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Knowledge graph query error: {e}")
            raise HTTPException(status_code=502, detail="Knowledge graph unavailable")


@app.get("/fazle/knowledge-graph/stats", dependencies=[Depends(verify_auth)])
async def kg_stats():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.knowledge_graph_url}/graph/stats")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Knowledge graph stats error: {e}")
            raise HTTPException(status_code=502, detail="Knowledge graph unavailable")


@app.get("/fazle/knowledge-graph/nodes", dependencies=[Depends(verify_auth)])
async def kg_nodes(node_type: str = None, limit: int = 50):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {"limit": limit}
            if node_type:
                params["node_type"] = node_type
            resp = await client.get(f"{settings.knowledge_graph_url}/graph/nodes", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Knowledge graph nodes error: {e}")
            raise HTTPException(status_code=502, detail="Knowledge graph unavailable")


@app.get("/fazle/knowledge-graph/context/{node_id}", dependencies=[Depends(verify_auth)])
async def kg_context(node_id: str, depth: int = 2):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.knowledge_graph_url}/graph/context/{node_id}", params={"depth": depth})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Knowledge graph context error: {e}")
            raise HTTPException(status_code=502, detail="Knowledge graph unavailable")


# ── Phase-5: Autonomous Task Runner proxy ───────────────────

@app.post("/fazle/autonomous-tasks", dependencies=[Depends(verify_auth)])
async def create_autonomous_task(body: dict):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.autonomous_runner_url}/tasks/autonomous", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomous runner error: {e}")
            raise HTTPException(status_code=502, detail="Autonomous runner unavailable")


@app.get("/fazle/autonomous-tasks", dependencies=[Depends(verify_auth)])
async def list_autonomous_tasks(status: str = None, limit: int = 50):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            resp = await client.get(f"{settings.autonomous_runner_url}/tasks/autonomous", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomous runner list error: {e}")
            raise HTTPException(status_code=502, detail="Autonomous runner unavailable")


@app.post("/fazle/autonomous-tasks/{task_id}/run", dependencies=[Depends(verify_auth)])
async def run_autonomous_task(task_id: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.autonomous_runner_url}/tasks/autonomous/{task_id}/run")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomous runner run error: {e}")
            raise HTTPException(status_code=502, detail="Autonomous runner unavailable")


@app.post("/fazle/autonomous-tasks/{task_id}/pause", dependencies=[Depends(verify_auth)])
async def pause_autonomous_task(task_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.autonomous_runner_url}/tasks/autonomous/{task_id}/pause")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomous runner pause error: {e}")
            raise HTTPException(status_code=502, detail="Autonomous runner unavailable")


@app.get("/fazle/autonomous-tasks/history", dependencies=[Depends(verify_auth)])
async def autonomous_task_history(task_id: str = None, limit: int = 50):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {"limit": limit}
            if task_id:
                params["task_id"] = task_id
            resp = await client.get(f"{settings.autonomous_runner_url}/tasks/autonomous/history", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Autonomous runner history error: {e}")
            raise HTTPException(status_code=502, detail="Autonomous runner unavailable")


# ── Phase-5: Self-Learning Engine proxy ─────────────────────

@app.post("/fazle/self-learning/analyze", dependencies=[Depends(verify_auth)])
async def self_learning_analyze(body: dict = None):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.self_learning_url}/learning/analyze", json=body or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Self-learning analyze error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unavailable")


@app.post("/fazle/self-learning/improve", dependencies=[Depends(verify_auth)])
async def self_learning_improve(body: dict = None):
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            resp = await client.post(f"{settings.self_learning_url}/learning/improve", json=body or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Self-learning improve error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unavailable")


@app.get("/fazle/self-learning/insights", dependencies=[Depends(verify_auth)])
async def self_learning_insights(limit: int = 50, insight_type: str = None):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {"limit": limit}
            if insight_type:
                params["insight_type"] = insight_type
            resp = await client.get(f"{settings.self_learning_url}/learning/insights", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Self-learning insights error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unavailable")


@app.get("/fazle/self-learning/stats", dependencies=[Depends(verify_auth)])
async def self_learning_stats():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.self_learning_url}/learning/stats")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Self-learning stats error: {e}")
            raise HTTPException(status_code=502, detail="Self-learning engine unavailable")


# ── AI Safety Guardrail Engine proxy ────────────────────────

@app.post("/fazle/guardrail/check", dependencies=[Depends(verify_auth)])
async def guardrail_check(body: dict):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.guardrail_url}/guardrail/check", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail check error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.get("/fazle/guardrail/policies", dependencies=[Depends(verify_auth)])
async def guardrail_policies():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.guardrail_url}/guardrail/policies")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail policies error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.post("/fazle/guardrail/policies")
async def guardrail_create_policy(body: dict, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.guardrail_url}/guardrail/policies", json=body)
            resp.raise_for_status()
            log_action(admin, "create_policy", target_type="guardrail", detail=str(body.get("name", "")))
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail create policy error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.put("/fazle/guardrail/policies/{policy_id}")
async def guardrail_update_policy(policy_id: str, body: dict, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(f"{settings.guardrail_url}/guardrail/policies/{policy_id}", json=body)
            resp.raise_for_status()
            log_action(admin, "update_policy", target_type="guardrail", target_id=policy_id)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail update policy error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.delete("/fazle/guardrail/policies/{policy_id}")
async def guardrail_delete_policy(policy_id: str, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.delete(f"{settings.guardrail_url}/guardrail/policies/{policy_id}")
            resp.raise_for_status()
            log_action(admin, "delete_policy", target_type="guardrail", target_id=policy_id)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail delete policy error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.put("/fazle/guardrail/policies/{policy_id}/toggle")
async def guardrail_toggle_policy(policy_id: str, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(f"{settings.guardrail_url}/guardrail/policies/{policy_id}/toggle")
            resp.raise_for_status()
            log_action(admin, "toggle_policy", target_type="guardrail", target_id=policy_id)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail toggle policy error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.get("/fazle/guardrail/logs")
async def guardrail_logs(limit: int = 50, risk_level: str = None, decision: str = None, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {"limit": limit}
            if risk_level:
                params["risk_level"] = risk_level
            if decision:
                params["decision"] = decision
            resp = await client.get(f"{settings.guardrail_url}/guardrail/logs", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail logs error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.post("/fazle/guardrail/logs/{log_id}/review")
async def guardrail_review(log_id: str, body: dict, admin: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.guardrail_url}/guardrail/logs/{log_id}/review", json=body)
            resp.raise_for_status()
            log_action(admin, "review_action", target_type="guardrail", target_id=log_id,
                       detail=f"Decision: {body.get('decision', '')}")
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail review error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


@app.get("/fazle/guardrail/stats", dependencies=[Depends(verify_auth)])
async def guardrail_stats():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.guardrail_url}/guardrail/stats")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Guardrail stats error: {e}")
            raise HTTPException(status_code=502, detail="Guardrail engine unavailable")


# ── Observability proxy ─────────────────────────────────────

@app.get("/fazle/observability/metrics", dependencies=[Depends(verify_auth)])
async def observability_metrics():
    """Aggregate metrics from Prometheus for dashboard display."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            queries = {
                "api_request_rate": 'sum(rate(http_requests_total{service=~"fazle-.*"}[5m]))',
                "api_latency_p95": 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="fazle-api"}[5m])) by (le))',
                "container_count": 'count(up{job=~"fazle-.*"})',
                "healthy_services": 'sum(up{job=~"fazle-.*"})',
            }
            results = {}
            for key, query in queries.items():
                try:
                    r = await client.get("http://prometheus:9090/api/v1/query", params={"query": query})
                    if r.status_code == 200:
                        data = r.json()
                        result = data.get("data", {}).get("result", [])
                        if result:
                            results[key] = float(result[0].get("value", [0, 0])[1])
                        else:
                            results[key] = 0
                except Exception:
                    results[key] = 0
            return results
        except httpx.HTTPError as e:
            logger.error(f"Observability metrics error: {e}")
            raise HTTPException(status_code=502, detail="Prometheus unavailable")


@app.get("/fazle/observability/services", dependencies=[Depends(verify_auth)])
async def observability_services():
    """Get health status of all Fazle services from Prometheus."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get("http://prometheus:9090/api/v1/query",
                                 params={"query": 'up{job=~"fazle-.*"}'})
            if r.status_code == 200:
                data = r.json()
                services = []
                for result in data.get("data", {}).get("result", []):
                    services.append({
                        "service": result["metric"].get("job", "unknown"),
                        "instance": result["metric"].get("instance", ""),
                        "up": int(result["value"][1]) == 1,
                    })
                return {"services": services}
            return {"services": []}
        except httpx.HTTPError as e:
            logger.error(f"Observability services error: {e}")
            raise HTTPException(status_code=502, detail="Prometheus unavailable")


@app.get("/fazle/observability/container-stats", dependencies=[Depends(verify_auth)])
async def observability_container_stats():
    """Get CPU + memory for all Fazle containers."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            containers = []
            cpu_r = await client.get("http://prometheus:9090/api/v1/query",
                                     params={"query": 'rate(container_cpu_usage_seconds_total{name=~"fazle-.*"}[5m]) * 100'})
            mem_r = await client.get("http://prometheus:9090/api/v1/query",
                                     params={"query": 'container_memory_usage_bytes{name=~"fazle-.*"} / 1024 / 1024'})
            cpu_map = {}
            if cpu_r.status_code == 200:
                for r in cpu_r.json().get("data", {}).get("result", []):
                    name = r["metric"].get("name", "")
                    cpu_map[name] = round(float(r["value"][1]), 2)
            mem_map = {}
            if mem_r.status_code == 200:
                for r in mem_r.json().get("data", {}).get("result", []):
                    name = r["metric"].get("name", "")
                    mem_map[name] = round(float(r["value"][1]), 1)
            all_names = set(list(cpu_map.keys()) + list(mem_map.keys()))
            for name in sorted(all_names):
                containers.append({
                    "name": name,
                    "cpu_percent": cpu_map.get(name, 0),
                    "memory_mb": mem_map.get(name, 0),
                })
            return {"containers": containers}
        except httpx.HTTPError as e:
            logger.error(f"Container stats error: {e}")
            raise HTTPException(status_code=502, detail="Prometheus unavailable")


# ── Workflow Engine proxy ────────────────────────────────────

@app.post("/fazle/workflows/create")
async def workflow_create(body: dict, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.workflow_engine_url}/workflows/create", json=body)
            resp.raise_for_status()
            log_action(user, "create_workflow", target_type="workflow", detail=str(body.get("name", "")))
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow create error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


@app.post("/fazle/workflows/{workflow_id}/start")
async def workflow_start(workflow_id: str, body: dict = None, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(f"{settings.workflow_engine_url}/workflows/{workflow_id}/start",
                                     json=body or {})
            resp.raise_for_status()
            log_action(user, "start_workflow", target_type="workflow", target_id=workflow_id)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow start error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


@app.get("/fazle/workflows", dependencies=[Depends(verify_auth)])
async def workflow_list(status: str = None, limit: int = 50):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            resp = await client.get(f"{settings.workflow_engine_url}/workflows", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow list error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


@app.get("/fazle/workflows/{workflow_id}", dependencies=[Depends(verify_auth)])
async def workflow_status(workflow_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.workflow_engine_url}/workflows/{workflow_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow status error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


@app.post("/fazle/workflows/{workflow_id}/stop")
async def workflow_stop(workflow_id: str, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.workflow_engine_url}/workflows/{workflow_id}/stop")
            resp.raise_for_status()
            log_action(user, "stop_workflow", target_type="workflow", target_id=workflow_id)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow stop error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


@app.get("/fazle/workflows/{workflow_id}/logs", dependencies=[Depends(verify_auth)])
async def workflow_logs(workflow_id: str, limit: int = 100):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.workflow_engine_url}/workflows/{workflow_id}/logs",
                                    params={"limit": limit})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Workflow logs error: {e}")
            raise HTTPException(status_code=502, detail="Workflow engine unavailable")


# ── Tool Marketplace proxy ───────────────────────────────────

@app.get("/fazle/marketplace/tools", dependencies=[Depends(verify_auth)])
async def marketplace_list():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.tool_engine_url}/marketplace/tools")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Marketplace list error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.post("/fazle/marketplace/tools/install")
async def marketplace_install(body: dict, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{settings.tool_engine_url}/marketplace/tools/install", json=body)
            resp.raise_for_status()
            log_action(user, "install_tool", target_type="marketplace", detail=str(body.get("name", "")))
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Marketplace install error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.post("/fazle/marketplace/tools/{tool_name}/enable")
async def marketplace_enable(tool_name: str, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.tool_engine_url}/marketplace/tools/{tool_name}/enable")
            resp.raise_for_status()
            log_action(user, "enable_tool", target_type="marketplace", detail=tool_name)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Marketplace enable error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.post("/fazle/marketplace/tools/{tool_name}/disable")
async def marketplace_disable(tool_name: str, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{settings.tool_engine_url}/marketplace/tools/{tool_name}/disable")
            resp.raise_for_status()
            log_action(user, "disable_tool", target_type="marketplace", detail=tool_name)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Marketplace disable error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")


@app.delete("/fazle/marketplace/tools/{tool_name}")
async def marketplace_remove(tool_name: str, user: dict = Depends(require_admin)):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.delete(f"{settings.tool_engine_url}/marketplace/tools/{tool_name}")
            resp.raise_for_status()
            log_action(user, "remove_tool", target_type="marketplace", detail=tool_name)
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Marketplace remove error: {e}")
            raise HTTPException(status_code=502, detail="Tool engine unavailable")
