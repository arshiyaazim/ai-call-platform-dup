# ============================================================
# Fazle Memory — Long-term memory with vector search (Qdrant)
# Stores: preferences, contacts, knowledge, conversations,
#         images, and documents with embedded images
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from prometheus_fastapi_instrumentator import Instrumentator
import httpx
import logging
import uuid
import hashlib
from typing import Optional, List
import os
import time
from datetime import datetime
from minio import Minio
from urllib.parse import urlparse
import psycopg2
import psycopg2.extras
import psycopg2.pool
import json as json_mod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-memory")


class Settings(BaseSettings):
    vector_db_url: str = "http://qdrant:6333"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    collection_name: str = "fazle_memories"

    # Multimodal collection (text-embedding-3-large for vision captions)
    multimodal_collection: str = "fazle_memories_multimodal"
    multimodal_embedding_dim: int = 3072
    multimodal_embedding_model: str = "text-embedding-3-large"

    # MinIO S3 storage for presigned URLs
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "fazle-multimodal"
    minio_secure: bool = False
    minio_presign_expiry: int = 3600  # 1 hour

    # Embedding provider control: "ollama" (local-first) or "openai"
    embedding_provider: str = "ollama"
    embedding_fallback: str = "openai"

    # Ollama embedding (primary when provider=ollama)
    ollama_url: str = "http://ollama:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_embedding_dim: int = 768

    # PostgreSQL for structured knowledge
    database_url: str = ""

    class Config:
        env_prefix = ""


settings = Settings()

app = FastAPI(title="Fazle Memory — Vector Memory System", version="1.0.0")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── PostgreSQL connection pool ──────────────────────────────
_db_pool: psycopg2.pool.SimpleConnectionPool | None = None


def _get_db_pool() -> psycopg2.pool.SimpleConnectionPool | None:
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    if not settings.database_url:
        logger.warning("DATABASE_URL not set — knowledge table endpoints disabled")
        return None
    try:
        _db_pool = psycopg2.pool.SimpleConnectionPool(1, 5, settings.database_url)
        logger.info("PostgreSQL connection pool created")
        return _db_pool
    except Exception as e:
        logger.error(f"Failed to create PostgreSQL pool: {e}")
        return None


# ── Embedding usage log table ─────────────────────────────────
def _ensure_embedding_log_table():
    pool = _get_db_pool()
    if not pool:
        return
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS embedding_usage_log (
                    id          SERIAL PRIMARY KEY,
                    ts          TIMESTAMPTZ DEFAULT NOW(),
                    provider    VARCHAR(20),
                    fallback_used BOOLEAN DEFAULT FALSE,
                    time_ms     REAL,
                    vector_dim  INT,
                    text_length INT,
                    model       VARCHAR(60)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_embed_log_ts
                ON embedding_usage_log(ts)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_embed_log_provider
                ON embedding_usage_log(provider)
            """)
            conn.commit()
        logger.info("embedding_usage_log table ensured")
    except Exception as e:
        logger.error(f"Failed to ensure embedding_usage_log: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            pool.putconn(conn)


def _log_embedding_usage(provider: str, fallback_used: bool, time_ms: float,
                         vector_dim: int, text_length: int, model: str = None):
    pool = _get_db_pool()
    if not pool:
        return
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO embedding_usage_log "
                "(provider, fallback_used, time_ms, vector_dim, text_length, model) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (provider, fallback_used, round(time_ms, 1), vector_dim, text_length, model),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to log embedding usage: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            pool.putconn(conn)


Instrumentator().instrument(app).expose(app, endpoint="/metrics")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://fazle.iamazim.com,https://iamazim.com").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMORY_TYPES = {"preference", "contact", "knowledge", "personal", "conversation", "image", "document_with_images"}

# Initialize MinIO client
def _get_minio_client() -> Minio | None:
    if not settings.minio_access_key or not settings.minio_secret_key:
        logger.warning("MinIO credentials not configured — presigned URLs disabled")
        return None
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

_minio_client: Minio | None = None

def get_minio() -> Minio | None:
    global _minio_client
    if _minio_client is None:
        _minio_client = _get_minio_client()
    return _minio_client


async def ensure_collection():
    """Create Qdrant collections if they don't exist."""
    collections = [
        (settings.collection_name, settings.embedding_dim),
        (settings.multimodal_collection, settings.multimodal_embedding_dim),
    ]
    async with httpx.AsyncClient(timeout=10.0) as client:
        for coll_name, dim in collections:
            try:
                resp = await client.get(f"{settings.vector_db_url}/collections/{coll_name}")
                if resp.status_code == 200:
                    continue
            except Exception:
                pass

            try:
                await client.put(
                    f"{settings.vector_db_url}/collections/{coll_name}",
                    json={
                        "vectors": {"size": dim, "distance": "Cosine"},
                    },
                )
                logger.info(f"Created collection: {coll_name} (dim={dim})")
            except Exception as e:
                logger.error(f"Failed to create collection {coll_name}: {e}")

        # Create payload indexes on multimodal collection for efficient filtering
        for field_name, field_type in [("type", "keyword"), ("uploaded_by", "keyword")]:
            try:
                await client.put(
                    f"{settings.vector_db_url}/collections/{settings.multimodal_collection}/index",
                    json={"field_name": field_name, "field_schema": field_type},
                )
            except Exception:
                pass  # Index may already exist

        # Create payload indexes for tree memory on main collection
        for field_name, field_type in [("tree_path", "keyword"), ("tree_ancestors", "keyword")]:
            try:
                await client.put(
                    f"{settings.vector_db_url}/collections/{settings.collection_name}/index",
                    json={"field_name": field_name, "field_schema": field_type},
                )
            except Exception:
                pass  # Index may already exist


async def _embed_via_ollama(text: str) -> list[float]:
    """Get embedding from Ollama (nomic-embed-text). Pads/truncates to embedding_dim."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": settings.ollama_embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        embedding = resp.json()["embedding"]
        # Pad or truncate to match expected dimension for Qdrant collection
        if len(embedding) < settings.embedding_dim:
            embedding += [0.0] * (settings.embedding_dim - len(embedding))
        elif len(embedding) > settings.embedding_dim:
            embedding = embedding[:settings.embedding_dim]
        return embedding


async def _embed_via_openai(text: str) -> list[float]:
    """Get embedding from OpenAI text-embedding-3-small (1536-dim)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.embedding_model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector. Provider controlled by EMBEDDING_PROVIDER (default: ollama).
    Falls back to EMBEDDING_FALLBACK if primary fails."""
    provider = settings.embedding_provider.lower()
    fallback = settings.embedding_fallback.lower()
    used_provider = provider
    t0 = time.monotonic()

    # ── Primary provider ──
    try:
        if provider == "ollama":
            vec = await _embed_via_ollama(text)
        else:
            vec = await _embed_via_openai(text)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(f"Embedding OK provider={used_provider} fallback_used=false time_ms={elapsed_ms:.0f}")
        _log_embedding_usage(
            provider=used_provider, fallback_used=False, time_ms=elapsed_ms,
            vector_dim=len(vec), text_length=len(text),
            model="nomic-embed-text" if used_provider == "ollama" else "text-embedding-3-small",
        )
        return vec
    except Exception as e:
        logger.warning(f"Primary embedding failed (provider={provider}): {e}")

    # ── Fallback provider ──
    if fallback and fallback != provider:
        try:
            t0 = time.monotonic()
            if fallback == "ollama":
                vec = await _embed_via_ollama(text)
            else:
                if not settings.openai_api_key:
                    raise RuntimeError("OpenAI API key not configured for fallback")
                vec = await _embed_via_openai(text)
            fallback_used = True
            used_provider = fallback
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(f"Embedding OK provider={used_provider} fallback_used=true time_ms={elapsed_ms:.0f}")
            _log_embedding_usage(
                provider=used_provider, fallback_used=True, time_ms=elapsed_ms,
                vector_dim=len(vec), text_length=len(text),
                model="nomic-embed-text" if used_provider == "ollama" else "text-embedding-3-small",
            )
            return vec
        except Exception as e2:
            logger.error(f"Fallback embedding also failed (provider={fallback}): {e2}")

    raise HTTPException(status_code=502, detail="All embedding services unavailable")


async def get_multimodal_embedding(text: str) -> list[float]:
    """Get embedding vector from OpenAI (text-embedding-3-large, 3072-dim)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.multimodal_embedding_model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]


def generate_presigned_url(object_name: str) -> str | None:
    """Generate a presigned URL for an object in MinIO."""
    client = get_minio()
    if not client:
        return None
    try:
        from datetime import timedelta
        url = client.presigned_get_object(
            settings.minio_bucket,
            object_name,
            expires=timedelta(seconds=settings.minio_presign_expiry),
        )
        return url
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL for {object_name}: {e}")
        return None


# ── Knowledge fact versioning columns ───────────────────────
def _ensure_knowledge_fact_columns():
    """Add fact versioning columns to fazle_owner_knowledge (idempotent)."""
    pool = _get_db_pool()
    if not pool:
        return
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS fact_id VARCHAR(300)")
            cur.execute("ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1")
            cur.execute("ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
            cur.execute("ALTER TABLE fazle_owner_knowledge ADD COLUMN IF NOT EXISTS supersedes UUID")
            # Backfill old rows
            cur.execute("""
                UPDATE fazle_owner_knowledge
                SET    fact_id = category || ':' || key
                WHERE  fact_id IS NULL
            """)
            cur.execute("ALTER TABLE fazle_owner_knowledge ALTER COLUMN fact_id SET NOT NULL")
            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_fact_id ON fazle_owner_knowledge(fact_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_active ON fazle_owner_knowledge(is_active)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_fact_active ON fazle_owner_knowledge(fact_id, is_active)")
            # Partial unique: one active row per fact_id
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_fact_active
                ON fazle_owner_knowledge(fact_id) WHERE is_active = TRUE
            """)
            conn.commit()
        logger.info("Knowledge fact versioning columns ensured")
    except Exception as e:
        logger.warning(f"knowledge_fact_columns migration: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            pool.putconn(conn)


@app.on_event("startup")
async def startup():
    _ensure_embedding_log_table()
    _ensure_knowledge_fact_columns()
    await ensure_collection()


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-memory", "timestamp": datetime.utcnow().isoformat()}


# ── Store memory ────────────────────────────────────────────
class StoreRequest(BaseModel):
    type: str = Field(..., description="Memory type")
    user: str = "Azim"
    content: dict = Field(default_factory=dict)
    text: str = ""
    user_id: Optional[str] = Field(None, description="Owner user ID for privacy isolation")


@app.post("/store")
async def store_memory(request: StoreRequest):
    """Store a memory with vector embedding."""
    if request.type not in MEMORY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid memory type. Must be one of: {MEMORY_TYPES}")

    text_to_embed = request.text or str(request.content)
    if not text_to_embed.strip():
        raise HTTPException(status_code=400, detail="No text content to store")

    try:
        embedding = await get_embedding(text_to_embed)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    # Generate deterministic ID from content for deduplication
    content_hash = hashlib.sha256(text_to_embed.encode()).hexdigest()[:16]
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

    payload = {
        "type": request.type,
        "user": request.user,
        "content": request.content,
        "text": text_to_embed,
        "created_at": datetime.utcnow().isoformat(),
    }
    if request.user_id:
        payload["user_id"] = request.user_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points",
                json={
                    "points": [
                        {
                            "id": point_id,
                            "vector": embedding,
                            "payload": payload,
                        }
                    ]
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Qdrant store failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    return {"status": "stored", "id": point_id, "type": request.type}


# ── Search memories ─────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    memory_type: Optional[str] = None
    limit: int = 5
    user_id: Optional[str] = Field(None, description="Filter memories by owner user ID")


@app.post("/search")
async def search_memories(request: SearchRequest):
    """Semantic search across memories."""
    try:
        embedding = await get_embedding(request.query)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    search_body: dict = {
        "vector": embedding,
        "limit": request.limit,
        "with_payload": True,
    }

    # Build filter conditions
    filter_conditions = []
    if request.memory_type and request.memory_type in MEMORY_TYPES:
        filter_conditions.append({"key": "type", "match": {"value": request.memory_type}})
    if request.user_id:
        filter_conditions.append({"key": "user_id", "match": {"value": request.user_id}})
    if filter_conditions:
        search_body["filter"] = {"must": filter_conditions}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/search",
                json=search_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    results = []
    for hit in data.get("result", []):
        payload = hit.get("payload", {})
        results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0),
            "type": payload.get("type"),
            "user": payload.get("user"),
            "content": payload.get("content"),
            "text": payload.get("text"),
            "created_at": payload.get("created_at"),
        })

    return {"results": results, "count": len(results)}


# ── Knowledge ingestion ─────────────────────────────────────
class IngestRequest(BaseModel):
    text: str
    source: str = "manual"
    title: str = ""


@app.post("/ingest")
async def ingest_knowledge(request: IngestRequest):
    """Ingest a document into the knowledge base. Splits into chunks."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="No text to ingest")

    # Split text into chunks of ~500 chars with overlap
    chunks = _chunk_text(request.text, chunk_size=500, overlap=50)
    stored = 0

    for i, chunk in enumerate(chunks):
        try:
            embedding = await get_embedding(chunk)
        except Exception as e:
            logger.warning(f"Embedding failed for chunk {i}: {e}")
            continue

        point_id = str(uuid.uuid4())
        payload = {
            "type": "knowledge",
            "user": "system",
            "content": {"source": request.source, "title": request.title, "chunk_index": i},
            "text": chunk,
            "created_at": datetime.utcnow().isoformat(),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.put(
                    f"{settings.vector_db_url}/collections/{settings.collection_name}/points",
                    json={"points": [{"id": point_id, "vector": embedding, "payload": payload}]},
                )
                stored += 1
            except Exception as e:
                logger.warning(f"Failed to store chunk {i}: {e}")

    return {"status": "ingested", "chunks_stored": stored, "total_chunks": len(chunks)}


# ── List memories by type ───────────────────────────────────
@app.get("/memories")
async def list_memories(memory_type: Optional[str] = None, limit: int = 20, offset: int = 0):
    """List stored memories, optionally filtered by type."""
    scroll_body: dict = {
        "limit": limit,
        "offset": offset,
        "with_payload": True,
    }

    if memory_type and memory_type in MEMORY_TYPES:
        scroll_body["filter"] = {
            "must": [{"key": "type", "match": {"value": memory_type}}]
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/scroll",
                json=scroll_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Qdrant scroll failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    points = data.get("result", {}).get("points", [])
    return {
        "memories": [
            {
                "id": p.get("id"),
                "type": p.get("payload", {}).get("type"),
                "text": p.get("payload", {}).get("text"),
                "content": p.get("payload", {}).get("content"),
                "created_at": p.get("payload", {}).get("created_at"),
            }
            for p in points
        ],
        "count": len(points),
    }


# ── Delete memory ───────────────────────────────────────────
@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a specific memory by ID."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/delete",
                json={"points": [memory_id]},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Qdrant delete failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")
    return {"status": "deleted", "id": memory_id}


# ── Store multimodal memory ─────────────────────────────────
class StoreMultimodalRequest(BaseModel):
    type: str = Field(..., description="Memory type (image / document_with_images)")
    user: str = "Azim"
    caption: str = Field(..., description="GPT-4o generated caption / description")
    object_key: str = Field(..., description="MinIO object key for the original file")
    thumbnail_key: str = Field("", description="MinIO object key for the thumbnail")
    original_filename: str = ""
    content: dict = Field(default_factory=dict)
    user_id: Optional[str] = None
    uploaded_by: Optional[str] = None


@app.post("/store-multimodal")
async def store_multimodal_memory(request: StoreMultimodalRequest):
    """Store a multimodal memory with text-embedding-3-large vector."""
    if request.type not in {"image", "document_with_images"}:
        raise HTTPException(status_code=400, detail="Type must be 'image' or 'document_with_images'")

    if not request.caption.strip():
        raise HTTPException(status_code=400, detail="Caption is required for multimodal storage")

    try:
        embedding = await get_multimodal_embedding(request.caption)
    except Exception as e:
        logger.error(f"Multimodal embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    content_hash = hashlib.sha256(
        f"{request.object_key}:{request.caption[:200]}".encode()
    ).hexdigest()[:16]
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

    payload = {
        "type": request.type,
        "user": request.user,
        "caption": request.caption,
        "text": request.caption,
        "object_key": request.object_key,
        "thumbnail_key": request.thumbnail_key,
        "original_filename": request.original_filename,
        "content": request.content,
        "created_at": datetime.utcnow().isoformat(),
    }
    if request.user_id:
        payload["user_id"] = request.user_id
    if request.uploaded_by:
        payload["uploaded_by"] = request.uploaded_by

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(
                f"{settings.vector_db_url}/collections/{settings.multimodal_collection}/points",
                json={
                    "points": [
                        {
                            "id": point_id,
                            "vector": embedding,
                            "payload": payload,
                        }
                    ]
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Qdrant multimodal store failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    return {"status": "stored", "id": point_id, "type": request.type, "collection": settings.multimodal_collection}


# ── Search multimodal memories ──────────────────────────────
class SearchMultimodalRequest(BaseModel):
    query: str
    limit: int = 5
    user_id: Optional[str] = None
    memory_type: Optional[str] = None


@app.post("/search-multimodal")
async def search_multimodal_memories(request: SearchMultimodalRequest):
    """Semantic search across multimodal memories (images, documents with images)."""
    try:
        embedding = await get_multimodal_embedding(request.query)
    except Exception as e:
        logger.error(f"Multimodal embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    search_body: dict = {
        "vector": embedding,
        "limit": request.limit,
        "with_payload": True,
    }

    filter_conditions = []
    if request.memory_type and request.memory_type in {"image", "document_with_images"}:
        filter_conditions.append({"key": "type", "match": {"value": request.memory_type}})
    if request.user_id:
        filter_conditions.append({"key": "user_id", "match": {"value": request.user_id}})
    if filter_conditions:
        search_body["filter"] = {"must": filter_conditions}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.multimodal_collection}/points/search",
                json=search_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Qdrant multimodal search failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    results = []
    for hit in data.get("result", []):
        p = hit.get("payload", {})
        # Generate presigned URLs for the images
        image_url = generate_presigned_url(p.get("object_key", "")) if p.get("object_key") else None
        thumbnail_url = generate_presigned_url(p.get("thumbnail_key", "")) if p.get("thumbnail_key") else None
        results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0),
            "type": p.get("type"),
            "user": p.get("user"),
            "caption": p.get("caption", ""),
            "text": p.get("text", p.get("caption", "")),
            "object_key": p.get("object_key", ""),
            "thumbnail_key": p.get("thumbnail_key", ""),
            "original_filename": p.get("original_filename", ""),
            "image_url": image_url,
            "thumbnail_url": thumbnail_url,
            "content": p.get("content", {}),
            "created_at": p.get("created_at"),
        })

    return {"results": results, "count": len(results)}


# ── Unified search (text + multimodal) ──────────────────────
@app.post("/search-all")
async def search_all_memories(request: SearchRequest):
    """Search across both text and multimodal collections, merging results by score."""
    # Search text collection
    text_results = []
    try:
        text_embedding = await get_embedding(request.query)
        text_search_body: dict = {
            "vector": text_embedding,
            "limit": request.limit,
            "with_payload": True,
        }
        text_filters = []
        if request.memory_type and request.memory_type in MEMORY_TYPES:
            text_filters.append({"key": "type", "match": {"value": request.memory_type}})
        if request.user_id:
            text_filters.append({"key": "user_id", "match": {"value": request.user_id}})
        if text_filters:
            text_search_body["filter"] = {"must": text_filters}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/search",
                json=text_search_body,
            )
            resp.raise_for_status()
            for hit in resp.json().get("result", []):
                p = hit.get("payload", {})
                text_results.append({
                    "id": hit.get("id"), "score": hit.get("score", 0),
                    "type": p.get("type"), "user": p.get("user"),
                    "text": p.get("text"), "content": p.get("content"),
                    "created_at": p.get("created_at"), "collection": "text",
                })
    except Exception as e:
        logger.warning(f"Text search failed: {e}")

    # Search multimodal collection
    mm_results = []
    try:
        mm_embedding = await get_multimodal_embedding(request.query)
        mm_search_body: dict = {
            "vector": mm_embedding,
            "limit": request.limit,
            "with_payload": True,
        }
        mm_filters = []
        if request.user_id:
            mm_filters.append({"key": "user_id", "match": {"value": request.user_id}})
        if mm_filters:
            mm_search_body["filter"] = {"must": mm_filters}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.multimodal_collection}/points/search",
                json=mm_search_body,
            )
            resp.raise_for_status()
            for hit in resp.json().get("result", []):
                p = hit.get("payload", {})
                image_url = generate_presigned_url(p.get("object_key", "")) if p.get("object_key") else None
                thumbnail_url = generate_presigned_url(p.get("thumbnail_key", "")) if p.get("thumbnail_key") else None
                mm_results.append({
                    "id": hit.get("id"), "score": hit.get("score", 0),
                    "type": p.get("type"), "user": p.get("user"),
                    "text": p.get("caption", p.get("text", "")),
                    "caption": p.get("caption", ""),
                    "object_key": p.get("object_key", ""),
                    "image_url": image_url, "thumbnail_url": thumbnail_url,
                    "original_filename": p.get("original_filename", ""),
                    "content": p.get("content", {}),
                    "created_at": p.get("created_at"), "collection": "multimodal",
                })
    except Exception as e:
        logger.warning(f"Multimodal search failed: {e}")

    # Merge and sort by score
    combined = text_results + mm_results
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"results": combined[:request.limit], "count": len(combined[:request.limit])}


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


# ── Personal Facts — Structured user data ───────────────────
PERSONAL_CATEGORIES = {
    "preference", "contact", "project", "schedule",
    "relationship", "health", "financial", "habit",
}


class PersonalFactRequest(BaseModel):
    category: str = Field(..., description="Fact category (preference, contact, project, etc.)")
    key: str = Field(..., description="Fact key (e.g., 'favorite_color')")
    value: str = Field(..., description="Fact value (e.g., 'blue')")
    user_id: Optional[str] = None


@app.post("/personal/store")
async def store_personal_fact(request: PersonalFactRequest):
    """Store a structured personal fact about the user."""
    if request.category not in PERSONAL_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {PERSONAL_CATEGORIES}",
        )

    text = f"Personal {request.category}: {request.key} is {request.value}"
    try:
        embedding = await get_embedding(text)
    except Exception as e:
        logger.error(f"Embedding failed for personal fact: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    content_hash = hashlib.sha256(
        f"personal:{request.category}:{request.key}".encode()
    ).hexdigest()[:16]
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

    payload = {
        "type": "personal",
        "user": "Azim",
        "category": request.category,
        "key": request.key,
        "value": request.value,
        "text": text,
        "content": {
            "category": request.category,
            "key": request.key,
            "value": request.value,
        },
        "created_at": datetime.utcnow().isoformat(),
    }
    if request.user_id:
        payload["user_id"] = request.user_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points",
                json={"points": [{"id": point_id, "vector": embedding, "payload": payload}]},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Personal fact store failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    return {"status": "stored", "id": point_id, "category": request.category, "key": request.key}


class PersonalSearchRequest(BaseModel):
    query: str = ""
    category: Optional[str] = None
    user_id: Optional[str] = None
    limit: int = 10


@app.post("/personal/search")
async def search_personal_facts(request: PersonalSearchRequest):
    """Search personal facts by semantic query and/or category."""
    if not request.query.strip() and not request.category:
        raise HTTPException(status_code=400, detail="Provide a query or category")

    search_text = request.query or f"personal {request.category}"
    try:
        embedding = await get_embedding(search_text)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    filter_conditions = [{"key": "type", "match": {"value": "personal"}}]
    if request.category and request.category in PERSONAL_CATEGORIES:
        filter_conditions.append({"key": "category", "match": {"value": request.category}})
    if request.user_id:
        filter_conditions.append({"key": "user_id", "match": {"value": request.user_id}})

    search_body = {
        "vector": embedding,
        "limit": request.limit,
        "with_payload": True,
        "filter": {"must": filter_conditions},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/search",
                json=search_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Personal fact search failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    results = []
    for hit in data.get("result", []):
        p = hit.get("payload", {})
        results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0),
            "category": p.get("category", ""),
            "key": p.get("key", ""),
            "value": p.get("value", ""),
            "text": p.get("text", ""),
            "created_at": p.get("created_at"),
        })

    return {"results": results, "count": len(results)}


# ── Metrics ─────────────────────────────────────────────────
@app.get("/metrics/collections")
async def collection_metrics():
    """Report collection sizes for monitoring."""
    metrics = {}
    for coll in [settings.collection_name, settings.multimodal_collection]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{settings.vector_db_url}/collections/{coll}")
                if resp.status_code == 200:
                    info = resp.json().get("result", {})
                    metrics[coll] = {
                        "points_count": info.get("points_count", 0),
                        "vectors_count": info.get("vectors_count", 0),
                    }
            except Exception:
                metrics[coll] = {"error": "unavailable"}
    return metrics


# ── Embedding analytics ─────────────────────────────────────
@app.get("/analytics/embedding-usage")
async def analytics_embedding_usage(days: int = 7):
    """Embedding usage analytics with provider breakdown and cost estimation."""
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")
    conn = None
    try:
        conn = pool.getconn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            d = int(days)
            cur.execute("""
                SELECT
                    COUNT(*) as total_requests,
                    COUNT(*) FILTER (WHERE provider = 'ollama') as ollama_count,
                    COUNT(*) FILTER (WHERE provider = 'openai') as openai_count,
                    COUNT(*) FILTER (WHERE fallback_used = TRUE) as fallback_count,
                    ROUND(AVG(time_ms)::numeric, 1) as avg_time_ms,
                    ROUND(AVG(time_ms) FILTER (WHERE provider = 'ollama')::numeric, 1) as avg_time_ollama,
                    ROUND(AVG(time_ms) FILTER (WHERE provider = 'openai')::numeric, 1) as avg_time_openai,
                    COALESCE(SUM(text_length), 0) as total_text_chars
                FROM embedding_usage_log
                WHERE ts > NOW() - INTERVAL '%s days'
            """ % d)
            summary = cur.fetchone()

            cur.execute("""
                SELECT model, COUNT(*) as count
                FROM embedding_usage_log
                WHERE ts > NOW() - INTERVAL '%s days'
                GROUP BY model ORDER BY count DESC
            """ % d)
            model_rows = cur.fetchall()

        total = summary["total_requests"] or 0
        openai_count = summary["openai_count"] or 0
        # Estimate: ~1 token per 4 chars for cost calc
        est_openai_tokens = int(summary["total_text_chars"] or 0) // 4 if openai_count > 0 else 0
        embed_cost = (est_openai_tokens / 1_000_000) * 0.02  # text-embedding-3-small rate

        fallback_count = summary["fallback_count"] or 0
        fallback_rate = f"{(fallback_count / total * 100):.1f}%" if total > 0 else "0%"

        return {
            "period_days": days,
            "total_requests": total,
            "providers": {
                "ollama": summary["ollama_count"] or 0,
                "openai": openai_count,
            },
            "fallback_rate": fallback_rate,
            "avg_time_ms": float(summary["avg_time_ms"] or 0),
            "avg_time_by_provider": {
                "ollama": float(summary["avg_time_ollama"] or 0),
                "openai": float(summary["avg_time_openai"] or 0),
            },
            "models": {r["model"]: r["count"] for r in model_rows},
            "cost_estimation": {
                "total_usd": round(embed_cost, 6),
                "ollama_cost": 0.0,
                "note": "Ollama embeddings are free; OpenAI cost estimated from text-embedding-3-small rates",
            },
            "total_text_chars": summary["total_text_chars"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            pool.putconn(conn)


# ── Owner Knowledge — Structured PostgreSQL storage ─────────

KNOWLEDGE_CATEGORIES = {
    "personal", "business", "political", "family", "daily",
    "social", "religious", "financial", "health", "tech",
    "preference", "education", "ideology",
}

# ── Fact type mapping ───────────────────────────────────────
_FACT_TYPE_ALIASES = {
    "name": "owner_name", "full_name": "owner_name",
    "company": "company_name", "business_name": "company_name",
    "address": "company_address", "office_address": "company_address",
    "service": "service_type", "services": "service_type",
    "price": "pricing", "rate": "pricing", "cost": "pricing",
}


def map_field_to_fact_id(category: str, key: str) -> str:
    """Normalize category:key into a canonical fact_id."""
    normalized_key = key.strip().lower().replace(" ", "_")
    normalized_key = _FACT_TYPE_ALIASES.get(normalized_key, normalized_key)
    return f"{category.strip().lower()}:{normalized_key}"


def _versioned_upsert(conn, category: str, subcategory: str, key: str,
                      value: str, language: str, confidence: float,
                      source: str, metadata: dict) -> tuple:
    """Insert new knowledge fact with version tracking.
    Returns (id, action) where action is 'created', 'updated', or 'skipped_duplicate'.
    """
    fact_id = map_field_to_fact_id(category, key)
    with conn.cursor() as cur:
        # Find current active fact
        cur.execute(
            "SELECT id, value, version FROM fazle_owner_knowledge "
            "WHERE fact_id = %s AND is_active = TRUE LIMIT 1",
            (fact_id,),
        )
        existing = cur.fetchone()

        # Conflict safety: skip if value unchanged
        if existing and existing[1] == value:
            return str(existing[0]), "skipped_duplicate"

        old_id = existing[0] if existing else None
        old_ver = existing[2] if existing else 0

        # Deactivate old version
        if old_id:
            cur.execute(
                "UPDATE fazle_owner_knowledge SET is_active = FALSE, updated_at = NOW() "
                "WHERE id = %s", (old_id,),
            )

        # Insert new active version
        cur.execute(
            "INSERT INTO fazle_owner_knowledge "
            "(category, subcategory, key, value, language, confidence, source, metadata, "
            " fact_id, version, is_active, supersedes) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s) "
            "RETURNING id",
            (category, subcategory, key, value, language, confidence, source,
             json_mod.dumps(metadata), fact_id, old_ver + 1, old_id),
        )
        new_id = cur.fetchone()[0]
        action = "updated" if old_id else "created"
        return str(new_id), action


class KnowledgeStoreRequest(BaseModel):
    category: str = Field(..., description="Knowledge category")
    subcategory: str = ""
    key: str = Field(..., description="Knowledge key (e.g., 'full_name')")
    value: str = Field(..., description="Knowledge value")
    language: str = "en"
    confidence: float = 1.0
    source: str = "owner_chat"
    metadata: dict = Field(default_factory=dict)


@app.post("/knowledge/store")
async def store_knowledge(request: KnowledgeStoreRequest):
    """Store structured owner knowledge in PostgreSQL."""
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")

    if request.category not in KNOWLEDGE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {KNOWLEDGE_CATEGORIES}",
        )

    conn = pool.getconn()
    try:
        result_id, action = _versioned_upsert(
            conn,
            category=request.category,
            subcategory=request.subcategory,
            key=request.key,
            value=request.value,
            language=request.language,
            confidence=request.confidence,
            source=request.source,
            metadata=request.metadata,
        )
        conn.commit()
        fact_id = map_field_to_fact_id(request.category, request.key)
        logger.info(f"fact_{action} fact_id={fact_id} id={result_id}")
    except Exception as e:
        conn.rollback()
        logger.error(f"Knowledge store failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to store knowledge")
    finally:
        pool.putconn(conn)

    # Also store in Qdrant for vector search
    text_to_embed = f"Azim's {request.category} — {request.key}: {request.value}"
    try:
        embedding = await get_embedding(text_to_embed)
        content_hash = hashlib.sha256(
            f"knowledge:{request.category}:{request.key}".encode()
        ).hexdigest()[:16]
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.put(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points",
                json={
                    "points": [{
                        "id": point_id,
                        "vector": embedding,
                        "payload": {
                            "type": "knowledge",
                            "user": "owner",
                            "category": request.category,
                            "key": request.key,
                            "text": text_to_embed,
                            "content": {"category": request.category, "key": request.key, "value": request.value},
                            "created_at": datetime.utcnow().isoformat(),
                        },
                    }],
                },
            )
    except Exception as e:
        logger.warning(f"Qdrant mirror for knowledge failed (non-fatal): {e}")

    return {
        "status": "stored",
        "id": str(result_id),
        "category": request.category,
        "key": request.key,
        "fact_id": map_field_to_fact_id(request.category, request.key),
        "action": action,
    }


class KnowledgeSearchRequest(BaseModel):
    query: str = ""
    category: Optional[str] = None
    limit: int = 20


@app.post("/knowledge/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    """Search owner knowledge from PostgreSQL by category or text match."""
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            conditions = []
            params: list = []
            if request.category:
                conditions.append("category = %s")
                params.append(request.category)
            if request.query:
                conditions.append("(key ILIKE %s OR value ILIKE %s)")
                like = f"%{request.query}%"
                params.extend([like, like])
            # Only return active facts (single source of truth)
            conditions.append("is_active = TRUE")
            where = f"WHERE {' AND '.join(conditions)}"
            cur.execute(
                f"SELECT id, category, subcategory, key, value, language, confidence, source, metadata, created_at "
                f"FROM fazle_owner_knowledge {where} ORDER BY updated_at DESC LIMIT %s",
                params + [request.limit],
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        raise HTTPException(status_code=500, detail="Knowledge search failed")
    finally:
        pool.putconn(conn)

    results = []
    for row in rows:
        results.append({
            "id": str(row[0]),
            "category": row[1],
            "subcategory": row[2],
            "key": row[3],
            "value": row[4],
            "language": row[5],
            "confidence": row[6],
            "source": row[7],
            "metadata": row[8] if isinstance(row[8], dict) else {},
            "created_at": row[9].isoformat() if row[9] else None,
        })

    return {"results": results, "count": len(results)}


@app.get("/knowledge/categories")
async def list_knowledge_categories():
    """List knowledge categories with counts."""
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, COUNT(*) as count FROM fazle_owner_knowledge "
                "WHERE is_active = TRUE GROUP BY category ORDER BY count DESC"
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Knowledge categories query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to list categories")
    finally:
        pool.putconn(conn)

    return {"categories": [{"category": r[0], "count": r[1]} for r in rows]}


@app.get("/knowledge/history")
async def knowledge_history(fact_id: str, limit: int = 50):
    """Return all versions of a fact (active + inactive) for audit."""
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")

    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, category, subcategory, key, value, language, confidence, "
                "       source, metadata, fact_id, version, is_active, supersedes, "
                "       created_at, updated_at "
                "FROM fazle_owner_knowledge "
                "WHERE fact_id = %s "
                "ORDER BY version DESC LIMIT %s",
                (fact_id, limit),
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Knowledge history query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")
    finally:
        pool.putconn(conn)

    versions = []
    for r in rows:
        versions.append({
            "id": str(r["id"]),
            "version": r["version"],
            "is_active": r["is_active"],
            "value": r["value"],
            "confidence": r["confidence"],
            "source": r["source"],
            "supersedes": str(r["supersedes"]) if r["supersedes"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })

    return {
        "fact_id": fact_id,
        "total_versions": len(versions),
        "current": versions[0] if versions else None,
        "history": versions,
    }


# ── Smart Retrieval & Context Optimization ──────────────────

# Category importance weights
_CATEGORY_WEIGHT = {
    "business": 3, "personal": 3,
    "financial": 2, "health": 2, "tech": 2,
    "family": 1, "education": 1, "preference": 1,
    "social": 0, "daily": 0, "political": 0,
    "religious": 0, "ideology": 0,
}

# Source priority weights
_SOURCE_WEIGHT = {
    "owner": 5, "owner_chat": 4, "manual": 4,
    "admin": 3, "api": 2, "system": 1,
    "auto_extract": 1,
}


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a query string."""
    stop_words = {
        "the", "is", "a", "an", "of", "in", "to", "for", "and", "or", "what",
        "which", "how", "who", "where", "when", "do", "does", "can", "your",
        "my", "our", "their", "this", "that", "it", "are", "was", "were", "be",
        "been", "have", "has", "had", "will", "would", "could", "should",
        "ki", "kি", "কি", "কে", "তা", "এটা", "সেটা", "আমার", "আপনার",
        "তোমার", "হলো", "করে", "এবং", "বা", "না", "হ্যাঁ",
    }
    words = query.lower().replace("?", " ").replace(".", " ").replace(",", " ").split()
    return [w.strip() for w in words if len(w) > 1 and w not in stop_words]


def _score_fact(fact: dict, keywords: list[str], now_ts: float) -> float:
    """Score a knowledge fact for relevance and priority."""
    score = 0.0

    # Recency bonus (max 3 points, decays over 7 days)
    updated_at = fact.get("updated_at")
    if updated_at:
        try:
            if isinstance(updated_at, str):
                from datetime import datetime as _dt
                ts = _dt.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            else:
                ts = updated_at.timestamp()
            age_days = (now_ts - ts) / 86400
            if age_days < 1:
                score += 3.0
            elif age_days < 7:
                score += 2.0
            elif age_days < 30:
                score += 1.0
        except Exception:
            pass

    # Category importance
    category = fact.get("category", "")
    score += _CATEGORY_WEIGHT.get(category, 0)

    # Source priority
    source = fact.get("source", "")
    score += _SOURCE_WEIGHT.get(source, 0)

    # Confidence boost
    confidence = fact.get("confidence", 1.0)
    if confidence and confidence >= 0.9:
        score += 1.0

    # Keyword match boost (check fact_id, category, key, value)
    if keywords:
        searchable = " ".join([
            fact.get("fact_id", ""),
            fact.get("category", ""),
            fact.get("key", ""),
            fact.get("value", ""),
        ]).lower()
        matches = sum(1 for kw in keywords if kw in searchable)
        score += min(matches * 2.0, 6.0)  # max 6 from keyword matching

    return round(score, 1)


def _build_clean_context(facts: list[dict]) -> str:
    """Format scored facts into a clean context string for LLM injection."""
    if not facts:
        return ""
    lines = ["FACTS:"]
    seen = set()
    for f in facts:
        key = f.get("key", "")
        value = f.get("value", "")
        if not key or not value:
            continue
        # Deduplicate by key
        dedup = key.lower()
        if dedup in seen:
            continue
        seen.add(dedup)
        # Format: human-readable key
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines) if len(lines) > 1 else ""


@app.get("/knowledge/retrieve")
async def knowledge_retrieve(query: str, limit: int = 10, category: str = None):
    """Smart knowledge retrieval with scoring, keyword matching, and clean context.
    Returns only active facts, scored and ranked, with formatted context.
    """
    pool = _get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not configured")

    keywords = _extract_keywords(query)
    now_ts = time.time()
    limit = min(max(limit, 1), 20)

    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Fetch all active facts (filtered by category if provided)
            conditions = ["is_active = TRUE"]
            params: list = []
            if category:
                conditions.append("category = %s")
                params.append(category)
            # Keyword-based filtering: if keywords exist, filter to relevant rows
            if keywords:
                kw_conditions = []
                for kw in keywords[:8]:  # cap at 8 keywords
                    kw_conditions.append("(key ILIKE %s OR value ILIKE %s OR fact_id ILIKE %s)")
                    like = f"%{kw}%"
                    params.extend([like, like, like])
                conditions.append(f"({' OR '.join(kw_conditions)})")

            where = f"WHERE {' AND '.join(conditions)}"
            cur.execute(
                f"SELECT id, category, subcategory, key, value, language, confidence, "
                f"       source, metadata, fact_id, version, is_active, "
                f"       created_at, updated_at "
                f"FROM fazle_owner_knowledge {where} "
                f"ORDER BY updated_at DESC LIMIT 50",
                params,
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Smart retrieval query failed: {e}")
        raise HTTPException(status_code=500, detail="Retrieval failed")
    finally:
        pool.putconn(conn)

    # Score and rank
    scored = []
    for row in rows:
        fact = dict(row)
        fact["score"] = _score_fact(fact, keywords, now_ts)
        scored.append(fact)
    scored.sort(key=lambda f: f["score"], reverse=True)

    # Priority order: owner facts → business → rest (already handled by scoring)
    selected = scored[:limit]
    skipped = scored[limit:]

    # Build clean context
    context = _build_clean_context(selected)

    # Debug logging
    logger.info(
        f"Smart retrieval: query='{query[:60]}' keywords={keywords[:5]} "
        f"matched={len(rows)} selected={len(selected)} skipped={len(skipped)}"
    )
    for f in selected[:5]:
        logger.debug(f"  SELECTED: fact_id={f.get('fact_id')} score={f['score']} key={f.get('key')}")
    for f in skipped[:3]:
        logger.debug(f"  SKIPPED: fact_id={f.get('fact_id')} score={f['score']} key={f.get('key')}")

    # Response
    facts_out = []
    for f in selected:
        facts_out.append({
            "fact_id": f.get("fact_id"),
            "category": f.get("category"),
            "key": f.get("key"),
            "value": f.get("value"),
            "version": f.get("version"),
            "confidence": f.get("confidence"),
            "source": f.get("source"),
            "score": f["score"],
            "updated_at": f["updated_at"].isoformat() if f.get("updated_at") else None,
        })

    return {
        "query": query,
        "keywords": keywords,
        "total_matched": len(rows),
        "selected_count": len(selected),
        "facts": facts_out,
        "context": context,
    }


# ══════════════════════════════════════════════════════════════
# Tree Memory System — Hierarchical knowledge with tree paths
# Stores memories tagged with tree paths like:
#   azim/business/al-aqsa/services
#   azim/family/wife/preferences
# Enables browsing & searching within branches of the tree.
# ══════════════════════════════════════════════════════════════

def _tree_ancestors(tree_path: str) -> list[str]:
    """Build ancestor list for a tree path.
    'azim/business/al-aqsa' → ['azim', 'azim/business', 'azim/business/al-aqsa']
    """
    parts = [p.strip() for p in tree_path.strip("/").split("/") if p.strip()]
    ancestors = []
    for i in range(1, len(parts) + 1):
        ancestors.append("/".join(parts[:i]))
    return ancestors


class TreeStoreRequest(BaseModel):
    tree_path: str = Field(..., description="Tree path e.g. 'business/al-aqsa/services'")
    text: str = Field(..., description="Memory content text")
    content: dict = Field(default_factory=dict, description="Optional structured content")
    user: str = "Azim"
    source: str = "manual"
    language: str = "en"


class TreeSearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query")
    tree_path: Optional[str] = Field(None, description="Filter to this branch (prefix match)")
    limit: int = 10


class TreeBulkStoreRequest(BaseModel):
    items: List[TreeStoreRequest]


@app.post("/tree/store")
async def tree_store(request: TreeStoreRequest):
    """Store a memory tagged with a tree path."""
    path = request.tree_path.strip("/").lower()
    if not path:
        raise HTTPException(status_code=400, detail="tree_path is required")
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    try:
        embedding = await get_embedding(request.text)
    except Exception as e:
        logger.error(f"Tree store embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    content_hash = hashlib.sha256(f"tree:{path}:{request.text[:200]}".encode()).hexdigest()[:16]
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))

    ancestors = _tree_ancestors(path)

    payload = {
        "type": "tree_memory",
        "tree_path": path,
        "tree_ancestors": ancestors,
        "tree_depth": len(ancestors),
        "user": request.user,
        "text": request.text,
        "content": request.content,
        "source": request.source,
        "language": request.language,
        "created_at": datetime.utcnow().isoformat(),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.put(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points",
                json={"points": [{"id": point_id, "vector": embedding, "payload": payload}]},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Tree store Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    logger.info(f"Tree memory stored: {path} — {request.text[:60]}")
    return {"status": "stored", "id": point_id, "tree_path": path, "depth": len(ancestors)}


@app.post("/tree/store-bulk")
async def tree_store_bulk(request: TreeBulkStoreRequest):
    """Store multiple tree memories at once."""
    results = []
    for item in request.items:
        try:
            r = await tree_store(item)
            results.append({"tree_path": item.tree_path, "status": "stored", "id": r.get("id")})
        except Exception as e:
            results.append({"tree_path": item.tree_path, "status": "error", "error": str(e)})
    return {"stored": sum(1 for r in results if r["status"] == "stored"), "total": len(results), "results": results}


@app.post("/tree/search")
async def tree_search(request: TreeSearchRequest):
    """Semantic search within tree memories, optionally filtered to a branch."""
    try:
        embedding = await get_embedding(request.query)
    except Exception as e:
        logger.error(f"Tree search embedding failed: {e}")
        raise HTTPException(status_code=502, detail="Embedding service unavailable")

    filter_conditions = [{"key": "type", "match": {"value": "tree_memory"}}]
    if request.tree_path:
        branch = request.tree_path.strip("/").lower()
        filter_conditions.append({"key": "tree_ancestors", "match": {"value": branch}})

    search_body = {
        "vector": embedding,
        "limit": request.limit,
        "with_payload": True,
        "filter": {"must": filter_conditions},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/search",
                json=search_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Tree search Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    results = []
    for hit in data.get("result", []):
        p = hit.get("payload", {})
        results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0),
            "tree_path": p.get("tree_path", ""),
            "text": p.get("text", ""),
            "content": p.get("content", {}),
            "source": p.get("source", ""),
            "language": p.get("language", ""),
            "created_at": p.get("created_at"),
        })

    return {"results": results, "count": len(results), "branch": request.tree_path}


@app.get("/tree/browse")
async def tree_browse(limit: int = 500):
    """List all unique tree paths (branches) stored in memory."""
    scroll_body = {
        "limit": limit,
        "with_payload": True,
        "filter": {"must": [{"key": "type", "match": {"value": "tree_memory"}}]},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/scroll",
                json=scroll_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Tree browse Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    # Collect unique paths and build tree structure
    path_counts: dict[str, int] = {}
    for point in data.get("result", {}).get("points", []):
        p = point.get("payload", {})
        tp = p.get("tree_path", "")
        if tp:
            path_counts[tp] = path_counts.get(tp, 0) + 1

    # Build nested tree from paths
    tree: dict = {}
    for path in sorted(path_counts.keys()):
        parts = path.split("/")
        node = tree
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]

    return {
        "paths": [{"path": p, "count": c} for p, c in sorted(path_counts.items())],
        "total_paths": len(path_counts),
        "total_memories": sum(path_counts.values()),
        "tree": tree,
    }


@app.get("/tree/branch")
async def tree_branch(path: str, limit: int = 50, offset: int = 0):
    """Get all memories under a specific tree path (branch)."""
    branch = path.strip("/").lower()
    if not branch:
        raise HTTPException(status_code=400, detail="path is required")

    scroll_body = {
        "limit": limit,
        "offset": offset,
        "with_payload": True,
        "filter": {
            "must": [
                {"key": "type", "match": {"value": "tree_memory"}},
                {"key": "tree_ancestors", "match": {"value": branch}},
            ]
        },
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/scroll",
                json=scroll_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Tree branch Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    memories = []
    for point in data.get("result", {}).get("points", []):
        p = point.get("payload", {})
        memories.append({
            "id": point.get("id"),
            "tree_path": p.get("tree_path", ""),
            "text": p.get("text", ""),
            "content": p.get("content", {}),
            "source": p.get("source", ""),
            "language": p.get("language", ""),
            "created_at": p.get("created_at"),
        })

    return {"branch": branch, "memories": memories, "count": len(memories)}


@app.delete("/tree/memory/{memory_id}")
async def tree_delete_memory(memory_id: str):
    """Delete a specific tree memory by ID."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/delete",
                json={"points": [memory_id]},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Tree delete Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")
    return {"status": "deleted", "id": memory_id}


@app.delete("/tree/branch-delete")
async def tree_delete_branch(path: str):
    """Delete all memories under a tree path (branch)."""
    branch = path.strip("/").lower()
    if not branch:
        raise HTTPException(status_code=400, detail="path is required")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{settings.vector_db_url}/collections/{settings.collection_name}/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "type", "match": {"value": "tree_memory"}},
                            {"key": "tree_ancestors", "match": {"value": branch}},
                        ]
                    }
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Tree branch delete Qdrant failed: {e}")
            raise HTTPException(status_code=502, detail="Vector database unavailable")

    return {"status": "deleted", "branch": branch}
