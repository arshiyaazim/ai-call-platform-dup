# ============================================================
# Phase 8: Action & Automation Engine — Deterministic Execution Layer
# Central registry for safe, auditable, idempotent owner actions.
# ============================================================
from __future__ import annotations

import json
import time
import re
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("fazle-brain.action-engine")


# ── Action Definition ────────────────────────────────────────

@dataclass(frozen=True)
class ActionDef:
    name: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    risk: str = "medium"                        # low | medium | high | critical
    needs_confirmation: bool = False
    description: str = ""
    idempotency_fields: tuple[str, ...] = ()    # fields used for dedup key


# ── Field Validators ─────────────────────────────────────────

_PHONE_RE = re.compile(r"^01[3-9]\d{8}$")
_SAFE_STR = re.compile(
    r"^[\w\s\-.,!?@#&()/।':;\"\u0980-\u09FF]+$", re.UNICODE
)

_VALIDATORS: dict[str, Callable] = {
    "name":         lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 200 and bool(_SAFE_STR.match(v.strip())),
    "phone":        lambda v: isinstance(v, str) and bool(_PHONE_RE.match(v.strip())),
    "company_name": lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 200 and bool(_SAFE_STR.match(v.strip())),
    "guard_name":   lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 200 and bool(_SAFE_STR.match(v.strip())),
    "client_name":  lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 200 and bool(_SAFE_STR.match(v.strip())),
    "location":     lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 300 and bool(_SAFE_STR.match(v.strip())),
    "price":        lambda v: isinstance(v, (int, float)) and 0 < float(v) < 10_000_000,
    "service_type": lambda v: isinstance(v, str) and 1 <= len(v.strip()) <= 100 and bool(_SAFE_STR.match(v.strip())),
}


# ── Validation ───────────────────────────────────────────────

def validate_action(action_name: str, params: dict) -> tuple[bool, str]:
    """Validate params against action definition. Returns (ok, error_msg)."""
    adef = ACTION_REGISTRY.get(action_name)
    if not adef:
        return False, f"Unknown action: {action_name}"
    # required fields
    for f in adef.required_fields:
        if f not in params or not params[f]:
            return False, f"Missing required field: {f}"
    # type / value checks
    for k, v in params.items():
        validator = _VALIDATORS.get(k)
        if validator and not validator(v):
            return False, f"Invalid value for '{k}'"
    return True, ""


# ── Idempotency ──────────────────────────────────────────────

def _build_dedup_key(action_name: str, params: dict) -> str:
    adef = ACTION_REGISTRY.get(action_name)
    if not adef or not adef.idempotency_fields:
        return ""
    parts = [action_name] + [
        str(params.get(f, "")).strip().lower() for f in adef.idempotency_fields
    ]
    return "|".join(parts)


def _already_executed(dsn: str, dedup_key: str) -> bool:
    """Return True if this exact action was already executed successfully."""
    if not dsn or not dedup_key:
        return False
    try:
        import psycopg2

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM owner_action_audit
                       WHERE result_data->>'_dedup_key' = %s
                         AND status = 'success'
                       LIMIT 1""",
                    (dedup_key,),
                )
                return cur.fetchone() is not None
    except Exception:
        return False


# ── Handlers (pure logic, no LLM, deterministic) ────────────

def _handler_add_client(params: dict, dsn: str) -> dict:
    """Add a new client record."""
    import psycopg2

    name = params["name"].strip()
    phone = params.get("phone", "").strip()

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Check existing (idempotent)
            cur.execute(
                """SELECT id FROM fazle_clients
                   WHERE LOWER(name) = LOWER(%s) OR (phone = %s AND phone != '')
                   LIMIT 1""",
                (name, phone),
            )
            existing = cur.fetchone()
            if existing:
                return {
                    "success": True,
                    "duplicate": True,
                    "client_id": existing[0],
                    "message": f"Client '{name}' already exists (ID: {existing[0]}).",
                }
            cur.execute(
                """INSERT INTO fazle_clients (name, phone, created_at)
                   VALUES (%s, %s, NOW()) RETURNING id""",
                (name, phone),
            )
            cid = cur.fetchone()[0]
        conn.commit()

    return {
        "success": True,
        "duplicate": False,
        "client_id": cid,
        "message": f"Client '{name}' added successfully (ID: {cid}).",
    }


def _handler_update_company_name(params: dict, dsn: str) -> dict:
    """Update company name in owner knowledge (versioned)."""
    import psycopg2

    new_name = params["company_name"].strip()
    fact_id = "business:company_name"

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Deactivate existing versions
            cur.execute(
                "UPDATE fazle_owner_knowledge SET is_active = FALSE WHERE fact_id = %s AND is_active = TRUE",
                (fact_id,),
            )
            # Get next version
            cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM fazle_owner_knowledge WHERE fact_id = %s",
                (fact_id,),
            )
            next_ver = cur.fetchone()[0]
            # Insert new version
            cur.execute(
                """INSERT INTO fazle_owner_knowledge
                       (category, key, value, source, fact_id, version, is_active, created_at, updated_at)
                   VALUES ('business', 'company_name', %s, 'owner_action', %s, %s, TRUE, NOW(), NOW())""",
                (new_name, fact_id, next_ver),
            )
        conn.commit()

    return {"success": True, "message": f"Company name updated to '{new_name}'."}


def _handler_assign_guard(params: dict, dsn: str) -> dict:
    """Assign a guard to a client/location."""
    import psycopg2

    guard_name = params["guard_name"].strip()
    client_name = params.get("client_name", "").strip()
    location = params.get("location", "").strip()

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Check duplicate active assignment
            cur.execute(
                """SELECT id FROM fazle_guard_assignments
                   WHERE LOWER(guard_name) = LOWER(%s)
                     AND LOWER(client_name) = LOWER(%s)
                     AND LOWER(location) = LOWER(%s)
                     AND active = TRUE
                   LIMIT 1""",
                (guard_name, client_name, location),
            )
            existing = cur.fetchone()
            if existing:
                return {
                    "success": True,
                    "duplicate": True,
                    "assignment_id": existing[0],
                    "message": f"Guard '{guard_name}' already at '{location}' for '{client_name}'.",
                }
            cur.execute(
                """INSERT INTO fazle_guard_assignments
                       (guard_name, client_name, location, active, created_at)
                   VALUES (%s, %s, %s, TRUE, NOW()) RETURNING id""",
                (guard_name, client_name, location),
            )
            aid = cur.fetchone()[0]
        conn.commit()

    return {
        "success": True,
        "duplicate": False,
        "assignment_id": aid,
        "message": f"Guard '{guard_name}' assigned to '{client_name}' at '{location}'.",
    }


def _handler_set_pricing(params: dict, dsn: str) -> dict:
    """Set or update pricing for a service type."""
    import psycopg2

    stype = params["service_type"].strip()
    price = float(params["price"])

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO fazle_service_pricing (service_type, price, updated_at)
                   VALUES (%s, %s, NOW())
                   ON CONFLICT (service_type)
                   DO UPDATE SET price = EXCLUDED.price, updated_at = NOW()
                   RETURNING id""",
                (stype, price),
            )
            pid = cur.fetchone()[0]
        conn.commit()

    return {
        "success": True,
        "pricing_id": pid,
        "message": f"Pricing for '{stype}' set to {price} BDT.",
    }


# ── Action Registry ─────────────────────────────────────────

ACTION_REGISTRY: dict[str, ActionDef] = {
    "add_client": ActionDef(
        name="add_client",
        required_fields=("name",),
        optional_fields=("phone",),
        risk="medium",
        needs_confirmation=True,
        description="Add a new client to the system",
        idempotency_fields=("name", "phone"),
    ),
    "update_company_name": ActionDef(
        name="update_company_name",
        required_fields=("company_name",),
        risk="medium",
        needs_confirmation=True,
        description="Update the company name",
        idempotency_fields=("company_name",),
    ),
    "assign_guard": ActionDef(
        name="assign_guard",
        required_fields=("guard_name",),
        optional_fields=("client_name", "location"),
        risk="high",
        needs_confirmation=True,
        description="Assign a guard to a client/location",
        idempotency_fields=("guard_name", "client_name", "location"),
    ),
    "set_pricing": ActionDef(
        name="set_pricing",
        required_fields=("service_type", "price"),
        risk="high",
        needs_confirmation=True,
        description="Set or update pricing for a service type",
        idempotency_fields=("service_type",),
    ),
}

_ACTION_HANDLERS: dict[str, Callable] = {
    "add_client": _handler_add_client,
    "update_company_name": _handler_update_company_name,
    "assign_guard": _handler_assign_guard,
    "set_pricing": _handler_set_pricing,
}


# ── Table Setup ──────────────────────────────────────────────

def ensure_action_tables(dsn: str) -> None:
    """Create business tables required by action handlers."""
    try:
        import psycopg2

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fazle_clients (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(200) NOT NULL,
                        phone VARCHAR(50) DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name_lower
                        ON fazle_clients (LOWER(name));

                    CREATE TABLE IF NOT EXISTS fazle_guard_assignments (
                        id SERIAL PRIMARY KEY,
                        guard_name VARCHAR(200) NOT NULL,
                        client_name VARCHAR(200) DEFAULT '',
                        location VARCHAR(300) DEFAULT '',
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_guard_assign_active
                        ON fazle_guard_assignments (active) WHERE active = TRUE;

                    CREATE TABLE IF NOT EXISTS fazle_service_pricing (
                        id SERIAL PRIMARY KEY,
                        service_type VARCHAR(100) NOT NULL UNIQUE,
                        price NUMERIC(12,2) NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
            conn.commit()
        logger.info("Action engine tables ensured (fazle_clients, fazle_guard_assignments, fazle_service_pricing)")
    except Exception as e:
        logger.warning(f"Action engine table creation failed (non-fatal): {e}")


# ── Metrics ──────────────────────────────────────────────────

_ACTION_METRICS: dict[str, dict] = {}


def _track_metric(action: str, success: bool, elapsed_ms: float, error: str = "") -> None:
    m = _ACTION_METRICS.setdefault(
        action, {"total": 0, "success": 0, "fail": 0, "last_error": "", "total_ms": 0.0}
    )
    m["total"] += 1
    if success:
        m["success"] += 1
    else:
        m["fail"] += 1
        m["last_error"] = error[:200]
    m["total_ms"] += elapsed_ms


def get_action_metrics() -> dict:
    """Return per-action metrics summary."""
    result = {}
    for action, m in _ACTION_METRICS.items():
        result[action] = {
            "total": m["total"],
            "success": m["success"],
            "fail": m["fail"],
            "success_rate": round(m["success"] / m["total"] * 100, 1) if m["total"] else 0,
            "avg_ms": round(m["total_ms"] / m["total"], 1) if m["total"] else 0,
            "last_error": m["last_error"],
        }
    return result


# ── Main Execution Pipeline ──────────────────────────────────

def execute_registered_action(action_name: str, params: dict, dsn: str) -> dict:
    """
    Central pipeline: validate → dedup check → execute handler → track.
    Returns dict with success, message, result_data, execution_time_ms.
    """
    t0 = time.time()

    # 1. Registry lookup
    if action_name not in ACTION_REGISTRY:
        return {
            "success": False,
            "message": f"Unknown action: {action_name}",
            "result_data": {},
            "execution_time_ms": 0,
        }

    # 2. Validate
    ok, err = validate_action(action_name, params)
    if not ok:
        elapsed = round((time.time() - t0) * 1000, 1)
        _track_metric(action_name, False, elapsed, err)
        logger.warning(f"Action '{action_name}' validation failed: {err}")
        return {
            "success": False,
            "message": f"Validation failed: {err}",
            "result_data": {},
            "execution_time_ms": elapsed,
        }

    # 3. Idempotency check
    dedup_key = _build_dedup_key(action_name, params)
    if dedup_key and _already_executed(dsn, dedup_key):
        elapsed = round((time.time() - t0) * 1000, 1)
        _track_metric(action_name, True, elapsed)
        logger.info(f"Action '{action_name}' skipped (duplicate): {dedup_key}")
        return {
            "success": True,
            "message": "Already executed (duplicate skipped).",
            "result_data": {"_dedup_key": dedup_key, "duplicate": True},
            "execution_time_ms": elapsed,
        }

    # 4. Execute handler
    handler = _ACTION_HANDLERS.get(action_name)
    if not handler:
        elapsed = round((time.time() - t0) * 1000, 1)
        return {
            "success": False,
            "message": f"No handler for action: {action_name}",
            "result_data": {},
            "execution_time_ms": elapsed,
        }

    try:
        result = handler(params, dsn)
        elapsed = round((time.time() - t0) * 1000, 1)
        result["_dedup_key"] = dedup_key
        result["execution_time_ms"] = elapsed
        _track_metric(action_name, result.get("success", False), elapsed)
        logger.info(f"Action '{action_name}' executed: {result.get('message', '')}")
        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "result_data": result,
            "execution_time_ms": elapsed,
        }
    except Exception as e:
        elapsed = round((time.time() - t0) * 1000, 1)
        _track_metric(action_name, False, elapsed, str(e))
        logger.error(f"Action '{action_name}' handler failed: {e}")
        return {
            "success": False,
            "message": f"Execution error: {e}",
            "result_data": {},
            "execution_time_ms": elapsed,
        }


# ── Public Helpers ───────────────────────────────────────────

def is_registered_action(intent: str) -> bool:
    """Check if an intent maps to a registered action."""
    return intent in ACTION_REGISTRY


def get_action_def(intent: str) -> Optional[ActionDef]:
    """Get action definition by intent name."""
    return ACTION_REGISTRY.get(intent)


def action_needs_confirmation(intent: str) -> bool:
    """Return True if this registered action requires confirmation."""
    adef = ACTION_REGISTRY.get(intent)
    return adef.needs_confirmation if adef else False


# ════════════════════════════════════════════════════════════
# Phase 9 — Part 1: Rule-Based Intent Pre-Detection
# ════════════════════════════════════════════════════════════

_RULE_PATTERNS: list[tuple[re.Pattern, str, Callable]] = [
    # add_client
    (re.compile(r"(?:add|নতুন|যোগ)\s*(?:client|ক্লায়েন্ট|customer|কাস্টমার)", re.I), "add_client",
     lambda m, msg: _extract_params_after(msg, ("client", "ক্লায়েন্ট", "customer", "কাস্টমার"), "name")),
    # update_company_name
    (re.compile(r"(?:company\s*name|কোম্পানির?\s*নাম)\s*(?:change|update|হবে|এখন|set)", re.I), "update_company_name",
     lambda m, msg: _extract_params_after(msg, ("name", "নাম", "to", "হবে", "এখন"), "company_name")),
    # assign_guard
    (re.compile(r"(?:assign|পাঠাও|দাও|বসাও)\s*(?:guard|গার্ড|security)", re.I), "assign_guard",
     lambda m, msg: _extract_guard_params(msg)),
    # set_pricing
    (re.compile(r"(?:set\s*pric|দাম|price|মূল্য|rate)\s*(?:for|of|হবে|set)?", re.I), "set_pricing",
     lambda m, msg: _extract_pricing_params(msg)),
]


def _extract_params_after(msg: str, markers: tuple, field: str) -> dict:
    """Extract the text after the last marker as `field`."""
    lower = msg.lower()
    best_pos = -1
    for mk in markers:
        idx = lower.rfind(mk.lower())
        if idx > best_pos:
            best_pos = idx + len(mk)
    if best_pos > 0:
        val = msg[best_pos:].strip().strip("।.,:;-–—\"'").strip()
        if val:
            return {field: val}
    return {}


def _extract_guard_params(msg: str) -> dict:
    """Best-effort extraction of guard_name from message."""
    # Try to find a name-like token after guard/গার্ড keywords
    m = re.search(r"(?:guard|গার্ড|security)\s+(.+?)(?:\s+(?:to|at|তে|এ)\s+|$)", msg, re.I)
    params: dict = {}
    if m:
        params["guard_name"] = m.group(1).strip().strip("।.,:;")
    return params


def _extract_pricing_params(msg: str) -> dict:
    """Best-effort extraction of service_type + price."""
    params: dict = {}
    price_m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(?:টাকা|BDT|taka|tk)?", msg, re.I)
    if price_m:
        try:
            params["price"] = float(price_m.group(1).replace(",", ""))
        except ValueError:
            pass
    svc_m = re.search(r"(?:for|of|এর)\s+(.+?)(?:\s+(?:price|দাম|rate|মূল্য)|\s+\d|$)", msg, re.I)
    if svc_m:
        params["service_type"] = svc_m.group(1).strip().strip("।.,:;")
    return params


def detect_action_rule(message: str) -> Optional[tuple[str, dict]]:
    """
    Rule-based intent detection. Returns (intent, extracted_params) or None.
    Runs BEFORE LLM call to reduce inference dependency.
    """
    for pattern, intent, extractor in _RULE_PATTERNS:
        m = pattern.search(message)
        if m:
            params = extractor(m, message)
            logger.info(f"Rule-detected intent '{intent}' from message (params={list(params.keys())})")
            return intent, params
    return None


# ════════════════════════════════════════════════════════════
# Phase 9 — Part 2: Rollback System
# ════════════════════════════════════════════════════════════

_ROLLBACK_HANDLERS: dict[str, Callable] = {}


def _rollback_add_client(result_data: dict, dsn: str) -> dict:
    """Reverse an add_client by deleting the record."""
    import psycopg2
    cid = result_data.get("client_id")
    if not cid:
        return {"success": False, "message": "No client_id in action result."}
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_clients WHERE id = %s RETURNING name", (cid,))
            row = cur.fetchone()
        conn.commit()
    if row:
        return {"success": True, "message": f"Client '{row[0]}' (ID: {cid}) removed."}
    return {"success": False, "message": f"Client ID {cid} not found."}


def _rollback_update_company_name(result_data: dict, dsn: str) -> dict:
    """Revert company name to previous active version."""
    import psycopg2
    fact_id = "business:company_name"
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Deactivate current
            cur.execute(
                "UPDATE fazle_owner_knowledge SET is_active = FALSE WHERE fact_id = %s AND is_active = TRUE",
                (fact_id,),
            )
            # Reactivate previous version
            cur.execute(
                """UPDATE fazle_owner_knowledge SET is_active = TRUE
                   WHERE id = (
                       SELECT id FROM fazle_owner_knowledge
                       WHERE fact_id = %s AND is_active = FALSE
                       ORDER BY version DESC LIMIT 1
                   ) RETURNING value""",
                (fact_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if row:
        return {"success": True, "message": f"Company name reverted to '{row[0]}'."}
    return {"success": False, "message": "No previous version to revert to."}


def _rollback_assign_guard(result_data: dict, dsn: str) -> dict:
    """Deactivate a guard assignment."""
    import psycopg2
    aid = result_data.get("assignment_id")
    if not aid:
        return {"success": False, "message": "No assignment_id in action result."}
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fazle_guard_assignments SET active = FALSE WHERE id = %s AND active = TRUE RETURNING guard_name",
                (aid,),
            )
            row = cur.fetchone()
        conn.commit()
    if row:
        return {"success": True, "message": f"Guard assignment '{row[0]}' (ID: {aid}) deactivated."}
    return {"success": False, "message": f"Assignment ID {aid} not found or already inactive."}


def _rollback_set_pricing(result_data: dict, dsn: str) -> dict:
    """Remove a pricing record."""
    import psycopg2
    pid = result_data.get("pricing_id")
    if not pid:
        return {"success": False, "message": "No pricing_id in action result."}
    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fazle_service_pricing WHERE id = %s RETURNING service_type", (pid,))
            row = cur.fetchone()
        conn.commit()
    if row:
        return {"success": True, "message": f"Pricing for '{row[0]}' removed."}
    return {"success": False, "message": f"Pricing ID {pid} not found."}


_ROLLBACK_HANDLERS = {
    "add_client": _rollback_add_client,
    "update_company_name": _rollback_update_company_name,
    "assign_guard": _rollback_assign_guard,
    "set_pricing": _rollback_set_pricing,
}


def rollback_action(action_id: int, dsn: str) -> dict:
    """
    Rollback a previously executed action by audit ID.
    Returns dict with success, message.
    """
    import psycopg2

    if not dsn:
        return {"success": False, "message": "Database not configured."}

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT action_type, result_data, status, COALESCE(
                       (result_data->>'rolled_back')::boolean, FALSE
                   ) as rolled_back
                   FROM owner_action_audit WHERE id = %s""",
                (action_id,),
            )
            row = cur.fetchone()

    if not row:
        return {"success": False, "message": f"Action ID {action_id} not found."}

    action_type, result_data, status, already_rolled = row
    if status != "success":
        return {"success": False, "message": f"Action ID {action_id} was not successful — cannot rollback."}
    if already_rolled:
        return {"success": False, "message": f"Action ID {action_id} already rolled back."}

    handler = _ROLLBACK_HANDLERS.get(action_type)
    if not handler:
        return {"success": False, "message": f"No rollback handler for '{action_type}'."}

    if not isinstance(result_data, dict):
        try:
            result_data = json.loads(result_data) if result_data else {}
        except (json.JSONDecodeError, TypeError):
            result_data = {}

    t0 = time.time()
    try:
        res = handler(result_data, dsn)
    except Exception as e:
        logger.error(f"Rollback failed for action {action_id}: {e}")
        return {"success": False, "message": f"Rollback error: {e}"}

    elapsed = round((time.time() - t0) * 1000, 1)

    # Mark as rolled back in audit
    if res.get("success"):
        try:
            import psycopg2 as _pg2
            with _pg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE owner_action_audit
                           SET result_data = result_data || '{"rolled_back": true}'::jsonb
                           WHERE id = %s""",
                        (action_id,),
                    )
                conn.commit()
        except Exception:
            pass
        _track_metric(f"rollback:{action_type}", True, elapsed)
    else:
        _track_metric(f"rollback:{action_type}", False, elapsed, res.get("message", ""))

    return res


# ════════════════════════════════════════════════════════════
# Phase 9 — Part 3: Workflow Engine
# ════════════════════════════════════════════════════════════

WORKFLOW_REGISTRY: dict[str, list[str]] = {
    "onboard_client": ["add_client", "assign_guard", "set_pricing"],
}


def execute_workflow(workflow_name: str, step_params: dict, dsn: str) -> dict:
    """
    Execute a multi-step workflow. step_params is a dict keyed by action name,
    e.g. {"add_client": {"name": "X"}, "assign_guard": {"guard_name": "Y"}, ...}
    Stops on first failure. Returns overall result + per-step results.
    """
    steps = WORKFLOW_REGISTRY.get(workflow_name)
    if not steps:
        return {"success": False, "message": f"Unknown workflow: {workflow_name}", "steps": []}

    results: list[dict] = []
    for step in steps:
        params = step_params.get(step, {})
        res = execute_registered_action(step, params, dsn)
        results.append({"action": step, **res})
        if not res["success"]:
            logger.warning(f"Workflow '{workflow_name}' stopped at step '{step}': {res['message']}")
            return {
                "success": False,
                "message": f"Workflow stopped at '{step}': {res['message']}",
                "steps": results,
            }

    return {
        "success": True,
        "message": f"Workflow '{workflow_name}' completed ({len(steps)} steps).",
        "steps": results,
    }


# ════════════════════════════════════════════════════════════
# Phase 9 — Part 4: Role-Based Permissions
# ════════════════════════════════════════════════════════════

_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"*"},  # all actions
    "manager": {"add_client", "assign_guard", "set_pricing", "update_company_name"},
    "employee": set(),  # no actions
}


def can_execute(user_role: str, action_name: str) -> bool:
    """Check if a role is allowed to execute the given action."""
    allowed = _ROLE_PERMISSIONS.get(user_role, set())
    if "*" in allowed:
        return True
    # Managers cannot do critical actions
    adef = ACTION_REGISTRY.get(action_name)
    if adef and adef.risk == "critical" and user_role != "owner":
        return False
    return action_name in allowed


def can_rollback(user_role: str) -> bool:
    """Only owner can rollback."""
    return user_role == "owner"
