#!/bin/bash
# Test WBOM through full chain with correct login

echo "=== Login ==="
RESP=$(curl -s -X POST http://127.0.0.1:8100/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"azim@iamazim.com","password":"Jahanalo@2019"}')
TOKEN=$(echo "$RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "FAIL: $RESP"
    exit 1
fi
echo "OK: ${TOKEN:0:20}..."

echo ""
echo "=== WBOM employees via API (localhost:8100) ==="
R1=$(curl -s 'http://127.0.0.1:8100/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN")
echo "$R1" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("success:", d.get("success"), "count:", len(d.get("data",[])))'

echo ""
echo "=== WBOM employees via nginx (https://fazle.iamazim.com) ==="
R2=$(curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN")
echo "$R2" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("success:", d.get("success"), "count:", len(d.get("data",[])))'

echo ""
echo "=== WBOM employees/count via nginx ==="
curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees/count' \
  -H "Authorization: Bearer $TOKEN"

echo ""
echo ""
echo "=== 403 count in WBOM logs (last 60s) ==="
docker logs fazle-wbom --since 60s 2>&1 | grep -c "403" || echo "0"

echo ""
echo "=== 200 count in WBOM logs (last 60s) ==="
docker logs fazle-wbom --since 60s 2>&1 | grep -c "200" || echo "0"

echo ""
echo "DONE"
