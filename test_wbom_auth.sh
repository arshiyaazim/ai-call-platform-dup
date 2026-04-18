#!/bin/bash
cd /home/azim/ai-call-platform

echo "=== 1. Check WBOM_INTERNAL_KEY in .env ==="
grep WBOM_INTERNAL_KEY .env || echo "NOT SET"

echo ""
echo "=== 2. What fazle-api sees ==="
docker exec fazle-api env | grep -i WBOM || echo "NONE"

echo ""
echo "=== 3. What fazle-wbom sees ==="
docker exec fazle-wbom env | grep -i WBOM || echo "NONE"

echo ""
echo "=== 4. WBOM direct test (no key) ==="
curl -s -o /dev/null -w "HTTP %{http_code}" http://fazle-wbom:9900/api/wbom/employees?limit=1 2>/dev/null || echo "Can't reach directly"

echo ""
echo "=== 5. WBOM via docker network (from fazle-api container) ==="
docker exec fazle-api python3 -c "
import os, urllib.request
key = os.environ.get('FAZLE_WBOM_INTERNAL_KEY', '')
print('API has FAZLE_WBOM_INTERNAL_KEY:', repr(key[:10] + '...' if len(key)>10 else repr(key)))
req = urllib.request.Request('http://fazle-wbom:9900/api/wbom/employees?limit=1')
if key:
    req.add_header('X-INTERNAL-KEY', key)
try:
    r = urllib.request.urlopen(req)
    print('With key -> HTTP', r.status, r.read().decode()[:200])
except Exception as e:
    print('With key -> FAIL:', e)
"

echo ""
echo "=== 6. Check rapid-fire requests (blinking indicator) ==="
docker logs fazle-wbom 2>&1 | grep "employees" | tail -20 | awk '{print $1}' | sort | uniq -c | sort -rn | head -5
