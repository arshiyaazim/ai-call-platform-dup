# ============================================================
# tests/test_recruitment.py  —  Sprint-3 WhatsApp Candidate Funnel
# 100% monkeypatched — no real DB or HTTP
# ============================================================
import os
import sys
import types
import pytest
from datetime import date, timedelta

# ── Bootstrap ────────────────────────────────────────────────
WBOM_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WBOM_DIR not in sys.path:
    sys.path.insert(0, WBOM_DIR)

# ── psycopg2 stub ─────────────────────────────────────────────
if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    extras_stub   = types.ModuleType("psycopg2.extras")
    pool_stub     = types.ModuleType("psycopg2.pool")

    class _ThreadedConnectionPool:
        def __init__(self, *a, **kw): pass
        def getconn(self): return _FakeConn()
        def putconn(self, c): pass

    class _RealDictCursor: pass

    class _FakeConn:
        def cursor(self, *a, **kw): return _FakeCursor()
        def commit(self): pass
        def rollback(self): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _FakeCursor:
        def execute(self, *a, **kw): pass
        def fetchone(self): return None
        def fetchall(self): return []
        def __enter__(self): return self
        def __exit__(self, *a): pass

    pool_stub.ThreadedConnectionPool = _ThreadedConnectionPool
    extras_stub.RealDictCursor       = _RealDictCursor
    psycopg2_stub.extras = extras_stub
    psycopg2_stub.pool   = pool_stub
    sys.modules["psycopg2"]        = psycopg2_stub
    sys.modules["psycopg2.extras"] = extras_stub
    sys.modules["psycopg2.pool"]   = pool_stub

# ── prometheus stub ───────────────────────────────────────────
if "prometheus_fastapi_instrumentator" not in sys.modules:
    pfi = types.ModuleType("prometheus_fastapi_instrumentator")
    class _Inst:
        def instrument(self, *a, **kw): return self
        def expose(self, *a, **kw): return self
    pfi.Instrumentator = _Inst
    sys.modules["prometheus_fastapi_instrumentator"] = pfi

from fastapi.testclient import TestClient


# ── App fixture ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from main import app
    return TestClient(app)


# ────────────────────────────────────────────────────────────
# Unit tests — services.recruitment (pure logic, no HTTP)
# ────────────────────────────────────────────────────────────

class TestComputeScore:
    """Test the deterministic scoring function directly."""

    def _base(self, **overrides):
        base = {
            "full_name": "Rahim Uddin",
            "age": 28,
            "area": "Dhaka",
            "job_preference": "Escort",
            "experience_years": 6,
            "available_join_date": (date.today() + timedelta(days=2)).isoformat(),
        }
        base.update(overrides)
        return base

    def test_hot_candidate_full_profile(self):
        from services.recruitment import compute_score
        score, bucket = compute_score(self._base())
        # 60 (exp≥6) + 20 (quick join) + 10 (Escort) + 10 (complete) = 100
        assert score == 100
        assert bucket == "hot"

    def test_warm_candidate_medium_exp(self):
        from services.recruitment import compute_score
        c = self._base(
            experience_years=3,
            job_preference="Supervisor",          # no position bonus
            available_join_date=(date.today() + timedelta(days=30)).isoformat(),
        )
        # 40 (exp 3-5) + 0 (late join) + 0 (position) + 10 (complete) = 50
        score, bucket = compute_score(c)
        assert 40 <= score < 70
        assert bucket == "warm"

    def test_cold_candidate_no_experience(self):
        from services.recruitment import compute_score
        c = {
            "full_name": "Karim",
            "age": 22,
            "area": "Sylhet",
            "job_preference": "Labor",
            "experience_years": 0,
            "available_join_date": (date.today() + timedelta(days=60)).isoformat(),
        }
        # 0 + 0 + 0 + 10 (complete) = 10
        score, bucket = compute_score(c)
        assert score < 40
        assert bucket == "cold"

    def test_complete_profile_bonus(self):
        """Complete profile should add 10 pts over incomplete."""
        from services.recruitment import compute_score
        complete = self._base(experience_years=1, job_preference="Labor",
                              available_join_date=(date.today() + timedelta(days=30)).isoformat())
        incomplete = {k: v for k, v in complete.items() if k != "area"}

        score_c, _ = compute_score(complete)
        score_i, _ = compute_score(incomplete)
        assert score_c == score_i + 10

    def test_score_capped_at_100(self):
        from services.recruitment import compute_score
        c = self._base(experience_years=100)
        score, _ = compute_score(c)
        assert score <= 100


# ── Parsing helpers ────────────────────────────────────────

class TestParsers:
    def test_parse_age_valid(self):
        from services.recruitment import _parse_age
        assert _parse_age("আমার বয়স 25") == 25
        assert _parse_age("30") == 30

    def test_parse_age_out_of_range(self):
        from services.recruitment import _parse_age
        assert _parse_age("5") is None
        assert _parse_age("150") is None

    def test_parse_job_preference_digit(self):
        from services.recruitment import _parse_job_preference
        assert _parse_job_preference("3") == "Security Guard"
        assert _parse_job_preference("1") == "Escort"

    def test_parse_job_preference_name(self):
        from services.recruitment import _parse_job_preference
        assert _parse_job_preference("security guard") == "Security Guard"
        assert _parse_job_preference("supervisor") == "Supervisor"

    def test_parse_experience_int(self):
        from services.recruitment import _parse_experience
        assert _parse_experience("5 years") == 5
        assert _parse_experience("০ বছর 3") == 0

    def test_parse_join_date_iso(self):
        from services.recruitment import _parse_join_date
        assert _parse_join_date("2025-07-01") == date(2025, 7, 1)

    def test_parse_join_date_ddmmyyyy(self):
        from services.recruitment import _parse_join_date
        assert _parse_join_date("01/07/2025") == date(2025, 7, 1)
        assert _parse_join_date("01-07-2025") == date(2025, 7, 1)

    def test_parse_join_date_invalid(self):
        from services.recruitment import _parse_join_date
        assert _parse_join_date("asap") is None


# ────────────────────────────────────────────────────────────
# HTTP integration tests — monkeypatched
# ────────────────────────────────────────────────────────────

# ── Intake: new candidate trigger ──────────────────────────

def test_intake_trigger_creates_candidate(client, monkeypatch):
    """New phone + trigger keyword → candidate created, name question returned."""
    import services.recruitment as svc

    created_ids = []

    def mock_get_by_phone(phone):
        return None  # unknown phone

    def mock_insert_row(table, data):
        if table == "wbom_candidates":
            created_ids.append(1)
            return 1
        return 99  # conversation log

    monkeypatch.setattr(svc, "_get_candidate_by_phone", mock_get_by_phone)
    monkeypatch.setattr("database.insert_row", mock_insert_row)
    monkeypatch.setattr(svc, "insert_row", mock_insert_row)
    monkeypatch.setattr(svc, "_log_conversation", lambda *a, **kw: None)

    resp = client.post("/api/wbom/recruitment/intake", json={
        "phone": "+8801900000001",
        "message": "আমি job করতে চাই",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "created"
    assert body["candidate_id"] == 1
    assert "নাম" in body["reply"] or "name" in body["reply"].lower()


def test_intake_no_trigger_ignored(client, monkeypatch):
    """Unknown phone without trigger keyword → ignored, no reply."""
    import services.recruitment as svc

    monkeypatch.setattr(svc, "_get_candidate_by_phone", lambda phone: None)

    resp = client.post("/api/wbom/recruitment/intake", json={
        "phone": "+8801900000002",
        "message": "Hello there",
    })
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored"


def test_intake_collecting_advances_step(client, monkeypatch):
    """Candidate in 'collecting' stage → answer stored, next question returned."""
    import services.recruitment as svc

    existing = {
        "candidate_id": 5,
        "phone": "+8801900000005",
        "funnel_stage": "collecting",
        "collection_step": "age",
        "full_name": "Rahim",
        "experience_years": None,
        "available_join_date": None,
        "age": None,
        "area": None,
        "job_preference": None,
    }

    monkeypatch.setattr(svc, "_get_candidate_by_phone", lambda p: existing)
    monkeypatch.setattr(svc, "_log_conversation", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "update_row", lambda *a, **kw: None)

    resp = client.post("/api/wbom/recruitment/intake", json={
        "phone": "+8801900000005",
        "message": "28",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "collecting"
    assert body["candidate_id"] == 5
    # Should now ask about area
    assert "এলাকা" in body["reply"] or "area" in body["reply"].lower() or "কোথায়" in body["reply"]


def test_intake_already_applied_message(client, monkeypatch):
    """Candidate past collecting stage → already-applied message."""
    import services.recruitment as svc

    existing = {
        "candidate_id": 7,
        "phone": "+8801900000007",
        "funnel_stage": "assigned",
        "collection_step": None,
    }
    monkeypatch.setattr(svc, "_get_candidate_by_phone", lambda p: existing)

    resp = client.post("/api/wbom/recruitment/intake", json={
        "phone": "+8801900000007",
        "message": "আমি কি কাজ পেয়েছি?",
    })
    assert resp.status_code == 200
    assert resp.json()["action"] == "already_applied"


# ── Score endpoint ────────────────────────────────────────

def test_rescore_candidate(client, monkeypatch):
    """POST /candidates/{id}/score returns score + bucket."""
    import services.recruitment as svc

    candidate_data = {
        "candidate_id": 10,
        "full_name": "Jamal",
        "age": 30,
        "area": "Chittagong",
        "job_preference": "Escort",
        "experience_years": 4,
        "available_join_date": (date.today() + timedelta(days=3)).isoformat(),
    }

    monkeypatch.setattr(svc, "_get_candidate_by_id", lambda cid: candidate_data)
    monkeypatch.setattr(svc, "update_row", lambda *a, **kw: None)

    resp = client.post("/api/wbom/recruitment/candidates/10/score")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_id"] == 10
    assert 0 <= body["score"] <= 100
    assert body["score_bucket"] in ("hot", "warm", "cold")


def test_rescore_not_found(client, monkeypatch):
    import services.recruitment as svc
    monkeypatch.setattr(svc, "_get_candidate_by_id", lambda cid: None)

    resp = client.post("/api/wbom/recruitment/candidates/999/score")
    assert resp.status_code == 404


# ── Assign recruiter ────────────────────────────────────

def test_assign_recruiter(client, monkeypatch):
    import services.recruitment as svc

    candidate_data = {"candidate_id": 20, "funnel_stage": "scored", "phone": "+880199"}
    monkeypatch.setattr(svc, "_get_candidate_by_id", lambda cid: candidate_data)
    monkeypatch.setattr(svc, "update_row", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_create_reminder", lambda *a, **kw: None)

    resp = client.post("/api/wbom/recruitment/candidates/20/assign",
                       json={"recruiter_name": "Rashed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["assigned_recruiter"] == "Rashed"
    assert body["funnel_stage"] == "assigned"


# ── Stage advance ───────────────────────────────────────

def test_advance_stage_valid(client, monkeypatch):
    import services.recruitment as svc

    candidate_data = {"candidate_id": 30, "funnel_stage": "assigned"}
    monkeypatch.setattr(svc, "_get_candidate_by_id", lambda cid: candidate_data)
    monkeypatch.setattr(svc, "update_row", lambda *a, **kw: None)

    resp = client.post("/api/wbom/recruitment/candidates/30/advance",
                       json={"to_stage": "contacted"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["from_stage"] == "assigned"
    assert body["to_stage"] == "contacted"


def test_advance_stage_invalid_transition(client, monkeypatch):
    import services.recruitment as svc

    candidate_data = {"candidate_id": 31, "funnel_stage": "new"}
    monkeypatch.setattr(svc, "_get_candidate_by_id", lambda cid: candidate_data)

    resp = client.post("/api/wbom/recruitment/candidates/31/advance",
                       json={"to_stage": "hired"})
    assert resp.status_code == 422


# ── Owner metrics ───────────────────────────────────────

def test_metrics_shape(client, monkeypatch):
    """GET /recruitment/metrics returns expected keys."""
    import services.recruitment as svc

    def mock_execute_query(sql, params):
        # New-leads-today query: single COUNT with date filter, no GROUP BY
        if "COUNT(*) AS cnt" in sql and "created_at >=" in sql and "GROUP BY" not in sql:
            return [{"cnt": 5}]
        # Total/hired/rejected aggregation (unique: has both 'total' alias and 'rejected')
        if "AS total" in sql and "AS rejected" in sql:
            return [{"total": 20, "hired": 4, "rejected": 2}]
        # Funnel breakdown: GROUP BY funnel_stage
        if "GROUP BY funnel_stage" in sql:
            return [{"funnel_stage": "scored", "cnt": 10}]
        # Recruiter performance: GROUP BY assigned_recruiter
        if "GROUP BY assigned_recruiter" in sql:
            return [{"assigned_recruiter": "Rashed", "assigned_count": 8, "hired_count": 2}]
        # No-response leads
        if "last_contact_at" in sql and "assigned" in sql:
            return []
        return []

    monkeypatch.setattr(svc, "execute_query", mock_execute_query)

    resp = client.get("/api/wbom/recruitment/metrics")
    assert resp.status_code == 200
    body = resp.json()

    required_keys = {
        "ref_date", "new_leads_today", "total_this_month", "hired_this_month",
        "conversion_rate", "funnel_breakdown", "recruiter_performance",
        "no_response_leads",
    }
    assert required_keys.issubset(body.keys())
    assert body["new_leads_today"] == 5
    assert body["conversion_rate"] == pytest.approx(22.2, abs=0.5)


def test_metrics_zero_division_safe(client, monkeypatch):
    """Metrics with no candidates should not raise division errors."""
    import services.recruitment as svc

    def mock_zero(sql, params):
        if "COUNT(*) AS cnt" in sql and "GROUP BY" not in sql:
            return [{"cnt": 0}]
        if "AS total" in sql and "AS rejected" in sql:
            return [{"total": 0, "hired": 0, "rejected": 0}]
        return []
    monkeypatch.setattr(svc, "execute_query", mock_zero)

    resp = client.get("/api/wbom/recruitment/metrics")
    assert resp.status_code == 200
    assert resp.json()["conversion_rate"] == 0.0
