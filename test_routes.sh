#!/bin/bash
cd /home/azim/ai-call-platform

echo "=== Test API social proxy (via /fazle/social) ==="
echo "--- /fazle/social/stats ---"
curl -s http://localhost:8100/fazle/social/stats | head -c 300
echo ""

echo "--- /fazle/social/contacts/book?limit=2 ---"
curl -s http://localhost:8100/fazle/social/contacts/book?limit=2 | head -c 300
echo ""

echo "--- /fazle/social/whatsapp/messages?limit=2 ---"
curl -s http://localhost:8100/fazle/social/whatsapp/messages?limit=2 | head -c 300
echo ""

echo "--- /fazle/social/integrations ---"
curl -s http://localhost:8100/fazle/social/integrations | head -c 300
echo ""

echo ""
echo "=== Test WBOM via API proxy ==="
KEY=$(grep INTERNAL_KEY .env | head -1 | cut -d= -f2)
echo "--- /fazle/wbom/contacts?limit=2 ---"
curl -s -H "X-INTERNAL-KEY: $KEY" http://localhost:9900/api/wbom/contacts?limit=2 | python3 -c "
import json,sys
d=json.load(sys.stdin)
if isinstance(d,list):
    print(f'Got {len(d)} contacts')
    if d: print('First:', json.dumps(d[0], indent=2)[:200])
else:
    print(json.dumps(d, indent=2)[:300])
"

echo ""
echo "=== Owner query routes via API ==="
echo "--- Contact list (needs auth) ---"
curl -s http://localhost:8100/fazle/owner/contacts?limit=2 -w '\nHTTP %{http_code}' | tail -2
echo ""

echo ""
echo "=== Frontend pages ==="
echo "--- Dashboard ---"
curl -s http://localhost:3020 -o /dev/null -w 'HTTP %{http_code}'
echo ""
echo "--- Login page ---"
curl -s http://localhost:3020/login -o /dev/null -w 'HTTP %{http_code}'
echo ""
echo "--- Social page ---"
curl -s http://localhost:3020/social -o /dev/null -w 'HTTP %{http_code}'
echo ""
echo "--- Contacts page ---"
curl -s http://localhost:3020/contacts -o /dev/null -w 'HTTP %{http_code}'
echo ""
echo "--- WBOM page ---"
curl -s http://localhost:3020/wbom -o /dev/null -w 'HTTP %{http_code}'
echo ""

echo ""
echo "=== DONE ==="
