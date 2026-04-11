# ============================================================
# Phase 10: Autonomous Intelligence Layer
# Detection → Recommendation → Optional Execution (under owner control)
# ============================================================
from __future__ import annotations

import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("fazle-brain.autonomous-intelligence")


# ════════════════════════════════════════════════════════════
# Part 1: Event Detection Engine
# ════════════════════════════════════════════════════════════

# Each detector returns list of dicts: [{"event": ..., "entity": ..., "details": ...}]

def _detect_inactive_clients(dsn: str, days: int = 7) -> list[dict]:
    """Clients with no activity in the last N days."""
    import psycopg2
    events: list[dict] = []
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, phone, last_activity
                    FROM fazle_clients
                    WHERE last_activity < NOW() - INTERVAL '%s days'
                      AND active = TRUE
                    ORDER BY last_activity ASC
                    LIMIT 50
                """, (days,))
                for row in cur.fetchall():
                    days_ago = (datetime.utcnow() - row[3]).days if row[3] else days
                    events.append({
                        "event": "inactive_client",
                        "entity_id": row[0],
                        "entity_name": row[1] or "Unknown",
                        "details": {
                            "phone": row[2],
                            "last_activity": row[3].isoformat() if row[3] else None,
                            "days_inactive": days_ago,
                        },
                    })
    except Exception as e:
        logger.debug(f"inactive_clients detection skipped: {e}")
    return events


def _detect_unassigned_guards(dsn: str) -> list[dict]:
    """Active clients that have no guard assigned."""
    import psycopg2
    events: list[dict] = []
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id, c.name
                    FROM fazle_clients c
                    LEFT JOIN fazle_guard_assignments ga
                        ON ga.client_id = c.id AND ga.active = TRUE
                    WHERE c.active = TRUE
                      AND ga.id IS NULL
                    LIMIT 50
                """)
                for row in cur.fetchall():
                    events.append({
                        "event": "unassigned_guard",
                        "entity_id": row[0],
                        "entity_name": row[1] or "Unknown",
                        "details": {"client_id": row[0]},
                    })
    except Exception as e:
        logger.debug(f"unassigned_guards detection skipped: {e}")
    return events


def _detect_missing_pricing(dsn: str) -> list[dict]:
    """Active clients or services without pricing set."""
    import psycopg2
    events: list[dict] = []
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.id, c.name
                    FROM fazle_clients c
                    LEFT JOIN fazle_service_pricing sp
                        ON sp.client_id = c.id AND sp.active = TRUE
                    WHERE c.active = TRUE
                      AND sp.id IS NULL
                    LIMIT 50
                """)
                for row in cur.fetchall():
                    events.append({
                        "event": "pricing_missing",
                        "entity_id": row[0],
                        "entity_name": row[1] or "Unknown",
                        "details": {"client_id": row[0]},
                    })
    except Exception as e:
        logger.debug(f"missing_pricing detection skipped: {e}")
    return events


_EVENT_DETECTORS = [
    _detect_inactive_clients,
    _detect_unassigned_guards,
    _detect_missing_pricing,
]


def detect_events(dsn: str) -> list[dict]:
    """Run all event detectors and return combined event list."""
    all_events: list[dict] = []
    for detector in _EVENT_DETECTORS:
        try:
            all_events.extend(detector(dsn))
        except Exception as e:
            logger.warning(f"Detector {detector.__name__} failed: {e}")
    return all_events


# ════════════════════════════════════════════════════════════
# Part 2: Recommendation Engine + DB table
# ════════════════════════════════════════════════════════════

def ensure_recommendation_tables(dsn: str) -> None:
    """Create the ai_recommendations + ai_learning_weights tables if they don't exist."""
    import psycopg2
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_recommendations (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        event_type VARCHAR(100) NOT NULL,
                        entity_id INTEGER,
                        entity_name VARCHAR(200),
                        suggested_action VARCHAR(100) NOT NULL,
                        message TEXT NOT NULL,
                        details JSONB DEFAULT '{}',
                        priority_score REAL DEFAULT 0.5,
                        urgency VARCHAR(20) DEFAULT 'medium',
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        resolved_at TIMESTAMPTZ,
                        resolved_by VARCHAR(50),
                        execution_result JSONB,
                        feedback_score REAL DEFAULT 0.0,
                        learning_weight REAL DEFAULT 1.0
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_rec_status
                        ON ai_recommendations(status);
                    CREATE INDEX IF NOT EXISTS idx_ai_rec_created
                        ON ai_recommendations(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_ai_rec_priority
                        ON ai_recommendations(priority_score DESC);

                    -- Phase 11: Learning weights table
                    CREATE TABLE IF NOT EXISTS ai_learning_weights (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(100) NOT NULL,
                        action VARCHAR(100) NOT NULL,
                        weight REAL NOT NULL DEFAULT 1.0,
                        approve_count INTEGER DEFAULT 0,
                        dismiss_count INTEGER DEFAULT 0,
                        last_updated TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(event_type, action)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_lw_event
                        ON ai_learning_weights(event_type, action);
                """)
                # Add Phase 11 columns if missing (safe for existing tables)
                for col, coltype in [
                    ("feedback_score", "REAL DEFAULT 0.0"),
                    ("learning_weight", "REAL DEFAULT 1.0"),
                ]:
                    cur.execute(f"""
                        ALTER TABLE ai_recommendations
                        ADD COLUMN IF NOT EXISTS {col} {coltype}
                    """)
            conn.commit()
        logger.info("ai_recommendations + ai_learning_weights tables ensured")
    except Exception as e:
        logger.warning(f"ai_recommendations table creation failed: {e}")


# ════════════════════════════════════════════════════════════
# Part 3: Action Mapping (event → suggested_action)
# ════════════════════════════════════════════════════════════

_EVENT_ACTION_MAP: dict[str, dict] = {
    "inactive_client": {
        "suggested_action": "follow_up_client",
        "message_template": "Client '{entity_name}' inactive for {days_inactive} days. Send follow-up?",
        "risk": "low",
    },
    "unassigned_guard": {
        "suggested_action": "assign_guard",
        "message_template": "Client '{entity_name}' has no guard assigned. Assign one?",
        "risk": "medium",
    },
    "pricing_missing": {
        "suggested_action": "set_pricing",
        "message_template": "Client '{entity_name}' has no pricing set. Set pricing?",
        "risk": "medium",
    },
}


# ════════════════════════════════════════════════════════════
# Part 4: Priority Scoring
# ════════════════════════════════════════════════════════════

_URGENCY_WEIGHTS = {
    "inactive_client": 0.6,   # moderate urgency
    "unassigned_guard": 0.8,  # high — security risk
    "pricing_missing": 0.5,   # low-medium — revenue risk
}


def _calculate_priority(event: dict, learning_weight: float = 1.0) -> tuple[float, str]:
    """Return (score 0-1, urgency label) based on event type + details + learning."""
    base = _URGENCY_WEIGHTS.get(event["event"], 0.5)

    # Boost by staleness for inactive clients
    if event["event"] == "inactive_client":
        days = event.get("details", {}).get("days_inactive", 7)
        # Scale: 7d=0.6, 14d=0.75, 30d=0.9
        base = min(0.95, base + (days - 7) * 0.01)

    # Phase 11: Apply learning weight (adaptive scoring)
    base = min(0.99, max(0.05, base * learning_weight))

    if base >= 0.8:
        urgency = "high"
    elif base >= 0.5:
        urgency = "medium"
    else:
        urgency = "low"

    return round(base, 3), urgency


# ════════════════════════════════════════════════════════════
# Part 5: Generate and Store Recommendations
# ════════════════════════════════════════════════════════════

def _recommendation_exists(dsn: str, event_type: str, entity_id: int) -> bool:
    """Check if a pending/approved recommendation already exists for this event+entity."""
    import psycopg2
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM ai_recommendations
                    WHERE event_type = %s AND entity_id = %s
                      AND status IN ('pending', 'approved')
                    LIMIT 1
                """, (event_type, entity_id))
                return cur.fetchone() is not None
    except Exception:
        return False


def generate_recommendations(dsn: str) -> list[dict]:
    """Detect events → generate scored recommendations → store new ones in DB."""
    import psycopg2
    events = detect_events(dsn)
    new_recs: list[dict] = []

    # Phase 11: Load learning weights once per scan
    weights = _load_learning_weights(dsn)

    for event in events:
        mapping = _EVENT_ACTION_MAP.get(event["event"])
        if not mapping:
            continue

        entity_id = event.get("entity_id")
        # Skip if a pending recommendation already exists
        if entity_id and _recommendation_exists(dsn, event["event"], entity_id):
            continue

        # Phase 11: Get learned weight for this event+action pair
        lw_key = f"{event['event']}:{mapping['suggested_action']}"
        lw = weights.get(lw_key, 1.0)

        # Pattern learning: if weight is very low (<0.2), skip entirely
        if lw < 0.2:
            continue

        score, urgency = _calculate_priority(event, learning_weight=lw)

        # Build human-readable message
        tpl_vars = {"entity_name": event.get("entity_name", "?")}
        tpl_vars.update(event.get("details", {}))
        try:
            message = mapping["message_template"].format(**tpl_vars)
        except KeyError:
            message = f"{event['event']} detected for {event.get('entity_name', '?')}"

        rec = {
            "event_type": event["event"],
            "entity_id": entity_id,
            "entity_name": event.get("entity_name"),
            "suggested_action": mapping["suggested_action"],
            "message": message,
            "details": event.get("details", {}),
            "priority_score": score,
            "urgency": urgency,
            "learning_weight": lw,
        }

        # Store in DB
        try:
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ai_recommendations
                            (event_type, entity_id, entity_name, suggested_action,
                             message, details, priority_score, urgency, learning_weight)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        rec["event_type"], rec["entity_id"], rec["entity_name"],
                        rec["suggested_action"], rec["message"],
                        json.dumps(rec["details"]), rec["priority_score"],
                        rec["urgency"], rec["learning_weight"],
                    ))
                    rec["id"] = cur.fetchone()[0]
                conn.commit()
            new_recs.append(rec)
            logger.info(f"Recommendation created: {rec['event_type']} → {rec['suggested_action']} "
                        f"for '{rec['entity_name']}' (priority={rec['priority_score']}, lw={lw})")
        except Exception as e:
            logger.warning(f"Failed to store recommendation: {e}")

    return new_recs


# ════════════════════════════════════════════════════════════
# Part 6: Owner Approval / Dismiss / Auto-Execution
# ════════════════════════════════════════════════════════════

AUTO_EXECUTION_ENABLED = os.getenv("AI_AUTO_EXECUTION", "false").lower() == "true"


def get_pending_recommendations(dsn: str, limit: int = 30) -> list[dict]:
    """Fetch pending recommendations sorted by priority."""
    import psycopg2
    recs: list[dict] = []
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, created_at, event_type, entity_id, entity_name,
                           suggested_action, message, details, priority_score,
                           urgency, status
                    FROM ai_recommendations
                    WHERE status = 'pending'
                    ORDER BY priority_score DESC, created_at ASC
                    LIMIT %s
                """, (limit,))
                for r in cur.fetchall():
                    recs.append({
                        "id": r[0],
                        "created_at": r[1].isoformat() if r[1] else None,
                        "event_type": r[2], "entity_id": r[3],
                        "entity_name": r[4], "suggested_action": r[5],
                        "message": r[6],
                        "details": r[7] if isinstance(r[7], dict) else {},
                        "priority_score": r[8], "urgency": r[9],
                        "status": r[10],
                    })
    except Exception as e:
        logger.warning(f"Failed to fetch recommendations: {e}")
    return recs


def get_all_recommendations(dsn: str, limit: int = 50, status_filter: str | None = None) -> list[dict]:
    """Fetch recommendations with optional status filter, sorted by priority."""
    import psycopg2
    recs: list[dict] = []
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                if status_filter:
                    cur.execute("""
                        SELECT id, created_at, event_type, entity_id, entity_name,
                               suggested_action, message, details, priority_score,
                               urgency, status, resolved_at, resolved_by, execution_result
                        FROM ai_recommendations
                        WHERE status = %s
                        ORDER BY priority_score DESC, created_at DESC
                        LIMIT %s
                    """, (status_filter, limit))
                else:
                    cur.execute("""
                        SELECT id, created_at, event_type, entity_id, entity_name,
                               suggested_action, message, details, priority_score,
                               urgency, status, resolved_at, resolved_by, execution_result
                        FROM ai_recommendations
                        ORDER BY
                            CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1
                                        WHEN 'executed' THEN 2 WHEN 'dismissed' THEN 3 END,
                            priority_score DESC, created_at DESC
                        LIMIT %s
                    """, (limit,))
                for r in cur.fetchall():
                    recs.append({
                        "id": r[0],
                        "created_at": r[1].isoformat() if r[1] else None,
                        "event_type": r[2], "entity_id": r[3],
                        "entity_name": r[4], "suggested_action": r[5],
                        "message": r[6],
                        "details": r[7] if isinstance(r[7], dict) else {},
                        "priority_score": r[8], "urgency": r[9],
                        "status": r[10],
                        "resolved_at": r[11].isoformat() if r[11] else None,
                        "resolved_by": r[12],
                        "execution_result": r[13] if isinstance(r[13], dict) else {},
                    })
    except Exception as e:
        logger.warning(f"Failed to fetch recommendations: {e}")
    return recs


def approve_recommendation(rec_id: int, dsn: str, execute_now: bool = True) -> dict:
    """
    Approve a recommendation. If execute_now=True, also execute the mapped action.
    Returns {"success": bool, "message": str, "execution": ...}.
    """
    import psycopg2
    from action_engine import is_registered_action, execute_registered_action

    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, event_type, entity_id, entity_name,
                           suggested_action, details, status, priority_score
                    FROM ai_recommendations WHERE id = %s
                """, (rec_id,))
                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": f"Recommendation {rec_id} not found"}
                if row[6] != "pending":
                    return {"success": False, "message": f"Recommendation already {row[6]}"}

                event_type = row[1]
                action = row[4]
                details = row[5] if isinstance(row[5], dict) else {}

                # Mark as approved + set positive feedback
                cur.execute("""
                    UPDATE ai_recommendations
                    SET status = 'approved', resolved_at = NOW(), resolved_by = 'owner',
                        feedback_score = 1.0
                    WHERE id = %s
                """, (rec_id,))
            conn.commit()

        # Phase 11: Record positive feedback in learning weights
        _record_feedback(dsn, event_type, action, approved=True)

        execution = None
        if execute_now and is_registered_action(action):
            execution = execute_registered_action(action, details, dsn)
            # Update with execution result
            final_status = "executed" if execution.get("success") else "approved"
            try:
                with psycopg2.connect(dsn) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE ai_recommendations
                            SET status = %s, execution_result = %s
                            WHERE id = %s
                        """, (final_status, json.dumps(execution), rec_id))
                    conn.commit()
            except Exception:
                pass

        return {
            "success": True,
            "message": f"Recommendation {rec_id} approved" + (" and executed" if execution else ""),
            "execution": execution,
        }

    except Exception as e:
        logger.error(f"Approve recommendation {rec_id} failed: {e}")
        return {"success": False, "message": str(e)}


def dismiss_recommendation(rec_id: int, dsn: str) -> dict:
    """Dismiss a recommendation. No action taken."""
    import psycopg2
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, event_type, suggested_action
                    FROM ai_recommendations WHERE id = %s
                """, (rec_id,))
                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": f"Recommendation {rec_id} not found"}
                if row[0] != "pending":
                    return {"success": False, "message": f"Recommendation already {row[0]}"}

                event_type, action = row[1], row[2]

                cur.execute("""
                    UPDATE ai_recommendations
                    SET status = 'dismissed', resolved_at = NOW(), resolved_by = 'owner',
                        feedback_score = -1.0
                    WHERE id = %s
                """, (rec_id,))
            conn.commit()
        # Phase 11: Record negative feedback in learning weights
        _record_feedback(dsn, event_type, action, approved=False)
        logger.info(f"Recommendation {rec_id} dismissed")
        return {"success": True, "message": f"Recommendation {rec_id} dismissed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ════════════════════════════════════════════════════════════
# Part 7: Auto-Execution (controlled, low-risk only)
# ════════════════════════════════════════════════════════════

_LOW_RISK_ACTIONS = {"follow_up_client"}  # Only truly safe actions


def run_auto_execution(dsn: str) -> list[dict]:
    """
    If AUTO_EXECUTION_ENABLED, auto-approve + execute LOW-risk pending recommendations.
    High/medium risk actions are NEVER auto-executed.
    Returns list of auto-executed results.
    """
    if not AUTO_EXECUTION_ENABLED:
        return []

    results: list[dict] = []
    pending = get_pending_recommendations(dsn, limit=20)

    for rec in pending:
        action = rec.get("suggested_action", "")
        # Safety: only low-risk actions
        if action not in _LOW_RISK_ACTIONS:
            continue
        # Double-check via action mapping risk
        mapping = _EVENT_ACTION_MAP.get(rec.get("event_type", ""), {})
        if mapping.get("risk", "high") != "low":
            continue

        logger.info(f"Auto-executing recommendation {rec['id']}: {action}")
        result = approve_recommendation(rec["id"], dsn, execute_now=True)
        results.append({"rec_id": rec["id"], "action": action, **result})

    return results


# ════════════════════════════════════════════════════════════
# Part 8: Background Worker (called periodically)
# ════════════════════════════════════════════════════════════

_LAST_SCAN: float = 0.0
_SCAN_INTERVAL_SECONDS = int(os.getenv("AI_SCAN_INTERVAL", "300"))  # default 5 min


def periodic_intelligence_scan(dsn: str) -> dict:
    """
    Run detection + recommendation + optional auto-execution.
    Called from a background loop or manual trigger.
    Returns scan summary.
    """
    global _LAST_SCAN
    now = time.time()

    # Throttle: don't scan more often than interval
    if now - _LAST_SCAN < _SCAN_INTERVAL_SECONDS:
        return {"skipped": True, "reason": "throttled", "next_in_seconds": int(_SCAN_INTERVAL_SECONDS - (now - _LAST_SCAN))}

    _LAST_SCAN = now
    t0 = time.time()

    new_recs = generate_recommendations(dsn)
    auto_results = run_auto_execution(dsn)

    elapsed = round((time.time() - t0) * 1000, 1)
    summary = {
        "skipped": False,
        "new_recommendations": len(new_recs),
        "auto_executed": len(auto_results),
        "scan_time_ms": elapsed,
        "auto_execution_enabled": AUTO_EXECUTION_ENABLED,
    }
    logger.info(f"Intelligence scan: {summary}")
    return summary


# ════════════════════════════════════════════════════════════
# Part 9: Recommendation Statistics
# ════════════════════════════════════════════════════════════

def get_recommendation_stats(dsn: str) -> dict:
    """Get aggregated recommendation statistics."""
    import psycopg2
    stats = {"total": 0, "pending": 0, "approved": 0, "executed": 0, "dismissed": 0}
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT status, COUNT(*) FROM ai_recommendations
                    GROUP BY status
                """)
                for row in cur.fetchall():
                    stats[row[0]] = row[1]
                    stats["total"] += row[1]
    except Exception as e:
        logger.debug(f"Recommendation stats query failed: {e}")
    return stats


# ════════════════════════════════════════════════════════════
# Phase 11: Self-Learning Intelligence Engine
# ════════════════════════════════════════════════════════════

# Safety: high-risk actions can never have weight boosted above this cap
_HIGH_RISK_ACTIONS = {"assign_guard", "set_pricing"}
_HIGH_RISK_WEIGHT_CAP = 1.5
_LOW_RISK_WEIGHT_CAP = 3.0
_WEIGHT_FLOOR = 0.05  # Never go below this (prevents permanent suppression)


def _load_learning_weights(dsn: str) -> dict[str, float]:
    """Load learning weights from DB. Returns dict of 'event_type:action' → weight."""
    import psycopg2
    weights: dict[str, float] = {}
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT event_type, action, weight FROM ai_learning_weights")
                for row in cur.fetchall():
                    weights[f"{row[0]}:{row[1]}"] = float(row[2])
    except Exception as e:
        logger.debug(f"Failed to load learning weights: {e}")
    return weights


def _record_feedback(dsn: str, event_type: str, action: str, approved: bool) -> None:
    """
    Record feedback in ai_learning_weights via upsert.
    Approved → weight * 1.1 (boost), Dismissed → weight * 0.85 (reduce).
    Safety: high-risk actions capped, weight never below floor.
    """
    import psycopg2
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                # Upsert the learning weight row
                if approved:
                    cur.execute("""
                        INSERT INTO ai_learning_weights (event_type, action, weight, approve_count, dismiss_count, last_updated)
                        VALUES (%s, %s, 1.1, 1, 0, NOW())
                        ON CONFLICT (event_type, action) DO UPDATE SET
                            weight = LEAST(%s, GREATEST(%s, ai_learning_weights.weight * 1.1)),
                            approve_count = ai_learning_weights.approve_count + 1,
                            last_updated = NOW()
                    """, (
                        event_type, action,
                        _HIGH_RISK_WEIGHT_CAP if action in _HIGH_RISK_ACTIONS else _LOW_RISK_WEIGHT_CAP,
                        _WEIGHT_FLOOR,
                    ))
                else:
                    cur.execute("""
                        INSERT INTO ai_learning_weights (event_type, action, weight, approve_count, dismiss_count, last_updated)
                        VALUES (%s, %s, 0.85, 0, 1, NOW())
                        ON CONFLICT (event_type, action) DO UPDATE SET
                            weight = GREATEST(%s, ai_learning_weights.weight * 0.85),
                            dismiss_count = ai_learning_weights.dismiss_count + 1,
                            last_updated = NOW()
                    """, (event_type, action, _WEIGHT_FLOOR))
            conn.commit()
        logger.info(f"Learning feedback recorded: {event_type}:{action} approved={approved}")
    except Exception as e:
        logger.warning(f"Failed to record learning feedback: {e}")


def get_learning_stats(dsn: str) -> dict:
    """Get learning weight statistics for dashboard/API."""
    import psycopg2
    stats = {"weights": [], "total_feedback": 0, "patterns": []}
    try:
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT event_type, action, weight, approve_count, dismiss_count, last_updated
                    FROM ai_learning_weights
                    ORDER BY last_updated DESC
                """)
                for row in cur.fetchall():
                    total = row[3] + row[4]
                    stats["weights"].append({
                        "event_type": row[0],
                        "action": row[1],
                        "weight": round(row[2], 3),
                        "approve_count": row[3],
                        "dismiss_count": row[4],
                        "total_feedback": total,
                        "approval_rate": round(row[3] / total, 2) if total > 0 else 0,
                        "last_updated": row[5].isoformat() if row[5] else None,
                    })
                    stats["total_feedback"] += total

                # Behavior patterns: identify consistently approved/dismissed
                cur.execute("""
                    SELECT event_type, action, weight, approve_count, dismiss_count
                    FROM ai_learning_weights
                    WHERE (approve_count + dismiss_count) >= 3
                """)
                for row in cur.fetchall():
                    total = row[3] + row[4]
                    rate = row[3] / total if total > 0 else 0
                    if rate >= 0.8:
                        stats["patterns"].append({
                            "event_type": row[0], "action": row[1],
                            "pattern": "consistently_approved",
                            "approval_rate": round(rate, 2), "weight": round(row[2], 3),
                        })
                    elif rate <= 0.2:
                        stats["patterns"].append({
                            "event_type": row[0], "action": row[1],
                            "pattern": "consistently_dismissed",
                            "approval_rate": round(rate, 2), "weight": round(row[2], 3),
                        })
    except Exception as e:
        logger.debug(f"Learning stats query failed: {e}")
    return stats
