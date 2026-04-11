# ============================================================
# Tests — Maintenance Console Backend
# Verifies metadata enforcement, permissions, and CRUD behavior
# ============================================================
import pytest
from admin_data_access.metadata import (
    TABLE_REGISTRY,
    BLOCKED_TABLES,
    AccessMode,
    DeletePolicy,
    get_table_meta,
    get_table_schema,
    list_exposed_tables,
)
from admin_data_access.permissions import (
    check_table_exposed,
    check_access,
    check_column_allowed,
)


# ── Metadata Registry Tests ─────────────────────────────────


class TestTableRegistry:
    """Verify the metadata registry is correctly configured."""

    def test_all_registered_tables_have_columns(self):
        for name, meta in TABLE_REGISTRY.items():
            assert len(meta.columns) > 0, f"{name} has no columns"

    def test_all_registered_tables_have_primary_key(self):
        for name, meta in TABLE_REGISTRY.items():
            pk_col = None
            for c in meta.columns:
                if c.name == meta.primary_key:
                    pk_col = c
                    break
            assert pk_col is not None, f"{name} has no column matching primary key '{meta.primary_key}'"

    def test_all_registered_tables_have_audit_prefix(self):
        for name, meta in TABLE_REGISTRY.items():
            assert meta.audit_event_prefix, f"{name} is missing audit_event_prefix"

    def test_blocked_tables_not_in_exposed(self):
        exposed = list_exposed_tables()
        exposed_names = {t["table_name"] for t in exposed}
        for blocked in BLOCKED_TABLES:
            assert blocked not in exposed_names, f"Blocked table '{blocked}' appears in exposed list"

    def test_expected_table_groups(self):
        groups = {meta.group for meta in TABLE_REGISTRY.values()}
        expected = {"admin_config", "contacts", "user_rules", "knowledge", "users", "social"}
        assert expected.issubset(groups), f"Missing groups: {expected - groups}"

    def test_singleton_tables_disallow_create(self):
        for name, meta in TABLE_REGISTRY.items():
            if meta.singleton:
                schema = get_table_schema(name)
                assert not schema["can_create"], f"Singleton table '{name}' should not allow creation"

    def test_read_only_tables_disallow_write(self):
        for name, meta in TABLE_REGISTRY.items():
            if meta.access_mode == AccessMode.READ_ONLY:
                schema = get_table_schema(name)
                assert not schema["can_create"], f"Read-only '{name}' should not allow creation"
                assert not schema["can_update"], f"Read-only '{name}' should not allow update"

    def test_get_table_meta_returns_none_for_unknown(self):
        assert get_table_meta("nonexistent_table") is None

    def test_get_table_schema_returns_none_for_blocked(self):
        for blocked in list(BLOCKED_TABLES)[:3]:
            assert get_table_schema(blocked) is None


# ── Permission Tests ────────────────────────────────────────


class TestPermissions:
    """Test access mode enforcement."""

    def test_blocked_table_raises_403(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_table_exposed("fazle_audit_log")
        assert exc.value.status_code == 403

    def test_unknown_table_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_table_exposed("totally_fake_table")
        assert exc.value.status_code == 404

    def test_read_only_table_blocks_create(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_access("fazle_feedback_learning", "create")
        assert exc.value.status_code == 403

    def test_read_only_table_allows_read(self):
        meta = check_access("fazle_feedback_learning", "read")
        assert meta.table_name == "fazle_feedback_learning"

    def test_singleton_blocks_create(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_access("fazle_admin_persona", "create")
        assert exc.value.status_code == 403

    def test_disallow_delete_raises_403(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            check_access("fazle_admin_persona", "delete")
        assert exc.value.status_code == 403

    def test_read_write_allows_all_operations(self):
        for op in ("read", "create", "update", "delete"):
            meta = check_access("fazle_admin_agents", op)
            assert meta.table_name == "fazle_admin_agents"


# ── Column-Level Permission Tests ───────────────────────────


class TestColumnPermissions:
    """Test column-level access enforcement."""

    def test_hidden_column_blocks_write(self):
        from fastapi import HTTPException
        meta = get_table_meta("fazle_users")
        with pytest.raises(HTTPException) as exc:
            check_column_allowed(meta, "hashed_password", "create")
        assert exc.value.status_code == 403

    def test_immutable_column_blocks_update(self):
        from fastapi import HTTPException
        meta = get_table_meta("fazle_users")
        with pytest.raises(HTTPException) as exc:
            check_column_allowed(meta, "email", "update")
        assert exc.value.status_code == 403

    def test_unknown_column_raises_400(self):
        from fastapi import HTTPException
        meta = get_table_meta("fazle_admin_agents")
        with pytest.raises(HTTPException) as exc:
            check_column_allowed(meta, "fake_column", "create")
        assert exc.value.status_code == 400

    def test_valid_column_passes(self):
        meta = get_table_meta("fazle_admin_agents")
        # Should not raise
        check_column_allowed(meta, "name", "create")
        check_column_allowed(meta, "name", "update")


# ── Schema Output Tests ─────────────────────────────────────


class TestSchemaOutput:
    """Test that schema output correctly hides/masks columns."""

    def test_hidden_columns_excluded_from_schema(self):
        schema = get_table_schema("fazle_users")
        col_names = [c["name"] for c in schema["columns"]]
        assert "hashed_password" not in col_names

    def test_schema_includes_access_mode(self):
        schema = get_table_schema("fazle_admin_agents")
        assert schema["access_mode"] == "read_write"

    def test_schema_includes_column_metadata(self):
        schema = get_table_schema("fazle_admin_agents")
        name_col = next(c for c in schema["columns"] if c["name"] == "name")
        assert name_col["required"] is True
        assert name_col["max_length"] == 100
        assert name_col["searchable"] is True

    def test_schema_enum_values_included(self):
        schema = get_table_schema("fazle_admin_agents")
        status_col = next(c for c in schema["columns"] if c["name"] == "status")
        assert status_col["enum_values"] == ["active", "inactive"]
