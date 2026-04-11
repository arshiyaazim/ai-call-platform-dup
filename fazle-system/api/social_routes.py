# ============================================================
# Fazle API — Social Engine Proxy Routes
# WhatsApp + Facebook automation via Social Engine microservice
# ============================================================
from fastapi import APIRouter, Depends, HTTPException, Query, Request
import httpx
import logging
from typing import Optional

from auth import require_admin, get_current_user
from audit import log_action

logger = logging.getLogger("fazle-api")

router = APIRouter(prefix="/fazle/social", tags=["social"])


def _get_settings():
    from main import settings
    return settings


async def _proxy(method: str, path: str, **kwargs):
    """Helper to proxy requests to the social engine."""
    settings = _get_settings()
    url = f"{settings.social_engine_url}{path}"
    async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 15.0)) as client:
        try:
            resp = await getattr(client, method)(url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Social engine error [{method.upper()} {path}]: {e}")
            return {"status": "fallback", "data": [], "detail": "Social engine unavailable"}


# ── Integration Management ─────────────────────────────────

@router.get("/integrations")
async def list_integrations(user: dict = Depends(require_admin)):
    """List all social platform integrations (secrets masked)."""
    return await _proxy("get", "/integrations")


@router.post("/integrations/save")
async def save_integration(body: dict, user: dict = Depends(require_admin)):
    """Save or update a platform integration (WhatsApp or Facebook)."""
    result = await _proxy("post", "/integrations/save", json=body, timeout=15.0)
    log_action(user, "save_integration", target_type="social", detail=body.get("platform", ""))
    return result


@router.post("/integrations/test")
async def test_integration(body: dict, user: dict = Depends(require_admin)):
    """Test connectivity for a saved integration."""
    return await _proxy("post", "/integrations/test", json=body, timeout=15.0)


@router.post("/integrations/enable")
async def enable_integration(body: dict, user: dict = Depends(require_admin)):
    """Enable a platform integration."""
    result = await _proxy("post", "/integrations/enable", json=body)
    log_action(user, "enable_integration", target_type="social", detail=body.get("platform", ""))
    return result


@router.post("/integrations/disable")
async def disable_integration(body: dict, user: dict = Depends(require_admin)):
    """Disable a platform integration."""
    result = await _proxy("post", "/integrations/disable", json=body)
    log_action(user, "disable_integration", target_type="social", detail=body.get("platform", ""))
    return result


@router.get("/integration/status")
async def integration_status(user: dict = Depends(require_admin)):
    """Return connected platforms, webhook status, last message timestamp."""
    return await _proxy("get", "/integration/status")


# ── Webhook Passthrough (public — no auth for Meta verification) ──

@router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(request: Request):
    """Public endpoint: Meta sends GET for WhatsApp webhook verification."""
    settings = _get_settings()
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.social_engine_url}/whatsapp/webhook", params=params)
            # Return raw response (could be plain int for challenge)
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail="Verification failed")
        except httpx.HTTPError as e:
            logger.error(f"WhatsApp webhook verify error: {e}")
            return {"status": "ok"}


@router.post("/whatsapp/webhook")
async def whatsapp_webhook_receive(request: Request):
    """Public endpoint: Meta sends POST for incoming WhatsApp messages."""
    raw_body = await request.body()
    forward_headers = {}
    sig = request.headers.get("X-Hub-Signature-256")
    if sig:
        forward_headers["X-Hub-Signature-256"] = sig
    settings = _get_settings()
    url = f"{settings.social_engine_url}/whatsapp/webhook"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, content=raw_body, headers=forward_headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp webhook status error: {e.response.status_code}")
            return {"status": "ok"}
        except httpx.HTTPError as e:
            logger.error(f"WhatsApp webhook receive error: {e}")
            return {"status": "ok"}


@router.get("/facebook/webhook")
async def facebook_webhook_verify(request: Request):
    """Public endpoint: Meta sends GET for Facebook webhook verification."""
    settings = _get_settings()
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.social_engine_url}/facebook/webhook", params=params)
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail="Verification failed")
        except httpx.HTTPError as e:
            logger.error(f"Facebook webhook verify error: {e}")
            return {"status": "ok"}


@router.post("/facebook/webhook")
async def facebook_webhook_receive(request: Request):
    """Public endpoint: Meta sends POST for incoming Facebook events."""
    raw_body = await request.body()
    forward_headers = {}
    sig = request.headers.get("X-Hub-Signature-256")
    if sig:
        forward_headers["X-Hub-Signature-256"] = sig
    settings = _get_settings()
    url = f"{settings.social_engine_url}/facebook/webhook"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, content=raw_body, headers=forward_headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook webhook status error: {e.response.status_code}")
            return {"status": "ok"}
        except httpx.HTTPError as e:
            logger.error(f"Facebook webhook receive error: {e}")
            return {"status": "ok"}


# ── WhatsApp ────────────────────────────────────────────────

@router.post("/whatsapp/send")
async def whatsapp_send(body: dict, user: dict = Depends(require_admin)):
    """Send a WhatsApp message."""
    result = await _proxy("post", "/whatsapp/send", json=body, timeout=30.0)
    log_action(user, "whatsapp_send", target_type="social", detail=body.get("to", ""))
    return result


@router.post("/whatsapp/schedule")
async def whatsapp_schedule(body: dict, user: dict = Depends(require_admin)):
    """Schedule a WhatsApp message."""
    result = await _proxy("post", "/whatsapp/schedule", json=body)
    log_action(user, "whatsapp_schedule", target_type="social")
    return result


@router.post("/whatsapp/broadcast")
async def whatsapp_broadcast(body: dict, user: dict = Depends(require_admin)):
    """Broadcast a message to multiple WhatsApp contacts."""
    result = await _proxy("post", "/whatsapp/broadcast", json=body, timeout=30.0)
    log_action(user, "whatsapp_broadcast", target_type="social")
    return result


@router.get("/whatsapp/messages")
async def whatsapp_messages(limit: int = Query(50, ge=1, le=200), user: dict = Depends(require_admin)):
    """Get recent WhatsApp messages."""
    return await _proxy("get", "/whatsapp/messages", params={"limit": limit})


@router.get("/whatsapp/scheduled")
async def whatsapp_scheduled(user: dict = Depends(require_admin)):
    """Get scheduled WhatsApp messages."""
    return await _proxy("get", "/whatsapp/scheduled")


# ── Facebook ───────────────────────────────────────────────

@router.post("/facebook/post")
async def facebook_post(body: dict, user: dict = Depends(require_admin)):
    """Create or schedule a Facebook post."""
    result = await _proxy("post", "/facebook/post", json=body, timeout=30.0)
    log_action(user, "facebook_post", target_type="social")
    return result


@router.post("/facebook/comment")
async def facebook_comment(body: dict, user: dict = Depends(require_admin)):
    """Reply to a Facebook comment."""
    result = await _proxy("post", "/facebook/comment", json=body)
    log_action(user, "facebook_comment", target_type="social")
    return result


@router.post("/facebook/react")
async def facebook_react(body: dict, user: dict = Depends(require_admin)):
    """React to a Facebook post or comment."""
    return await _proxy("post", "/facebook/react", json=body)


@router.get("/facebook/posts")
async def facebook_posts(limit: int = Query(50, ge=1, le=200), user: dict = Depends(require_admin)):
    """Get recent Facebook posts."""
    return await _proxy("get", "/facebook/posts", params={"limit": limit})


@router.get("/facebook/scheduled")
async def facebook_scheduled(user: dict = Depends(require_admin)):
    """Get scheduled Facebook posts."""
    return await _proxy("get", "/facebook/scheduled")


# ── Contacts ───────────────────────────────────────────────

@router.get("/contacts")
async def list_contacts(
    platform: Optional[str] = Query(None, pattern=r"^(whatsapp|facebook)$"),
    user: dict = Depends(require_admin),
):
    """List social contacts."""
    params = {}
    if platform:
        params["platform"] = platform
    return await _proxy("get", "/contacts", params=params)


@router.post("/contacts")
async def add_contact(body: dict, user: dict = Depends(require_admin)):
    """Add a social contact."""
    result = await _proxy("post", "/contacts", json=body)
    log_action(user, "add_contact", target_type="social")
    return result


# ── Contact Book (fazle_contacts — personal contact intelligence) ──

@router.get("/contacts/book")
async def list_contact_book(
    platform: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_admin),
):
    """List contacts from the personal contact book with search/filter."""
    params = {"limit": limit, "offset": offset}
    if platform:
        params["platform"] = platform
    if search:
        params["search"] = search
    return await _proxy("get", "/contacts/book", params=params)


@router.get("/contacts/book/{contact_id}")
async def get_contact_book_entry(contact_id: str, user: dict = Depends(require_admin)):
    """Get a single contact from the contact book."""
    return await _proxy("get", f"/contacts/book/{contact_id}")


@router.put("/contacts/book/{contact_id}")
async def update_contact_book_entry(contact_id: str, body: dict, user: dict = Depends(require_admin)):
    """Update a contact in the contact book."""
    result = await _proxy("put", f"/contacts/book/{contact_id}", json=body)
    log_action(user, "update_contact", target_type="social", detail=contact_id)
    return result


@router.delete("/contacts/book/{contact_id}")
async def delete_contact_book_entry(contact_id: str, user: dict = Depends(require_admin)):
    """Delete a contact from the contact book."""
    result = await _proxy("delete", f"/contacts/book/{contact_id}")
    log_action(user, "delete_contact", target_type="social", detail=contact_id)
    return result


@router.post("/contacts/import")
async def import_contacts_csv(request: Request, user: dict = Depends(require_admin)):
    """Import contacts from CSV (text/csv body or JSON with csv field)."""
    content_type = request.headers.get("content-type", "")
    if "text/csv" in content_type:
        raw = await request.body()
        result = await _proxy("post", "/contacts/import", content=raw,
                              headers={"Content-Type": "text/csv"}, timeout=30.0)
    else:
        body = await request.json()
        result = await _proxy("post", "/contacts/import", json=body, timeout=30.0)
    log_action(user, "import_contacts", target_type="social")
    return result


# ── Campaigns ──────────────────────────────────────────────

@router.get("/campaigns")
async def list_campaigns(user: dict = Depends(require_admin)):
    """List social campaigns."""
    return await _proxy("get", "/campaigns")


@router.post("/campaigns")
async def create_campaign(body: dict, user: dict = Depends(require_admin)):
    """Create a social campaign."""
    result = await _proxy("post", "/campaigns", json=body)
    log_action(user, "create_campaign", target_type="social")
    return result


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(require_admin)):
    """Get a single campaign by ID."""
    return await _proxy("get", f"/campaigns/{campaign_id}")


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: dict, user: dict = Depends(require_admin)):
    """Update a social campaign."""
    result = await _proxy("put", f"/campaigns/{campaign_id}", json=body)
    log_action(user, "update_campaign", target_type="social", detail=campaign_id)
    return result


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, user: dict = Depends(require_admin)):
    """Delete or cancel a social campaign."""
    result = await _proxy("delete", f"/campaigns/{campaign_id}")
    log_action(user, "delete_campaign", target_type="social", detail=campaign_id)
    return result


# ── Scheduled Messages ─────────────────────────────────────

@router.get("/scheduled")
async def list_all_scheduled(user: dict = Depends(require_admin)):
    """List all scheduled messages across platforms."""
    return await _proxy("get", "/scheduled")


@router.delete("/scheduled/{message_id}")
async def cancel_scheduled_message(message_id: str, user: dict = Depends(require_admin)):
    """Cancel a scheduled message."""
    result = await _proxy("delete", f"/scheduled/{message_id}")
    log_action(user, "cancel_scheduled", target_type="social", detail=message_id)
    return result


@router.put("/scheduled/{message_id}")
async def update_scheduled_message(message_id: str, body: dict, user: dict = Depends(require_admin)):
    """Update a scheduled message (e.g., reschedule or change content)."""
    result = await _proxy("put", f"/scheduled/{message_id}", json=body)
    log_action(user, "update_scheduled", target_type="social", detail=message_id)
    return result


# ── Stats ──────────────────────────────────────────────────

@router.get("/stats")
async def social_stats(user: dict = Depends(require_admin)):
    """Get social engine stats."""
    return await _proxy("get", "/stats")


# ── Reply Reuse & Learning ────────────────────────────────

@router.get("/reply-stats")
async def reply_stats(user: dict = Depends(require_admin)):
    """Get reply reuse, feedback, summary, and multimodal learning stats."""
    return await _proxy("get", "/reply-stats")


@router.get("/summaries")
async def list_summaries(phone: str = "", limit: int = 20, user: dict = Depends(require_admin)):
    """Get conversation summaries, optionally filtered by phone."""
    params = {"limit": limit}
    if phone:
        params["phone"] = phone
    return await _proxy("get", "/summaries", params=params)


@router.get("/owner/audio-examples")
async def owner_audio_examples(limit: int = 10, user: dict = Depends(require_admin)):
    """Get owner audio transcripts for style learning."""
    return await _proxy("get", "/owner/audio-examples", params={"limit": limit})


@router.get("/feedback")
async def list_feedback(limit: int = 50, user: dict = Depends(require_admin)):
    """Get owner feedback on AI replies."""
    return await _proxy("get", "/feedback", params={"limit": limit})
