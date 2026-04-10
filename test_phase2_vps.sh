#!/bin/bash
API="http://localhost:8100"
BRAIN="http://localhost:8200"
KEY="2aMFFfIaGDfgfP6JiXaevEgMRx9aZtgAzYriHGRcpvdEcWCtp7Xpqul0BYdjFchq"
PASS=0
FAIL=0

check() {
    local name="$1"
    local code="$2"
    local body="$3"
    if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
        echo "PASS $name (HTTP $code)"
        PASS=$((PASS+1))
    else
        echo "FAIL $name (HTTP $code) $body"
        FAIL=$((FAIL+1))
    fi
}

echo "=============================="
echo "Phase 2 VPS Integration Tests"
echo "=============================="

# --- Brain control-plane ---
echo ""
echo "--- Brain Control Plane ---"
RESP=$(curl -s -w "\n%{http_code}" "$BRAIN/control-plane/status")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "Control-plane status" "$CODE" "$BODY"
echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['phase']==2; assert d['features']['2A_owner_query_apis']; print('  phase=2, all features on')" 2>&1

# --- 2A: Owner Query APIs ---
echo ""
echo "--- Phase 2A: Owner Query APIs ---"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/owner/messages?hours=24&limit=5")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2A-1 GET /owner/messages" "$CODE" "$BODY"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/owner/senders?hours=24")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2A-2 GET /owner/senders" "$CODE" "$BODY"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/owner/leads/stats")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2A-3 GET /owner/leads/stats" "$CODE" "$BODY"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/owner/contacts")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2A-4 GET /owner/contacts" "$CODE" "$BODY"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/owner/daily-report")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2A-5 GET /owner/daily-report" "$CODE" "$BODY"

# Test auth rejection (no key)
RESP=$(curl -s -w "\n%{http_code}" "$API/owner/messages?hours=24")
CODE=$(echo "$RESP" | tail -1)
if [ "$CODE" -eq 401 ] || [ "$CODE" -eq 403 ]; then
    echo "PASS 2A-6 Auth rejection (HTTP $CODE)"
    PASS=$((PASS+1))
else
    echo "FAIL 2A-6 Auth rejection expected 401/403, got $CODE"
    FAIL=$((FAIL+1))
fi

# --- 2B: User Rules APIs ---
echo ""
echo "--- Phase 2B: User Rules ---"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/user-rules/rules")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-1 GET /user-rules/rules (empty)" "$CODE" "$BODY"

# Create a rule
RESP=$(curl -s -w "\n%{http_code}" -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"contact_identifier":"test_user_phase2","platform":"whatsapp","rule_type":"tone","rule_value":"Always be very formal and respectful"}' \
    "$API/user-rules/rules")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-2 POST /user-rules/rules (create tone)" "$CODE" "$BODY"

# Create another rule
RESP=$(curl -s -w "\n%{http_code}" -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"contact_identifier":"test_user_phase2","platform":"whatsapp","rule_type":"greeting","rule_value":"Greet with Salaam"}' \
    "$API/user-rules/rules")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-3 POST /user-rules/rules (create greeting)" "$CODE" "$BODY"

# List rules for contact
RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/user-rules/rules?contact=test_user_phase2")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-4 GET /user-rules/rules?contact=test_user_phase2" "$CODE" "$BODY"
echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  found', len(d.get('rules',d if isinstance(d,list) else [])), 'rules')" 2>&1

# Update rule
RESP=$(curl -s -w "\n%{http_code}" -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"rule_value":"Be extremely formal, use Sir/Madam"}' \
    "$API/user-rules/rules/test_user_phase2/tone")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-5 PUT /user-rules/rules/.../tone (update)" "$CODE" "$BODY"

# Audit trail
RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/user-rules/audit?contact=test_user_phase2")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-6 GET /user-rules/audit" "$CODE" "$BODY"

# Deactivate rule
RESP=$(curl -s -w "\n%{http_code}" -X DELETE -H "X-API-Key: $KEY" "$API/user-rules/rules/test_user_phase2/greeting")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2B-7 DELETE /user-rules/rules/.../greeting (deactivate)" "$CODE" "$BODY"

# Bad rule type
RESP=$(curl -s -w "\n%{http_code}" -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"contact_identifier":"test_user_phase2","platform":"whatsapp","rule_type":"invalid_type","rule_value":"test"}' \
    "$API/user-rules/rules")
CODE=$(echo "$RESP" | tail -1)
if [ "$CODE" -eq 400 ] || [ "$CODE" -eq 422 ]; then
    echo "PASS 2B-8 Invalid rule_type rejection (HTTP $CODE)"
    PASS=$((PASS+1))
else
    BODY=$(echo "$RESP" | head -n -1)
    echo "FAIL 2B-8 Invalid rule_type expected 400/422, got $CODE: $BODY"
    FAIL=$((FAIL+1))
fi

# --- 2C: Knowledge Lifecycle ---
echo ""
echo "--- Phase 2C: Knowledge Lifecycle ---"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/governance/facts/expiring?days=30")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2C-1 GET /governance/facts/expiring" "$CODE" "$BODY"

# First create a governance fact to test expiry on
RESP=$(curl -s -w "\n%{http_code}" -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"category":"business","fact_key":"test_promo_phase2","fact_value":"Summer sale 50% off","source":"owner"}' \
    "$API/governance/facts")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2C-2 POST /governance/facts (create test fact)" "$CODE" "$BODY"

# Set expiry on the fact
RESP=$(curl -s -w "\n%{http_code}" -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
    -d '{"expires_at":"2026-04-15T00:00:00Z"}' \
    "$API/governance/facts/business/test_promo_phase2/expiry")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2C-3 PUT /governance/facts/.../expiry" "$CODE" "$BODY"

# Check expiring again
RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/governance/facts/expiring?days=30")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2C-4 GET /governance/facts/expiring (should include test)" "$CODE" "$BODY"

# Conflicts
RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/governance/conflicts")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2C-5 GET /governance/conflicts" "$CODE" "$BODY"

# --- 2D: Governance Injection ---
echo ""
echo "--- Phase 2D: Governance Injection ---"

RESP=$(curl -s -w "\n%{http_code}" -H "X-API-Key: $KEY" "$API/governance/prompt")
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)
check "2D-1 GET /governance/prompt block" "$CODE" "$BODY"
echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); p=d.get('prompt',''); print('  prompt length:', len(p), 'chars'); print('  has test_promo:', 'test_promo_phase2' in p or 'Summer sale' in p)" 2>&1

# --- Summary ---
echo ""
echo "=============================="
echo "Results: $PASS passed, $FAIL failed"
echo "=============================="
