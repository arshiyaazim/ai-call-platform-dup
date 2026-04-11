# ============================================================
# Admin Data Access — Centralized maintenance layer
# Metadata-driven table management with access control
# ============================================================
from admin_data_access.core import get_conn, get_dict_cursor
from admin_data_access.metadata import TABLE_REGISTRY, get_table_meta, list_exposed_tables
from admin_data_access.repository import MaintenanceRepository
from admin_data_access.permissions import AccessMode, check_access, check_column_allowed

__all__ = [
    "get_conn",
    "get_dict_cursor",
    "TABLE_REGISTRY",
    "get_table_meta",
    "list_exposed_tables",
    "MaintenanceRepository",
    "AccessMode",
    "check_access",
    "check_column_allowed",
]
