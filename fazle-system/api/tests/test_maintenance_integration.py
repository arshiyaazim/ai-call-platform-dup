# ============================================================
# Integration Tests — Maintenance Console API Endpoints
# Uses FastAPI TestClient with a lightweight test app
# ============================================================
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure API directory is in path (conftest handles external module mocks)
api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Set env vars before any imports that need them
os.environ.setdefault("FAZLE_JWT_SECRET", "test-secret-key-for-integration-tests")
os.environ.setdefault("FAZLE_API_KEY", "test-api-key")
os.environ.setdefault("FAZLE_DATABASE_URL", "postgresql://test:test@localhost:5432/test")

# auth module is mocked by conftest, but we need require_admin to be a proper callable
from auth import require_admin as _orig_require_admin

# Import the maintenance router (conftest mocks handle psycopg2/database/audit)
from maintenance_routes import router as maintenance_router

# Build a minimal test app with just the maintenance router
app = FastAPI()


async def _mock_admin():
    return {
        "id": "test-admin-id",
        "email": "admin@test.com",
        "name": "Admin",
        "role": "admin",
        "is_active": True,
    }


# Override require_admin dependency
from auth import require_admin
app.dependency_overrides[require_admin] = _mock_admin

# Also patch log_action to be a no-op
from audit import log_action

app.include_router(maintenance_router)

client = TestClient(app, raise_server_exceptions=False)

MAINTENANCE_BASE = "/fazle/admin/maintenance"


# ── Table Discovery Tests ──────────────────────────────────


class TestTableDiscovery:
    """Test table listing and schema endpoints."""

    def test_list_tables_returns_200(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables")
        assert resp.status_code == 200
        data = resp.json()
        assert "tables" in data
        assert len(data["tables"]) > 0

    def test_list_tables_contains_expected_tables(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables")
        table_names = {t["table_name"] for t in resp.json()["tables"]}
        expected = {"fazle_admin_agents", "fazle_contacts", "fazle_users", "fazle_user_rules"}
        assert expected.issubset(table_names), f"Missing: {expected - table_names}"

    def test_list_tables_excludes_blocked(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables")
        table_names = {t["table_name"] for t in resp.json()["tables"]}
        blocked = {"fazle_audit_log", "fazle_conversations", "fazle_messages"}
        assert blocked.isdisjoint(table_names), f"Blocked tables exposed: {blocked & table_names}"

    def test_table_entries_have_required_fields(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables")
        for table in resp.json()["tables"]:
            assert "table_name" in table
            assert "display_name" in table
            assert "group" in table
            assert "access_mode" in table

    def test_get_schema_for_known_table(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_agents/schema")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["table_name"] == "fazle_admin_agents"
        assert schema["access_mode"] == "read_write"
        assert len(schema["columns"]) > 0

    def test_get_schema_includes_column_metadata(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_agents/schema")
        schema = resp.json()
        col_names = [c["name"] for c in schema["columns"]]
        assert "name" in col_names
        assert "status" in col_names

        name_col = next(c for c in schema["columns"] if c["name"] == "name")
        assert name_col["required"] is True
        assert name_col["max_length"] == 100

    def test_get_schema_hides_password_column(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_users/schema")
        assert resp.status_code == 200
        col_names = [c["name"] for c in resp.json()["columns"]]
        assert "hashed_password" not in col_names

    def test_get_schema_shows_permissions(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_agents/schema")
        schema = resp.json()
        assert schema["can_create"] is True
        assert schema["can_update"] is True
        assert schema["can_delete"] is True

    def test_get_schema_singleton_cannot_create(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_persona/schema")
        schema = resp.json()
        assert schema["singleton"] is True
        assert schema["can_create"] is False

    def test_get_schema_read_only_restrictions(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_feedback_learning/schema")
        schema = resp.json()
        assert schema["can_create"] is False
        assert schema["can_update"] is False
        assert schema["can_delete"] is False

    def test_get_schema_for_unknown_table(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/nonexistent_table/schema")
        assert resp.status_code == 404

    def test_get_schema_for_blocked_table(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_audit_log/schema")
        assert resp.status_code == 404


# ── Row Operation Tests (permission checks, no DB) ────────


class TestRowPermissions:
    """Test that row operations enforce access restrictions at the API level."""

    def test_create_on_read_only_table_returns_403(self):
        resp = client.post(
            f"{MAINTENANCE_BASE}/tables/fazle_feedback_learning/rows",
            json={"data": {"original_query": "test"}},
        )
        assert resp.status_code == 403

    def test_update_on_read_only_table_returns_403(self):
        resp = client.put(
            f"{MAINTENANCE_BASE}/tables/fazle_feedback_learning/rows/1",
            json={"data": {"rating": 5}},
        )
        assert resp.status_code == 403

    def test_delete_on_disallowed_table_returns_403(self):
        resp = client.delete(
            f"{MAINTENANCE_BASE}/tables/fazle_admin_persona/rows/1",
        )
        assert resp.status_code == 403

    def test_create_on_singleton_table_returns_403(self):
        resp = client.post(
            f"{MAINTENANCE_BASE}/tables/fazle_admin_persona/rows",
            json={"data": {"name": "test"}},
        )
        assert resp.status_code == 403

    def test_crud_on_blocked_table_returns_403(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_audit_log/rows")
        assert resp.status_code == 403

        resp = client.post(
            f"{MAINTENANCE_BASE}/tables/fazle_audit_log/rows",
            json={"data": {"dummy": "test"}},
        )
        assert resp.status_code == 403

    def test_get_rows_on_unknown_table_returns_404(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/totally_fake/rows")
        assert resp.status_code == 404


# ── Adapter Tests ────────────────────────────────────────────


class TestUserAdapter:
    """Test that the users adapter blocks creation through maintenance."""

    def test_user_create_blocked_via_maintenance(self):
        resp = client.post(
            f"{MAINTENANCE_BASE}/tables/fazle_users/rows",
            json={"data": {"email": "test@test.com", "name": "Test"}},
        )
        assert resp.status_code == 403
        assert "registration endpoint" in resp.json()["detail"].lower()


# ── Response Format Tests ────────────────────────────────────


class TestResponseFormats:
    """Verify response structures match expected shapes."""

    def test_tables_response_shape(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables")
        data = resp.json()
        assert isinstance(data["tables"], list)
        for t in data["tables"]:
            assert isinstance(t["table_name"], str)
            assert isinstance(t["display_name"], str)
            assert t["access_mode"] in ("read_write", "limited_write", "read_only")

    def test_schema_response_shape(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_agents/schema")
        schema = resp.json()
        assert isinstance(schema["columns"], list)
        assert isinstance(schema["can_create"], bool)
        assert isinstance(schema["can_update"], bool)
        assert isinstance(schema["can_delete"], bool)
        assert "primary_key" in schema
        assert "pk_type" in schema

    def test_schema_column_shape(self):
        resp = client.get(f"{MAINTENANCE_BASE}/tables/fazle_admin_agents/schema")
        for col in resp.json()["columns"]:
            assert "name" in col
            assert "display_name" in col
            assert "type" in col
            assert "required" in col
            assert "immutable" in col
