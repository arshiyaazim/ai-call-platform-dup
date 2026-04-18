#!/bin/bash
# Full end-to-end WBOM test through nginx

echo "=== 1. Get valid auth token ==="
TOKEN=$(curl -s -X POST http://127.0.0.1:8100/fazle/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"azim","password":"Jahanalo@2019"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token","FAIL"))')
echo "Token: ${TOKEN:0:20}..."

echo ""
echo "=== 2. WBOM employees via API (8100) ==="
curl -s 'http://127.0.0.1:8100/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("Success:", d.get("success"), "- Count:", len(d.get("data",[])), "employees")'

echo ""
echo "=== 3. WBOM employees via nginx (fazle.iamazim.com) ==="
curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees?limit=2' \
  -H "Authorization: Bearer $TOKEN" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("Success:", d.get("success"), "- Count:", len(d.get("data",[])), "employees")'

echo ""
echo "=== 4. WBOM employees count ==="
curl -s 'https://fazle.iamazim.com/api/fazle/wbom/employees/count' \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool 2>/dev/null || echo "FAILED"

echo ""
echo "=== 5. Check for 403 errors in last 30s ==="
COUNT_403=$(docker logs fazle-wbom --since 30s 2>&1 | grep -c "403" || echo "0")
echo "403 errors in last 30s: $COUNT_403"

echo ""
echo "=== 6. Check for successful WBOM requests ==="
docker logs fazle-wbom --since 30s 2>&1 | grep "200" | tail -5

echo ""
echo "=== DONE ==="
