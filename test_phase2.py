# ============================================================
# Phase 2 — Local Structural Tests
# Tests all Phase 2 components without requiring Docker/DB
# ============================================================
import sys
import os

# Add fazle-system to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fazle-system"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fazle-system", "brain"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fazle-system", "api"))

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}")


# ══════════════════════════════════════════════════════════════
# Phase 2A: Owner Query APIs
# ══════════════════════════════════════════════════════════════
print("\n═══ Phase 2A: Owner Query APIs ═══")

try:
    from owner_query_routes import router as oq_router
    routes = {r.path: r.methods for r in oq_router.routes if hasattr(r, "path")}
    test("owner_query_routes imported", True)
    test("/owner/messages endpoint exists", "/messages" in str(routes) or any("/messages" in r for r in routes))
    test("/owner/senders endpoint exists", any("/senders" in r for r in routes))
    test("/owner/leads/stats endpoint exists", any("/leads/stats" in r for r in routes))
    test("/owner/contacts endpoint exists", any("/contacts" in r for r in routes))
    test("/owner/daily-report endpoint exists", any("/daily-report" in r for r in routes))
    test("At least 5 owner query endpoints", len(routes) >= 5)
except Exception as e:
    test(f"owner_query_routes import: {e}", False)

# ══════════════════════════════════════════════════════════════
# Phase 2B: Per-User Instruction Rules
# ══════════════════════════════════════════════════════════════
print("\n═══ Phase 2B: Per-User Rules ═══")

# DB Migration
migration_path = os.path.join(
    os.path.dirname(__file__), "fazle-system", "tasks", "migrations", "007_user_rules.sql"
)
test("007_user_rules.sql exists", os.path.exists(migration_path))
if os.path.exists(migration_path):
    content = open(migration_path, encoding="utf-8").read()
    test("fazle_user_rules table in migration", "fazle_user_rules" in content)
    test("fazle_user_rules_audit table in migration", "fazle_user_rules_audit" in content)
    test("rule_type column exists", "rule_type" in content)
    test("expires_at column exists", "expires_at" in content)

# Brain-side engine
try:
    from owner_control.user_rules import UserRulesEngine, RULE_TYPES, UserRule
    test("UserRulesEngine imported", True)
    test("6 rule types defined", len(RULE_TYPES) == 6)
    test("tone rule type exists", "tone" in RULE_TYPES)
    test("block rule type exists", "block" in RULE_TYPES)
    test("auto_reply rule type exists", "auto_reply" in RULE_TYPES)
    test("escalate rule type exists", "escalate" in RULE_TYPES)
    test("restrict_topic rule type exists", "restrict_topic" in RULE_TYPES)
    test("greeting rule type exists", "greeting" in RULE_TYPES)

    # Test build_rules_prompt with mock
    engine = UserRulesEngine.__new__(UserRulesEngine)
    engine._dsn = ""
    engine._redis_url = ""
    engine._redis = None
    # Can't call get_rules without DB, but verify method exists
    test("build_rules_prompt method exists", hasattr(engine, "build_rules_prompt"))
    test("should_block method exists", hasattr(engine, "should_block"))
    test("get_auto_reply method exists", hasattr(engine, "get_auto_reply"))
    test("should_escalate method exists", hasattr(engine, "should_escalate"))
    test("set_rule method exists", hasattr(engine, "set_rule"))
    test("deactivate_rule method exists", hasattr(engine, "deactivate_rule"))
except Exception as e:
    test(f"UserRulesEngine import: {e}", False)

# API routes
try:
    from user_rules_routes import router as ur_router, VALID_RULE_TYPES
    routes = {r.path: r.methods for r in ur_router.routes if hasattr(r, "path")}
    test("user_rules_routes imported", True)
    test("GET /user-rules/rules endpoint", any("/rules" in r for r in routes))
    test("POST /user-rules/rules endpoint", any("/rules" in r and "POST" in str(routes.get(r, {})) for r in routes))
    test("DELETE deactivate endpoint", any("DELETE" in str(m) for m in routes.values()))
    test("GET /user-rules/audit endpoint", any("/audit" in r for r in routes))
    test("6 valid rule types", len(VALID_RULE_TYPES) == 6)
except Exception as e:
    test(f"user_rules_routes import: {e}", False)

# ══════════════════════════════════════════════════════════════
# Phase 2C: Knowledge Lifecycle
# ══════════════════════════════════════════════════════════════
print("\n═══ Phase 2C: Knowledge Lifecycle ═══")

migration_path_2c = os.path.join(
    os.path.dirname(__file__), "fazle-system", "tasks", "migrations", "008_knowledge_lifecycle.sql"
)
test("008_knowledge_lifecycle.sql exists", os.path.exists(migration_path_2c))
if os.path.exists(migration_path_2c):
    content = open(migration_path_2c, encoding="utf-8").read()
    test("expires_at column added to governance", "expires_at" in content)
    test("fazle_knowledge_conflicts table", "fazle_knowledge_conflicts" in content)
    test("conflict resolution columns", "resolution" in content and "resolved_by" in content)

# Governance routes now have lifecycle endpoints
try:
    from governance_routes import router as gov_router
    route_paths = [r.path for r in gov_router.routes if hasattr(r, "path")]
    test("expiry endpoint exists", any("expiry" in p for p in route_paths))
    test("expiring facts endpoint exists", any("expiring" in p for p in route_paths))
    test("conflicts list endpoint exists", any("conflicts" in p for p in route_paths))
    test("conflict resolve endpoint exists", any("resolve" in p for p in route_paths))
except Exception as e:
    test(f"governance lifecycle routes: {e}", False)

# ══════════════════════════════════════════════════════════════
# Phase 2D: Governance Prompt Injection
# ══════════════════════════════════════════════════════════════
print("\n═══ Phase 2D: Governance Prompt Injection ═══")

try:
    import importlib
    persona_spec = importlib.util.find_spec("persona_engine")
    test("persona_engine module found", persona_spec is not None)
except Exception:
    pass

# Read persona_engine.py and check for injection code
persona_path = os.path.join(
    os.path.dirname(__file__), "fazle-system", "brain", "persona_engine.py"
)
if os.path.exists(persona_path):
    content = open(persona_path, encoding="utf-8").read()
    test("_get_governance_prompt function exists", "_get_governance_prompt" in content)
    test("_get_user_rules_prompt function exists", "_get_user_rules_prompt" in content)
    test("governance prompt injected in build_system_prompt", "gov_prompt = _get_governance_prompt()" in content)
    test("user rules injected in build_system_prompt", "rules_prompt = _get_user_rules_prompt" in content)
    test("GOVERNANCE_CACHE_KEY defined", "_GOVERNANCE_CACHE_KEY" in content)
    test("DATABASE_URL imported for governance", "DATABASE_URL" in content)
else:
    test("persona_engine.py exists", False)

# ══════════════════════════════════════════════════════════════
# Phase 2: Control Plane Status
# ══════════════════════════════════════════════════════════════
print("\n═══ Control Plane Status ═══")

brain_main_path = os.path.join(
    os.path.dirname(__file__), "fazle-system", "brain", "main.py"
)
if os.path.exists(brain_main_path):
    content = open(brain_main_path, encoding="utf-8").read()
    test("Phase 2 in control-plane status", '"phase": 2' in content or "'phase': 2" in content)
    test("2A feature flag", "2A_owner_query_apis" in content)
    test("2B feature flag", "2B_user_rules" in content)
    test("2C feature flag", "2C_knowledge_lifecycle" in content)
    test("2D feature flag", "2D_governance_injection" in content)

# ══════════════════════════════════════════════════════════════
# API Gateway Wiring
# ══════════════════════════════════════════════════════════════
print("\n═══ API Gateway Wiring ═══")

api_main_path = os.path.join(
    os.path.dirname(__file__), "fazle-system", "api", "main.py"
)
if os.path.exists(api_main_path):
    content = open(api_main_path, encoding="utf-8").read()
    test("owner_query_routes imported", "from owner_query_routes import" in content)
    test("user_rules_routes imported", "from user_rules_routes import" in content)
    test("owner_query_router included", "owner_query_router" in content)
    test("user_rules_router included", "user_rules_router" in content)
    test("ensure_user_rules_tables in startup", "ensure_user_rules_tables()" in content)

# Capability matrix updated
cap_path = os.path.join(
    os.path.dirname(__file__), "fazle-system", "brain", "owner_control", "capability_matrix.py"
)
if os.path.exists(cap_path):
    content = open(cap_path, encoding="utf-8").read()
    test("knowledge_governance now IMPLEMENTED", 'CapStatus.IMPLEMENTED' in content and 'knowledge_governance' in content)

# ══════════════════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"Phase 2 Tests: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'='*50}")
sys.exit(1 if failed > 0 else 0)
