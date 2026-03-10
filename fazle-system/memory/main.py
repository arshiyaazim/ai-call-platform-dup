# ============================================================
# Fazle Memory — Long-term memory with vector search (Qdrant)
# Stores: preferences, contacts, knowledge, conversations
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import httpx
import logging
import uuid
import hashlib
from typing import Optional
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-memory")


class Settings(BaseSettings):
    vector_db_url: str = "http://qdrant:6333"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    collection_name: str = "fazle_memories"

    class Config:
        env_prefix = ""


settings = Settings()

app = FastAPI(title="Fazle Memory — Vector Memory System", version="1.0.0")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://fazle.iamazim.com,https://iamazim.com,http://localhost:3020").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMORY_TYPES = {"preference", "contact", "knowledge", "personal", "conversation"}


async def ensure_collection():
    """Create Qdrant collection if it doesn't exist."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.vector_db_url}/collections/{settings.collection_name}")
            if resp.status_code == 200:
                return
        except Exception:
            pass

        try:
            await client.put(
                f"{settings.vector_db_url}/collections/{settings.collection_name}",
                json={
                    "vectors": {"size": settings.embedding_dim, "distance": "Cosine"},
                },
            )
            logger.info(f"Created collection: {settings.collection_name}")
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector from OpenAI."""
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


@app.on_event("startup")
async def startup():
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
