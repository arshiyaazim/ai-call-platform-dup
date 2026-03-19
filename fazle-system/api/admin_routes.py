# ============================================================
# Fazle API — Admin Routes
# Dashboard management endpoints (agents, plugins, tasks, persona, logs)
# All routes require admin role
# ============================================================
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx

from auth import require_admin
from audit import log_action
from database import (
    list_agents, get_agent, create_agent, update_agent, delete_agent,
    list_plugins, create_plugin, update_plugin, delete_plugin,
    list_admin_tasks, create_admin_task, update_admin_task, delete_admin_task,
    get_persona, update_persona,
    get_all_conversations, delete_conversation,
    get_dashboard_stats,
)

logger = logging.getLogger("fazle-api")

router = APIRouter(prefix="/fazle/admin", dependencies=[Depends(require_admin)])


# ── Schemas ─────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    model: str = Field("gpt-4o-mini", max_length=100)
    priority: int = Field(1, ge=1, le=100)
    description: str = Field("", max_length=1000)
    status: str = Field("active", max_length=20)

class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    priority: Optional[int] = Field(None, ge=1, le=100)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = Field(None, max_length=20)

class PluginInstall(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=1000)
    version: str = Field("1.0.0", max_length=30)
    status: str = Field("enabled", max_length=20)
    manifest: Optional[dict] = None

class PluginUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    version: Optional[str] = Field(None, max_length=30)
    status: Optional[str] = Field(None, max_length=20)
    manifest: Optional[dict] = None

class AdminTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    task_type: str = Field("reminder", max_length=50)
    schedule: str = Field("", max_length=100)
    scheduled_at: Optional[str] = Field(None, max_length=30)
    description: str = Field("", max_length=2000)
    status: str = Field("pending", max_length=20)

class AdminTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    task_type: Optional[str] = Field(None, max_length=50)
    schedule: Optional[str] = Field(None, max_length=100)
    scheduled_at: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, max_length=20)

class PersonaUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    tone: Optional[str] = Field(None, max_length=500)
    language: Optional[str] = Field(None, max_length=50)
    speaking_style: Optional[str] = Field(None, max_length=2000)
    knowledge_notes: Optional[str] = Field(None, max_length=5000)


# ── Dashboard Stats ────────────────────────────────────────

@router.get("/dashboard/stats")
async def dashboard_stats(admin: dict = Depends(require_admin)):
    try:
        stats = get_dashboard_stats()
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        stats = {}
    return stats


# ── Agents ──────────────────────────────────────────────────

@router.get("/agents")
async def get_agents(admin: dict = Depends(require_admin)):
    return {"agents": list_agents()}


@router.post("/agents")
async def add_agent(request: AgentCreate, admin: dict = Depends(require_admin)):
    agent = create_agent(
        name=request.name,
        model=request.model,
        priority=request.priority,
        description=request.description,
        status=request.status,
    )
    log_action(admin, "create_agent", target_type="agent", target_id=str(agent["id"]),
               detail=f"Created agent {request.name}")
    return agent


@router.put("/agents/{agent_id}")
async def edit_agent(agent_id: str, request: AgentUpdate, admin: dict = Depends(require_admin)):
    existing = get_agent(agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")
    updated = update_agent(agent_id, **request.model_dump(exclude_unset=True))
    log_action(admin, "update_agent", target_type="agent", target_id=agent_id,
               detail=str(request.model_dump(exclude_unset=True)))
    return updated


@router.delete("/agents/{agent_id}")
async def remove_agent(agent_id: str, admin: dict = Depends(require_admin)):
    if not delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    log_action(admin, "delete_agent", target_type="agent", target_id=agent_id)
    return {"status": "deleted"}


# ── Plugins ─────────────────────────────────────────────────

@router.get("/plugins")
async def get_plugins(admin: dict = Depends(require_admin)):
    return {"plugins": list_plugins()}


@router.post("/plugins/install")
async def install_plugin(request: PluginInstall, admin: dict = Depends(require_admin)):
    plugin = create_plugin(
        name=request.name,
        description=request.description,
        version=request.version,
        status=request.status,
        manifest=request.manifest,
    )
    log_action(admin, "install_plugin", target_type="plugin", target_id=str(plugin["id"]),
               detail=f"Installed plugin {request.name} v{request.version}")
    return plugin


@router.put("/plugins/{plugin_id}")
async def edit_plugin(plugin_id: str, request: PluginUpdate, admin: dict = Depends(require_admin)):
    updated = update_plugin(plugin_id, **request.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Plugin not found")
    log_action(admin, "update_plugin", target_type="plugin", target_id=plugin_id,
               detail=str(request.model_dump(exclude_unset=True)))
    return updated


@router.delete("/plugins/{plugin_id}")
async def remove_plugin(plugin_id: str, admin: dict = Depends(require_admin)):
    if not delete_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="Plugin not found")
    log_action(admin, "delete_plugin", target_type="plugin", target_id=plugin_id)
    return {"status": "deleted"}


# ── Managed Tasks ───────────────────────────────────────────

@router.get("/tasks")
async def get_tasks(admin: dict = Depends(require_admin)):
    return {"tasks": list_admin_tasks()}


@router.post("/tasks")
async def add_task(request: AdminTaskCreate, admin: dict = Depends(require_admin)):
    task = create_admin_task(
        title=request.title,
        task_type=request.task_type,
        schedule=request.schedule,
        scheduled_at=request.scheduled_at,
        description=request.description,
        status=request.status,
    )
    log_action(admin, "create_task", target_type="task", target_id=str(task["id"]),
               detail=f"Created task: {request.title}")
    return task


@router.put("/tasks/{task_id}")
async def edit_task(task_id: str, request: AdminTaskUpdate, admin: dict = Depends(require_admin)):
    updated = update_admin_task(task_id, **request.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    log_action(admin, "update_task", target_type="task", target_id=task_id,
               detail=str(request.model_dump(exclude_unset=True)))
    return updated


@router.delete("/tasks/{task_id}")
async def remove_task(task_id: str, admin: dict = Depends(require_admin)):
    if not delete_admin_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    log_action(admin, "delete_task", target_type="task", target_id=task_id)
    return {"status": "deleted"}


# ── Persona ─────────────────────────────────────────────────

@router.get("/persona")
async def get_persona_config(admin: dict = Depends(require_admin)):
    return get_persona()


@router.put("/persona")
async def update_persona_config(request: PersonaUpdate, admin: dict = Depends(require_admin)):
    updated = update_persona(**request.model_dump(exclude_unset=True))
    log_action(admin, "update_persona", target_type="persona",
               detail=str(request.model_dump(exclude_unset=True)))
    return updated


# ── Conversation Logs ───────────────────────────────────────

@router.get("/logs")
async def get_logs(limit: int = 100, admin: dict = Depends(require_admin)):
    conversations = get_all_conversations(limit=min(limit, 500))
    logs = []
    for c in conversations:
        logs.append({
            "id": c.get("conversation_id", ""),
            "title": c.get("title", ""),
            "user_name": c.get("user_name", ""),
            "relationship": c.get("relationship_to_azim", ""),
            "last_message": c.get("last_message", ""),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
        })
    return {"logs": logs}


@router.delete("/logs/{conversation_id}")
async def delete_log(conversation_id: str, admin: dict = Depends(require_admin)):
    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    log_action(admin, "delete_conversation", target_type="conversation",
               target_id=conversation_id)
    return {"status": "deleted"}


# ── Memory listing (admin view) ─────────────────────────────

@router.get("/memories")
async def get_memories(admin: dict = Depends(require_admin)):
    """List all memories from the memory service."""
    from pydantic_settings import BaseSettings

    class _S(BaseSettings):
        memory_url: str = "http://fazle-memory:8300"
        class Config:
            env_prefix = "FAZLE_"

    memory_url = _S().memory_url
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{memory_url}/search",
                json={"query": "all", "limit": 100},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return {"results": []}
