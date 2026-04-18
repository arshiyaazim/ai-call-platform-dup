#!/bin/bash
# Test login and WBOM through the full chain

echo "=== Login via API ==="
RESP=$(curl -s -X POST http://127.0.0.1:8100/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"azim","password":"Jahanalo@2019"}')
echo "Login response: ${RESP:0:100}..."

TOKEN=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "Login via /auth/login failed, trying /fazle/auth/login..."
    RESP=$(curl -s -X POST http://127.0.0.1:8100/fazle/auth/login \
      -H 'Content-Type: application/json' \
      -d '{"username":"azim","password":"Jahanalo@2019"}')
    echo "Login response: ${RESP:0:100}..."
    TOKEN=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
fi

if [ -z "$TOKEN" ]; then
    echo "FAIL: Could not get token. Listing API routes..."
    curl -s http://127.0.0.1:8100/openapi.json 2>/dev/null | python3 -c 'import sys,json; [print(p) for p in sorted(json.load(sys.stdin).get("paths",{}))]' 2>/dev/null
    exit 1
fi

echo "Token: ${TOKEN:0:20}..."

echo ""
echo "=== WBOM employees via localhost API ==="
curl -s 'http://127.0.0.1:8100/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool 2>/dev/null | head -15

echo ""
echo "=== WBOM employees via nginx ==="
curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool 2>/dev/null | head -15

echo ""
echo "=== WBOM employees/count via nginx ==="
curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees/count' \
  -H "Authorization: Bearer $TOKEN"

echo ""
echo "=== Recent WBOM logs ==="
docker logs fazle-wbom --since 10s 2>&1 | tail -10

echo ""
echo "=== 403 count in last 60s ==="
docker logs fazle-wbom --since 60s 2>&1 | grep -c "403" || echo "0"

echo "DONE"
