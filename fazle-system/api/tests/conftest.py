# ============================================================
# Test Configuration — Mock external dependencies for unit tests
# ============================================================
import sys
import os
from unittest.mock import MagicMock

# Add the API directory to sys.path so imports resolve
api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

# Mock psycopg2 and its submodules (not installed locally; only on VPS)
for mod_name in [
    "psycopg2", "psycopg2.extras", "psycopg2.pool",
    "psycopg2.extensions",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Mock pydantic_settings if not installed
if "pydantic_settings" not in sys.modules:
    mock_ps = MagicMock()
    # BaseSettings must be a class for class inheritance
    mock_ps.BaseSettings = type("BaseSettings", (), {"Config": type("Config", (), {})})
    sys.modules["pydantic_settings"] = mock_ps

# Mock the database module before admin_data_access is imported.
# This avoids needing a live PostgreSQL connection for pure unit tests.
if "database" not in sys.modules:
    mock_database = MagicMock()
    mock_database._pool = MagicMock()
    sys.modules["database"] = mock_database

# Mock the audit module (used by maintenance_routes but not needed in unit tests)
if "audit" not in sys.modules:
    mock_audit = MagicMock()
    mock_audit.log_action = MagicMock()
    sys.modules["audit"] = mock_audit

# Mock the auth module (used by maintenance_routes)
if "auth" not in sys.modules:
    mock_auth = MagicMock()
    mock_auth.require_admin = MagicMock()
    sys.modules["auth"] = mock_auth
