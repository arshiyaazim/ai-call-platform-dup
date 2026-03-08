# ============================================================
# Fazle Task Engine — Scheduling, reminders, and automation
# ============================================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import httpx
import json
import logging
import os
import uuid
from typing import Optional
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fazle-task-engine")


class Settings(BaseSettings):
    brain_url: str = "http://fazle-brain:8200"
    memory_url: str = "http://fazle-memory:8300"
    dograh_api_url: str = "http://dograh-api:8000"
    database_url: str = ""

    class Config:
        env_prefix = "FAZLE_"


settings = Settings()

# ── Database setup ──────────────────────────────────────────
DATABASE_URL = settings.database_url or os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/postgres",
)

engine = create_engine(DATABASE_URL)


def ensure_tables():
    """Create task and scheduler tables if they don't exist (idempotent)."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fazle_tasks (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                description TEXT DEFAULT '',
                task_type VARCHAR(50) NOT NULL DEFAULT 'reminder',
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                scheduled_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                payload JSONB DEFAULT '{}'::jsonb
            )
        """))
        conn.commit()
    logger.info("Database tables verified")


app = FastAPI(title="Fazle Task Engine — Scheduling & Automation", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

jobstores = {"default": SQLAlchemyJobStore(engine=engine)}
scheduler = AsyncIOScheduler(jobstores=jobstores)

TASK_TYPES = {"reminder", "call", "summary", "instruction", "custom"}


@app.on_event("startup")
async def startup():
    ensure_tables()
    scheduler.start()
    logger.info("Task scheduler started with PostgreSQL job store")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()


# ── Health ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fazle-task-engine", "timestamp": datetime.utcnow().isoformat()}


# ── Task models ─────────────────────────────────────────────
class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    scheduled_at: Optional[str] = None
    task_type: str = "reminder"
    payload: dict = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    task_type: str
    status: str
    scheduled_at: Optional[str]
    created_at: str
    payload: dict


# ── Create task ─────────────────────────────────────────────
@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreateRequest):
    """Create a new scheduled task or reminder."""
    if request.task_type not in TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task type. Must be one of: {TASK_TYPES}")

    task_id = str(uuid.uuid4())
    now = datetime.utcnow()

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO fazle_tasks (id, title, description, task_type, status, scheduled_at, created_at, payload)
                VALUES (:id, :title, :description, :task_type, 'pending', :scheduled_at, :created_at, :payload)
            """),
            {
                "id": task_id,
                "title": request.title,
                "description": request.description,
                "task_type": request.task_type,
                "scheduled_at": request.scheduled_at,
                "created_at": now.isoformat(),
                "payload": json.dumps(request.payload),
            },
        )
        conn.commit()

    # Schedule if a time is provided
    if request.scheduled_at:
        try:
            trigger_time = datetime.fromisoformat(request.scheduled_at)
            scheduler.add_job(
                _execute_task,
                trigger=DateTrigger(run_date=trigger_time),
                args=[task_id],
                id=task_id,
                replace_existing=True,
            )
            logger.info(f"Task {task_id} scheduled for {request.scheduled_at}")
        except ValueError:
            logger.warning(f"Invalid schedule time: {request.scheduled_at}")

    return TaskResponse(
        id=task_id,
        title=request.title,
        description=request.description,
        task_type=request.task_type,
        status="pending",
        scheduled_at=request.scheduled_at,
        created_at=now.isoformat(),
        payload=request.payload,
    )


# ── List tasks ──────────────────────────────────────────────
@app.get("/tasks")
async def list_tasks(status: Optional[str] = None, task_type: Optional[str] = None):
    """List all tasks, optionally filtered."""
    query = "SELECT id, title, description, task_type, status, scheduled_at, created_at, payload FROM fazle_tasks WHERE 1=1"
    params: dict = {}
    if status:
        query += " AND status = :status"
        params["status"] = status
    if task_type:
        query += " AND task_type = :task_type"
        params["task_type"] = task_type
    query += " ORDER BY created_at DESC"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    result = [_row_to_dict(r) for r in rows]
    return {"tasks": result, "count": len(result)}


def _row_to_dict(row) -> dict:
    """Convert a DB row mapping to a task dict."""
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "task_type": row["task_type"],
        "status": row["status"],
        "scheduled_at": row["scheduled_at"].isoformat() if row["scheduled_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        "payload": row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or "{}"),
    }


# ── Get task ────────────────────────────────────────────────
@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, description, task_type, status, scheduled_at, created_at, payload FROM fazle_tasks WHERE id = :id"),
            {"id": task_id},
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(**_row_to_dict(row))


# ── Update task status ──────────────────────────────────────
class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


@app.patch("/tasks/{task_id}")
async def update_task(task_id: str, request: TaskUpdateRequest):
    sets = []
    params: dict = {"id": task_id}
    if request.status:
        sets.append("status = :status")
        params["status"] = request.status
    if request.title:
        sets.append("title = :title")
        params["title"] = request.title
    if request.description:
        sets.append("description = :description")
        params["description"] = request.description

    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    with engine.connect() as conn:
        result = conn.execute(
            text(f"UPDATE fazle_tasks SET {', '.join(sets)} WHERE id = :id RETURNING *"),
            params,
        ).mappings().first()
        conn.commit()

    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return _row_to_dict(result)


# ── Delete task ─────────────────────────────────────────────
@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    # Remove scheduled job if exists
    try:
        scheduler.remove_job(task_id)
    except Exception:
        pass

    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM fazle_tasks WHERE id = :id RETURNING id"), {"id": task_id}).first()
        conn.commit()

    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "id": task_id}


# ── Task execution ─────────────────────────────────────────
async def _execute_task(task_id: str):
    """Execute a scheduled task."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, description, task_type, status, scheduled_at, created_at, payload FROM fazle_tasks WHERE id = :id"),
            {"id": task_id},
        ).mappings().first()
    if not row:
        return

    task = _row_to_dict(row)
    _update_task_status(task_id, "executing")
    logger.info(f"Executing task: {task['title']} ({task['task_type']})")

    try:
        if task["task_type"] == "reminder":
            await _handle_reminder(task)
        elif task["task_type"] == "call":
            await _handle_call_task(task)
        elif task["task_type"] == "summary":
            await _handle_summary(task)

        _update_task_status(task_id, "completed")
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        _update_task_status(task_id, "failed")


def _update_task_status(task_id: str, status: str):
    """Update task status in the database."""
    with engine.connect() as conn:
        conn.execute(text("UPDATE fazle_tasks SET status = :status WHERE id = :id"), {"id": task_id, "status": status})
        conn.commit()


async def _handle_reminder(task: dict):
    """Store reminder result in memory."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(
                f"{settings.memory_url}/store",
                json={
                    "type": "personal",
                    "user": "Azim",
                    "content": {"task_id": task["id"], "reminder": task["title"]},
                    "text": f"Reminder: {task['title']}. {task['description']}",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to store reminder: {e}")


async def _handle_call_task(task: dict):
    """Trigger an outbound call via Dograh."""
    logger.info(f"Call task: {task['title']} — would trigger Dograh outbound call")


async def _handle_summary(task: dict):
    """Generate a summary using the brain."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            await client.post(
                f"{settings.brain_url}/chat",
                json={
                    "message": f"Generate a summary for: {task['description']}",
                    "user": "Azim",
                },
            )
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
