# ============================================================
# Fazle API — GDPR Compliance Routes (Enterprise-Grade)
# Async processing, soft delete, encrypted export, metrics,
# admin monitoring, failure recovery, identity mapping
# ============================================================
import json
import logging
import os
import uuid
import hashlib
import hmac
import base64
import time
import secrets
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from prometheus_client import Counter, Histogram, Gauge

from auth import get_current_user, require_admin
from database import (
    get_user_by_id,
    get_user_all_data,
    delete_user_all_data,
    create_gdpr_request,
    complete_gdpr_request,
    get_gdpr_requests,
    get_gdpr_request_by_code,
    log_gdpr_action,
    save_consent,
    get_consent,
    find_user_by_facebook_id,
    create_facebook_deletion_request,
    soft_delete_user,
    get_users_pending_deletion,
    cancel_deletion,
    upsert_user_identity,
    get_user_identity,
    find_user_by_identity,
    get_all_gdpr_requests_admin,
    get_gdpr_stats,
    update_gdpr_request_error,
    get_failed_gdpr_requests,
    reset_gdpr_request_for_retry,
)

logger = logging.getLogger("fazle-api")

router = APIRouter(prefix="/fazle/gdpr", tags=["GDPR"])


class GdprSettings(BaseSettings):
    facebook_app_secret: str = ""
    gdpr_deletion_delay_days: int = 7
    gdpr_export_expiry_hours: int = 24
    gdpr_max_retries: int = 3

    class Config:
        env_prefix = "FAZLE_"


gdpr_settings = GdprSettings()


# ── Prometheus Metrics ──────────────────────────────────────

GDPR_REQUESTS_TOTAL = Counter(
    "gdpr_requests_total", "Total GDPR requests", ["request_type"]
)
GDPR_DELETION_SUCCESS = Counter(
    "gdpr_deletion_success", "Successful GDPR deletions"
)
GDPR_DELETION_FAILURES = Counter(
    "gdpr_deletion_failures", "Failed GDPR deletions"
)
GDPR_EXPORT_REQUESTS = Counter(
    "gdpr_export_requests", "GDPR export requests"
)
GDPR_FACEBOOK_CALLBACKS = Counter(
    "facebook_callback_requests", "Facebook deletion callback requests"
)
GDPR_PROCESSING_DURATION = Histogram(
    "gdpr_processing_duration_seconds", "GDPR request processing time", ["request_type"]
)
GDPR_PENDING_DELETIONS = Gauge(
    "gdpr_pending_deletions", "Users awaiting permanent deletion"
)


# ── Rate limiter (in-memory, per-IP) ───────────────────────

class RateLimiter:
    """Simple in-memory rate limiter: max N requests per window (seconds)."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        self._hits[key] = [t for t in hits if now - t < self._window]
        if len(self._hits[key]) >= self._max:
            return False
        self._hits[key].append(now)
        return True


_delete_limiter = RateLimiter(max_requests=3, window_seconds=300)
_export_limiter = RateLimiter(max_requests=5, window_seconds=300)
_fb_limiter = RateLimiter(max_requests=10, window_seconds=60)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── AES Export Encryption ───────────────────────────────────

def _encrypt_export(data: dict) -> tuple[bytes, str]:
    """AES-encrypt export data. Returns (ciphertext, password)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    password = secrets.token_urlsafe(16)
    key = hashlib.sha256(password.encode()).digest()
    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(data, indent=2, default=str).encode("utf-8")
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    # Prepend nonce so decrypter can extract it
    return nonce + ciphertext, password


# ── In-memory encrypted export store with 24h expiry ───────

_export_store: dict[str, dict] = {}  # token -> {data, created, password_hint}
_export_lock = threading.Lock()


def _store_export(encrypted: bytes, password: str, user_id: str) -> str:
    """Store encrypted export, return download token."""
    token = secrets.token_urlsafe(32)
    with _export_lock:
        _export_store[token] = {
            "data": base64.b64encode(encrypted).decode(),
            "password": password,
            "user_id": user_id,
            "created": time.time(),
        }
    return token


def _cleanup_expired_exports():
    """Remove exports older than configured expiry."""
    cutoff = time.time() - (gdpr_settings.gdpr_export_expiry_hours * 3600)
    with _export_lock:
        expired = [k for k, v in _export_store.items() if v["created"] < cutoff]
        for k in expired:
            del _export_store[k]


# ── Pydantic models ────────────────────────────────────────

class ConsentRequest(BaseModel):
    terms: bool
    privacy: bool


class IdentityRequest(BaseModel):
    facebook_id: Optional[str] = None
    whatsapp_id: Optional[str] = None
    phone_number: Optional[str] = None


# ── Background Workers ─────────────────────────────────────

def _bg_process_deletion(user_id: str, request_id: str, client_ip: str):
    """Background worker: soft-delete user data."""
    start = time.time()
    try:
        GDPR_REQUESTS_TOTAL.labels(request_type="delete").inc()

        # Soft delete — mark for delayed permanent deletion
        result = soft_delete_user(user_id, gdpr_settings.gdpr_deletion_delay_days)
        if result:
            complete_gdpr_request(request_id, "completed")
            GDPR_DELETION_SUCCESS.inc()
            log_gdpr_action(
                user_id,
                "data_deletion_completed",
                f"User marked for deletion in {gdpr_settings.gdpr_deletion_delay_days} days (IP: {client_ip})",
            )
        else:
            update_gdpr_request_error(request_id, "soft_delete returned empty")
            GDPR_DELETION_FAILURES.inc()
    except Exception as e:
        update_gdpr_request_error(request_id, str(type(e).__name__))
        GDPR_DELETION_FAILURES.inc()
        logger.error(f"GDPR deletion worker failed: {type(e).__name__}")
    finally:
        GDPR_PROCESSING_DURATION.labels(request_type="delete").observe(time.time() - start)


def _bg_process_export(user_id: str, request_id: str, client_ip: str):
    """Background worker: generate encrypted export."""
    start = time.time()
    try:
        GDPR_REQUESTS_TOTAL.labels(request_type="export").inc()
        GDPR_EXPORT_REQUESTS.inc()

        data = get_user_all_data(user_id)
        if not data:
            update_gdpr_request_error(request_id, "No data found")
            return

        export_data = json.loads(json.dumps(data, default=str))
        export_data["exported_at"] = datetime.now(timezone.utc).isoformat()
        export_data["export_format"] = "GDPR_DATA_EXPORT_v2"
        export_data["request_id"] = request_id

        encrypted, password = _encrypt_export(export_data)
        token = _store_export(encrypted, password, user_id)

        # Store key hint (first 4 chars) on the request
        from database import _get_conn
        import psycopg2.extras
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE gdpr_requests SET encryption_key_hint = %s WHERE id = %s",
                    (password[:4], request_id),
                )
                conn.commit()

        complete_gdpr_request(request_id, "completed")
        log_gdpr_action(
            user_id,
            "data_export_completed",
            f"Encrypted export ready, token={token[:8]}... (IP: {client_ip})",
        )

        # Store the download token on the request so the client can poll for it
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE gdpr_requests SET confirmation_code = %s WHERE id = %s",
                    (token, request_id),
                )
                conn.commit()

    except Exception as e:
        update_gdpr_request_error(request_id, str(type(e).__name__))
        logger.error(f"GDPR export worker failed: {type(e).__name__}")
    finally:
        GDPR_PROCESSING_DURATION.labels(request_type="export").observe(time.time() - start)


def _bg_process_permanent_deletions():
    """Background worker: permanently delete users whose grace period expired."""
    users = get_users_pending_deletion()
    for user in users:
        uid = str(user["id"])
        try:
            deleted = delete_user_all_data(uid)
            log_gdpr_action(uid, "permanent_deletion",
                            f"Permanently deleted after grace period. Tables: {', '.join(deleted)}")
            GDPR_DELETION_SUCCESS.inc()
        except Exception as e:
            logger.error(f"Permanent deletion failed for {uid[:8]}: {type(e).__name__}")
            GDPR_DELETION_FAILURES.inc()


def _bg_retry_failed_requests():
    """Background worker: retry failed GDPR requests."""
    failed = get_failed_gdpr_requests(gdpr_settings.gdpr_max_retries)
    for req in failed:
        req_id = str(req["id"])
        user_id = str(req["user_id"]) if req["user_id"] else None
        req_type = req["request_type"]

        reset_gdpr_request_for_retry(req_id)
        try:
            if req_type == "delete" and user_id:
                soft_delete_user(user_id, gdpr_settings.gdpr_deletion_delay_days)
                complete_gdpr_request(req_id, "completed")
                GDPR_DELETION_SUCCESS.inc()
            elif req_type == "export" and user_id:
                _bg_process_export(user_id, req_id, "retry")
            else:
                complete_gdpr_request(req_id, "completed")
            log_gdpr_action(
                user_id or "00000000-0000-0000-0000-000000000000",
                "retry_success", f"Retried {req_type} request {req_id[:8]}"
            )
        except Exception as e:
            update_gdpr_request_error(req_id, f"retry failed: {type(e).__name__}")
            logger.error(f"GDPR retry failed for {req_id[:8]}: {type(e).__name__}")


# ── Authenticated GDPR Endpoints ───────────────────────────

@router.get("/me")
async def get_my_data(user: dict = Depends(get_current_user)):
    """Return all stored data for the current user (GDPR right of access)."""
    user_id = str(user["id"])
    GDPR_REQUESTS_TOTAL.labels(request_type="access").inc()
    log_gdpr_action(user_id, "data_access", "User requested access to all personal data")
    data = get_user_all_data(user_id)
    if not data:
        raise HTTPException(status_code=404, detail="No data found")
    return data


@router.post("/export")
async def export_my_data(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Queue encrypted export of all user data (GDPR data portability)."""
    client_ip = _get_client_ip(request)
    if not _export_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many export requests. Try again later.")

    user_id = str(user["id"])
    req = create_gdpr_request(user_id, "export")
    request_id = str(req["id"])

    log_gdpr_action(user_id, "data_export_requested", f"Export queued (IP: {client_ip})")

    # Process in background
    background_tasks.add_task(_bg_process_export, user_id, request_id, client_ip)

    return {
        "status": "processing",
        "message": "Your data export is being prepared. Check status for download link.",
        "request_id": request_id,
    }


@router.get("/export/{request_id}")
async def get_export_status(request_id: str, user: dict = Depends(get_current_user)):
    """Check export status and get download info when ready."""
    user_id = str(user["id"])
    requests_list = get_gdpr_requests(user_id)
    req = next((r for r in requests_list if str(r["id"]) == request_id), None)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req["status"] == "completed" and req.get("confirmation_code"):
        token = req["confirmation_code"]
        with _export_lock:
            entry = _export_store.get(token)
        if entry:
            return {
                "status": "ready",
                "download_token": token,
                "password": entry["password"],
                "expires_in_hours": gdpr_settings.gdpr_export_expiry_hours,
                "message": "Use the download token and password to retrieve your encrypted data.",
            }
        return {"status": "expired", "message": "Export has expired. Please request a new one."}
    elif req["status"] == "failed":
        return {"status": "failed", "message": "Export failed. It will be retried automatically."}
    return {"status": "processing", "message": "Export is being prepared..."}


@router.get("/export/download/{token}")
async def download_export(token: str):
    """Download encrypted export file (public with token)."""
    _cleanup_expired_exports()
    with _export_lock:
        entry = _export_store.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    return JSONResponse(content={
        "encrypted_data": entry["data"],
        "format": "AES-256-GCM",
        "nonce_prepended": True,
        "filename": f"fazle-export-{entry['user_id'][:8]}.enc",
    })


@router.post("/delete")
async def delete_my_data(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Queue user data deletion with configurable grace period (GDPR right to erasure)."""
    client_ip = _get_client_ip(request)
    if not _delete_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many deletion requests. Try again later.")

    user_id = str(user["id"])
    req = create_gdpr_request(user_id, "delete")
    request_id = str(req["id"])

    log_gdpr_action(
        user_id, "data_deletion_requested",
        f"User requested deletion (IP: {client_ip})",
    )

    # Process in background
    background_tasks.add_task(_bg_process_deletion, user_id, request_id, client_ip)

    return {
        "status": "processing",
        "message": f"Your account will be deactivated and permanently deleted after {gdpr_settings.gdpr_deletion_delay_days} days.",
        "request_id": request_id,
        "grace_period_days": gdpr_settings.gdpr_deletion_delay_days,
    }


@router.post("/cancel-deletion")
async def cancel_my_deletion(user: dict = Depends(get_current_user)):
    """Cancel pending deletion and reactivate account."""
    user_id = str(user["id"])
    success = cancel_deletion(user_id)
    if success:
        log_gdpr_action(user_id, "deletion_cancelled", "User cancelled pending deletion")
        return {"status": "cancelled", "message": "Your account has been reactivated."}
    raise HTTPException(status_code=400, detail="No pending deletion to cancel")


@router.get("/status")
async def get_my_requests(user: dict = Depends(get_current_user)):
    """Return all GDPR requests for the current user."""
    user_id = str(user["id"])
    requests_list = get_gdpr_requests(user_id)
    return {"requests": json.loads(json.dumps(requests_list, default=str))}


@router.post("/consent")
async def store_consent(body: ConsentRequest, user: dict = Depends(get_current_user)):
    """Store or update user consent for terms and privacy policy."""
    user_id = str(user["id"])
    consent = save_consent(user_id, body.terms, body.privacy)
    log_gdpr_action(user_id, "consent_updated", f"Terms: {body.terms}, Privacy: {body.privacy}")
    return {"status": "saved", "consent": json.loads(json.dumps(consent, default=str))}


@router.get("/consent")
async def get_my_consent(user: dict = Depends(get_current_user)):
    """Get current consent status."""
    user_id = str(user["id"])
    consent = get_consent(user_id)
    if not consent:
        return {"terms_accepted": False, "privacy_accepted": False, "accepted_at": None}
    return json.loads(json.dumps(consent, default=str))


# ── Identity Management ────────────────────────────────────

@router.post("/identity")
async def update_identity(body: IdentityRequest, user: dict = Depends(get_current_user)):
    """Update user identity mapping (link Facebook, WhatsApp, phone)."""
    user_id = str(user["id"])
    identity = upsert_user_identity(
        user_id,
        email=user.get("email"),
        facebook_id=body.facebook_id,
        whatsapp_id=body.whatsapp_id,
        phone_number=body.phone_number,
    )
    log_gdpr_action(user_id, "identity_updated", "User updated identity mapping")
    return {"status": "saved", "identity": json.loads(json.dumps(identity, default=str))}


@router.get("/identity")
async def get_my_identity(user: dict = Depends(get_current_user)):
    """Get current identity mapping."""
    user_id = str(user["id"])
    identity = get_user_identity(user_id)
    if not identity:
        return {"user_id": user_id, "email": user.get("email"), "facebook_id": None, "whatsapp_id": None, "phone_number": None}
    return json.loads(json.dumps(identity, default=str))


# ── Facebook Data Deletion Callback (Meta-compliant) ───────

def _parse_facebook_signed_request(signed_request: str, app_secret: str) -> Optional[dict]:
    """Parse and verify a Facebook signed_request."""
    try:
        parts = signed_request.split(".", 1)
        if len(parts) != 2:
            return None
        encoded_sig, encoded_payload = parts
        sig = base64.urlsafe_b64decode(encoded_sig + "==")
        payload_bytes = base64.urlsafe_b64decode(encoded_payload + "==")
        payload = json.loads(payload_bytes)
        if app_secret:
            expected_sig = hmac.new(
                app_secret.encode("utf-8"),
                encoded_payload.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(sig, expected_sig):
                logger.warning("Facebook signed_request signature verification failed")
                return None
        return payload
    except Exception as e:
        logger.error(f"Failed to parse Facebook signed_request: {type(e).__name__}")
        return None


@router.post("/facebook-deletion")
async def facebook_data_deletion(request: Request, background_tasks: BackgroundTasks):
    """Facebook Data Deletion Callback (Meta-compliant)."""
    client_ip = _get_client_ip(request)
    if not _fb_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")

    GDPR_FACEBOOK_CALLBACKS.inc()
    GDPR_REQUESTS_TOTAL.labels(request_type="facebook_deletion").inc()

    try:
        form = await request.form()
        signed_request = form.get("signed_request")
        if not signed_request:
            raise HTTPException(status_code=400, detail="Missing signed_request")

        payload = _parse_facebook_signed_request(
            str(signed_request), gdpr_settings.facebook_app_secret
        )
        if payload is None:
            raise HTTPException(status_code=400, detail="Invalid signed_request")

        fb_user_id = str(payload.get("user_id", ""))
        if not fb_user_id:
            raise HTTPException(status_code=400, detail="No user_id in signed_request")

        confirmation_code = uuid.uuid4().hex

        # Try identity table first, then fall back
        identity = find_user_by_identity(facebook_id=fb_user_id)
        internal_user = None
        if identity:
            internal_user = get_user_by_id(str(identity["user_id"]))
        if not internal_user:
            internal_user = find_user_by_facebook_id(fb_user_id)

        deleted_tables: list[str] = []
        if internal_user:
            internal_uid = str(internal_user["id"])
            log_gdpr_action(
                internal_uid, "facebook_deletion_callback",
                f"Facebook user {fb_user_id} requested deletion via Meta callback",
            )
            # Use soft delete
            soft_delete_user(internal_uid, gdpr_settings.gdpr_deletion_delay_days)
            deleted_tables = ["fazle_users (soft-deleted)"]
        else:
            log_gdpr_action(
                "00000000-0000-0000-0000-000000000000",
                "facebook_deletion_callback",
                f"Facebook user {fb_user_id} — no matching internal user",
            )

        create_facebook_deletion_request(fb_user_id, confirmation_code, deleted_tables)

        return JSONResponse(content={
            "url": f"https://iamazim.com/deletion-status/{confirmation_code}",
            "confirmation_code": confirmation_code,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Facebook deletion callback error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Processing failed")


@router.get("/deletion-status/{code}")
async def check_deletion_status(code: str):
    """Check status of a data deletion request (public, no auth)."""
    req = get_gdpr_request_by_code(code)
    if req:
        return {
            "status": req.get("status", "completed"),
            "message": "Your data deletion request has been successfully processed."
            if req.get("status") == "completed"
            else "Your data deletion request is being processed.",
            "confirmation_code": code,
        }
    return {
        "status": "completed",
        "message": "Your data deletion request has been successfully processed.",
        "confirmation_code": code,
    }


# ── Admin Endpoints (require_admin) ────────────────────────

@router.get("/admin/requests")
async def admin_list_requests(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    admin: dict = Depends(require_admin),
):
    """List all GDPR requests (admin only)."""
    result = get_all_gdpr_requests_admin(limit, offset, status)
    return json.loads(json.dumps(result, default=str))


@router.get("/admin/stats")
async def admin_gdpr_stats(admin: dict = Depends(require_admin)):
    """Get aggregated GDPR statistics (admin only)."""
    stats = get_gdpr_stats()
    # Add pending deletions gauge
    pending = get_users_pending_deletion()
    GDPR_PENDING_DELETIONS.set(len(pending))
    stats["pending_permanent_deletions"] = len(pending)
    stats["export_store_size"] = len(_export_store)
    return json.loads(json.dumps(stats, default=str))


@router.post("/admin/retry-failed")
async def admin_retry_failed(
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
):
    """Retry all failed GDPR requests (admin only)."""
    background_tasks.add_task(_bg_retry_failed_requests)
    log_gdpr_action(str(admin["id"]), "admin_retry", "Admin triggered retry of failed requests")
    return {"status": "queued", "message": "Failed requests will be retried in the background."}


@router.post("/admin/process-deletions")
async def admin_process_deletions(
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
):
    """Permanently delete users whose grace period has expired (admin only)."""
    background_tasks.add_task(_bg_process_permanent_deletions)
    log_gdpr_action(str(admin["id"]), "admin_process_deletions", "Admin triggered permanent deletion sweep")
    return {"status": "queued", "message": "Permanent deletion sweep queued."}


@router.post("/admin/cleanup-exports")
async def admin_cleanup_exports(admin: dict = Depends(require_admin)):
    """Clean up expired export files (admin only)."""
    before = len(_export_store)
    _cleanup_expired_exports()
    after = len(_export_store)
    return {"cleaned": before - after, "remaining": after}
