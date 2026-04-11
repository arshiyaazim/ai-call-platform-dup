# ============================================================
# Admin Data Access — Table Metadata Registry
# Declares which tables are exposed, their access modes,
# allowed fields, masked columns, and validation rules.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AccessMode(Enum):
    READ_WRITE = "read_write"
    LIMITED_WRITE = "limited_write"
    READ_ONLY = "read_only"
    BLOCKED = "blocked"


class DeletePolicy(Enum):
    HARD_DELETE = "hard_delete"
    SOFT_DELETE = "soft_delete"          # set is_active = false
    ARCHIVE = "archive"                  # set status = 'archived'
    DISALLOW = "disallow"


@dataclass
class ColumnMeta:
    name: str
    display_name: str
    col_type: str = "text"               # text, integer, boolean, uuid, timestamp, json, enum
    required: bool = False
    max_length: Optional[int] = None
    enum_values: Optional[list[str]] = None
    hidden: bool = False                 # never sent to client
    masked: bool = False                 # sent as "***" to client
    immutable: bool = False              # cannot be updated after creation
    searchable: bool = False
    default: Optional[str] = None


@dataclass
class TableMeta:
    table_name: str
    display_name: str
    group: str                           # admin_config, contacts, user_rules, knowledge, users, social
    access_mode: AccessMode
    primary_key: str = "id"
    pk_type: str = "uuid"               # uuid, serial, integer
    delete_policy: DeletePolicy = DeletePolicy.HARD_DELETE
    columns: list[ColumnMeta] = field(default_factory=list)
    singleton: bool = False             # single-row config table (e.g. persona)
    audit_event_prefix: str = ""        # e.g. "maintenance_agents" → "maintenance_agents_create"
    adapter: Optional[str] = None       # name of a table-specific adapter if generic CRUD is insufficient
    order_by: str = "created_at DESC"
    description: str = ""


# ── Column helper ───────────────────────────────────────────

def _col(name, display, col_type="text", **kw) -> ColumnMeta:
    return ColumnMeta(name=name, display_name=display, col_type=col_type, **kw)


def _ts(name="created_at", display="Created") -> ColumnMeta:
    return _col(name, display, "timestamp", immutable=True)


def _id(pk_type="uuid") -> ColumnMeta:
    return _col("id", "ID", pk_type, immutable=True)


# ── Registry ────────────────────────────────────────────────

TABLE_REGISTRY: dict[str, TableMeta] = {}


def _register(meta: TableMeta):
    TABLE_REGISTRY[meta.table_name] = meta


# ─────────────────────────────────────────────────────────────
# GROUP: admin_config
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_admin_agents",
    display_name="AI Agents",
    group="admin_config",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_agents",
    order_by="priority, created_at",
    description="Configured AI agent models",
    columns=[
        _id(),
        _col("name", "Name", required=True, max_length=100, searchable=True),
        _col("model", "Model", required=True, max_length=100),
        _col("priority", "Priority", "integer", required=True),
        _col("description", "Description", max_length=1000, searchable=True),
        _col("status", "Status", "enum", enum_values=["active", "inactive"], default="active"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))

_register(TableMeta(
    table_name="fazle_admin_plugins",
    display_name="Plugins",
    group="admin_config",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_plugins",
    order_by="created_at",
    description="Installed plugin configurations",
    columns=[
        _id(),
        _col("name", "Name", required=True, max_length=100, searchable=True),
        _col("description", "Description", max_length=1000, searchable=True),
        _col("version", "Version", max_length=30, default="1.0.0"),
        _col("status", "Status", "enum", enum_values=["enabled", "disabled"], default="enabled"),
        _col("manifest", "Manifest", "json"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))

_register(TableMeta(
    table_name="fazle_admin_tasks",
    display_name="Admin Tasks",
    group="admin_config",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_tasks",
    order_by="created_at DESC",
    description="Managed scheduled tasks and reminders",
    columns=[
        _id(),
        _col("title", "Title", required=True, max_length=200, searchable=True),
        _col("task_type", "Type", "enum", enum_values=["reminder", "scheduled", "recurring", "one-time"], default="reminder"),
        _col("schedule", "Schedule", max_length=100),
        _col("scheduled_at", "Scheduled At", "timestamp"),
        _col("description", "Description", max_length=2000, searchable=True),
        _col("status", "Status", "enum", enum_values=["pending", "running", "completed", "failed", "cancelled"], default="pending"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))

_register(TableMeta(
    table_name="fazle_admin_persona",
    display_name="Persona Config",
    group="admin_config",
    access_mode=AccessMode.LIMITED_WRITE,
    primary_key="id",
    pk_type="integer",
    delete_policy=DeletePolicy.DISALLOW,
    singleton=True,
    audit_event_prefix="maintenance_persona",
    description="AI persona configuration (single row)",
    columns=[
        _col("id", "ID", "integer", immutable=True),
        _col("name", "Name", max_length=100),
        _col("tone", "Tone"),
        _col("language", "Language", max_length=50),
        _col("speaking_style", "Speaking Style"),
        _col("knowledge_notes", "Knowledge Notes"),
        _ts("updated_at", "Updated"),
    ],
))


# ─────────────────────────────────────────────────────────────
# GROUP: contacts
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_contacts",
    display_name="Contacts",
    group="contacts",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_contacts",
    order_by="last_updated DESC",
    description="Known contacts across platforms",
    columns=[
        _id(),
        _col("phone", "Phone", required=True, max_length=50, searchable=True),
        _col("name", "Name", max_length=200, searchable=True),
        _col("relation", "Relation", max_length=100, default="unknown"),
        _col("notes", "Notes"),
        _col("company", "Company", max_length=300, searchable=True),
        _col("personality_hint", "Personality Hint", max_length=200),
        _col("platform", "Platform", "enum", enum_values=["whatsapp", "facebook", "manual"], default="whatsapp"),
        _col("interaction_count", "Interactions", "integer"),
        _col("interest_level", "Interest", "enum", enum_values=["unknown", "low", "medium", "high"], default="unknown"),
        _col("last_seen", "Last Seen", "timestamp"),
        _col("last_updated", "Last Updated", "timestamp"),
        _ts("created_at", "Created"),
    ],
))

_register(TableMeta(
    table_name="fazle_social_contacts",
    display_name="Social Contacts",
    group="contacts",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_social_contacts",
    order_by="created_at DESC",
    description="Social platform contact profiles",
    columns=[
        _id(),
        _col("name", "Name", required=True, max_length=200, searchable=True),
        _col("platform", "Platform", "enum", enum_values=["whatsapp", "facebook"], required=True),
        _col("identifier", "Identifier", required=True, max_length=200, searchable=True),
        _col("phone_number", "Phone", max_length=50),
        _col("profile_link", "Profile Link"),
        _col("metadata", "Metadata", "json"),
        _ts("created_at", "Created"),
    ],
))

_register(TableMeta(
    table_name="fazle_leads",
    display_name="Leads",
    group="contacts",
    access_mode=AccessMode.READ_WRITE,
    primary_key="id",
    pk_type="serial",
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_leads",
    order_by="created_at DESC",
    description="Captured lead inquiries",
    columns=[
        _col("id", "ID", "integer", immutable=True),
        _col("name", "Name", searchable=True),
        _col("phone", "Phone", searchable=True),
        _col("message", "Message", searchable=True),
        _col("intent", "Intent"),
        _col("source", "Source"),
        _col("status", "Status", "enum", enum_values=["new", "contacted", "qualified", "lost"], default="new"),
        _ts("created_at", "Created"),
    ],
))


# ─────────────────────────────────────────────────────────────
# GROUP: user_rules
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_user_rules",
    display_name="User Rules",
    group="user_rules",
    access_mode=AccessMode.LIMITED_WRITE,
    delete_policy=DeletePolicy.SOFT_DELETE,
    audit_event_prefix="maintenance_user_rules",
    adapter="user_rules",
    order_by="created_at DESC",
    description="Per-contact behavior rules (tone, blocks, auto-reply, etc.)",
    columns=[
        _id(),
        _col("contact_identifier", "Contact", required=True, searchable=True),
        _col("platform", "Platform", "enum", enum_values=["whatsapp", "facebook", "web"], required=True, default="whatsapp"),
        _col("rule_type", "Rule Type", "enum", enum_values=["tone", "block", "auto_reply", "greeting", "escalate", "restrict_topic"], required=True),
        _col("rule_value", "Rule Value", required=True),
        _col("priority", "Priority", "integer", default="1"),
        _col("is_active", "Active", "boolean", default="true"),
        _col("created_by", "Created By", immutable=True),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
        _col("expires_at", "Expires At", "timestamp"),
    ],
))


# ─────────────────────────────────────────────────────────────
# GROUP: knowledge
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_knowledge_governance",
    display_name="Knowledge Facts",
    group="knowledge",
    access_mode=AccessMode.LIMITED_WRITE,
    delete_policy=DeletePolicy.ARCHIVE,
    audit_event_prefix="maintenance_governance",
    adapter="knowledge_governance",
    order_by="updated_at DESC",
    description="Governed knowledge facts with versioning",
    columns=[
        _id(),
        _col("category", "Category", required=True, searchable=True),
        _col("fact_key", "Fact Key", required=True, searchable=True),
        _col("fact_value", "Fact Value", required=True, searchable=True),
        _col("language", "Language", max_length=10, default="bn"),
        _col("version", "Version", "integer", immutable=True),
        _col("status", "Status", "enum", enum_values=["active", "deprecated", "pending_review"], default="active"),
        _col("created_by", "Created By", immutable=True, default="system"),
        _col("source", "Source", default="manual"),
        _col("expires_at", "Expires At", "timestamp"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
        _col("deprecated_at", "Deprecated At", "timestamp"),
        _col("deprecation_reason", "Deprecation Reason"),
    ],
))

_register(TableMeta(
    table_name="fazle_knowledge_phrasing",
    display_name="Phrasing Rules",
    group="knowledge",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_phrasing",
    order_by="created_at DESC",
    description="Preferred and prohibited phrasing for topics",
    columns=[
        _id(),
        _col("topic", "Topic", required=True, searchable=True),
        _col("preferred_phrasing", "Preferred Phrasing", required=True, searchable=True),
        _col("prohibited_phrasing", "Prohibited Phrasing"),
        _col("language", "Language", max_length=10, default="bn"),
        _col("status", "Status", "enum", enum_values=["active", "inactive"], default="active"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))

_register(TableMeta(
    table_name="fazle_knowledge_base",
    display_name="Knowledge Base",
    group="knowledge",
    access_mode=AccessMode.READ_WRITE,
    primary_key="id",
    pk_type="serial",
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_knowledge_base",
    order_by="created_at DESC",
    description="Indexed knowledge entries",
    columns=[
        _col("id", "ID", "integer", immutable=True),
        _col("category", "Category", required=True, searchable=True),
        _col("subcategory", "Subcategory", searchable=True),
        _col("key", "Key", required=True, searchable=True),
        _col("value", "Value", required=True, searchable=True),
        _col("language", "Language", default="bn-en"),
        _col("confidence", "Confidence", "integer"),
        _col("tags", "Tags", "json"),
        _ts("created_at", "Created"),
    ],
))

_register(TableMeta(
    table_name="fazle_feedback_learning",
    display_name="Feedback Learning",
    group="knowledge",
    access_mode=AccessMode.READ_ONLY,
    primary_key="id",
    pk_type="serial",
    delete_policy=DeletePolicy.DISALLOW,
    audit_event_prefix="maintenance_feedback",
    order_by="created_at DESC",
    description="AI feedback corrections from users",
    columns=[
        _col("id", "ID", "integer", immutable=True),
        _col("original_query", "Original Query", searchable=True),
        _col("ai_reply", "AI Reply"),
        _col("corrected_reply", "Corrected Reply"),
        _col("rating", "Rating", "integer"),
        _ts("created_at", "Created"),
    ],
))


# ─────────────────────────────────────────────────────────────
# GROUP: users
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_users",
    display_name="Users",
    group="users",
    access_mode=AccessMode.LIMITED_WRITE,
    delete_policy=DeletePolicy.SOFT_DELETE,
    audit_event_prefix="maintenance_users",
    adapter="users",
    order_by="created_at",
    description="System users and family members",
    columns=[
        _id(),
        _col("email", "Email", required=True, max_length=255, searchable=True, immutable=True),
        _col("hashed_password", "Password", hidden=True),
        _col("name", "Name", required=True, max_length=100, searchable=True),
        _col("relationship_to_azim", "Relationship", "enum",
             enum_values=["self", "wife", "daughter", "son", "parent", "sibling"], default="self"),
        _col("role", "Role", "enum", enum_values=["admin", "member"], default="member"),
        _col("is_active", "Active", "boolean", default="true"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))


# ─────────────────────────────────────────────────────────────
# GROUP: social
# ─────────────────────────────────────────────────────────────

_register(TableMeta(
    table_name="fazle_social_scheduled",
    display_name="Scheduled Messages",
    group="social",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.HARD_DELETE,
    audit_event_prefix="maintenance_scheduled",
    order_by="scheduled_at DESC",
    description="Scheduled social media actions",
    columns=[
        _id(),
        _col("platform", "Platform", "enum", enum_values=["whatsapp", "facebook"], required=True),
        _col("action_type", "Action Type", required=True, max_length=50),
        _col("payload", "Payload", "json", required=True),
        _col("scheduled_at", "Scheduled At", "timestamp", required=True),
        _col("status", "Status", "enum", enum_values=["pending", "sent", "failed", "cancelled"], default="pending"),
        _ts("created_at", "Created"),
    ],
))

_register(TableMeta(
    table_name="fazle_social_campaigns",
    display_name="Campaigns",
    group="social",
    access_mode=AccessMode.READ_WRITE,
    delete_policy=DeletePolicy.ARCHIVE,
    audit_event_prefix="maintenance_campaigns",
    order_by="created_at DESC",
    description="Social media campaign configurations",
    columns=[
        _id(),
        _col("name", "Name", required=True, max_length=200, searchable=True),
        _col("platform", "Platform", "enum", enum_values=["whatsapp", "facebook"], required=True),
        _col("campaign_type", "Type", required=True, max_length=50),
        _col("config", "Config", "json", required=True),
        _col("status", "Status", "enum", enum_values=["draft", "active", "paused", "completed"], default="draft"),
        _ts("created_at", "Created"),
        _ts("updated_at", "Updated"),
    ],
))


# ─────────────────────────────────────────────────────────────
# BLOCKED TABLES — explicitly listed so console knows not to expose them
# ─────────────────────────────────────────────────────────────

BLOCKED_TABLES = frozenset([
    "fazle_audit_log",
    "fazle_password_reset_tokens",
    "fazle_social_integrations",       # contains app_secret, access_token
    "fazle_conversations",
    "fazle_messages",
    "fazle_social_messages",
    "fazle_owner_audio_profiles",
    "fazle_conversation_summaries",
    "fazle_multimodal_learning",
    "fazle_chat_replies",
    "fazle_knowledge_users",
    "fazle_access_rules",
    "fazle_knowledge_corrections",
    "fazle_knowledge_conflicts",
    "fazle_user_rules_audit",
    "fazle_social_posts",
    "fazle_owner_feedback",
    "fazle_owner_knowledge",
    "fazle_tasks",
])


# ── Public API ──────────────────────────────────────────────

def get_table_meta(table_name: str) -> TableMeta | None:
    """Return metadata for a registered table, or None."""
    return TABLE_REGISTRY.get(table_name)


def list_exposed_tables() -> list[dict]:
    """Return a list of table metadata dicts for the frontend (non-blocked only)."""
    result = []
    for meta in TABLE_REGISTRY.values():
        if meta.access_mode == AccessMode.BLOCKED:
            continue
        result.append({
            "table_name": meta.table_name,
            "display_name": meta.display_name,
            "group": meta.group,
            "access_mode": meta.access_mode.value,
            "singleton": meta.singleton,
            "description": meta.description,
        })
    return result


def get_table_schema(table_name: str) -> dict | None:
    """Return full schema metadata for a table, suitable for frontend form generation."""
    meta = TABLE_REGISTRY.get(table_name)
    if not meta or meta.access_mode == AccessMode.BLOCKED:
        return None

    columns = []
    for col in meta.columns:
        if col.hidden:
            continue
        columns.append({
            "name": col.name,
            "display_name": col.display_name,
            "type": col.col_type,
            "required": col.required,
            "max_length": col.max_length,
            "enum_values": col.enum_values,
            "masked": col.masked,
            "immutable": col.immutable,
            "searchable": col.searchable,
            "default": col.default,
        })

    can_create = meta.access_mode in (AccessMode.READ_WRITE, AccessMode.LIMITED_WRITE) and not meta.singleton
    can_update = meta.access_mode in (AccessMode.READ_WRITE, AccessMode.LIMITED_WRITE)
    can_delete = meta.delete_policy != DeletePolicy.DISALLOW and meta.access_mode != AccessMode.READ_ONLY

    return {
        "table_name": meta.table_name,
        "display_name": meta.display_name,
        "group": meta.group,
        "access_mode": meta.access_mode.value,
        "primary_key": meta.primary_key,
        "pk_type": meta.pk_type,
        "singleton": meta.singleton,
        "delete_policy": meta.delete_policy.value,
        "description": meta.description,
        "columns": columns,
        "can_create": can_create,
        "can_update": can_update,
        "can_delete": can_delete,
    }
