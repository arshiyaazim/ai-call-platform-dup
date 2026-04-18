#!/bin/bash
# Test social engine from within docker network
echo "=== Social Engine via docker network ==="
docker exec fazle-api python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://fazle-social-engine:9800/health')
    print('Health:', r.read().decode())
except Exception as e:
    print('Health FAIL:', e)

try:
    r = urllib.request.urlopen('http://fazle-social-engine:9800/stats')
    print('Stats:', r.read().decode())
except Exception as e:
    print('Stats FAIL:', e)

try:
    r = urllib.request.urlopen('http://fazle-social-engine:9800/contacts?limit=2')
    data = r.read().decode()
    print('Contacts:', data[:300])
except Exception as e:
    print('Contacts FAIL:', e)

try:
    r = urllib.request.urlopen('http://fazle-social-engine:9800/whatsapp/messages?limit=2')
    data = r.read().decode()
    print('Messages:', data[:300])
except Exception as e:
    print('Messages FAIL:', e)
"

echo ""
echo "=== API endpoints that proxy to social engine ==="
KEY=$(grep INTERNAL_KEY /home/azim/ai-call-platform/.env | head -1 | cut -d= -f2)

# Test via fazle-api proxy (8100 is exposed)
echo "--- /api/social/stats ---"
curl -s -H "Authorization: Bearer placeholder" http://localhost:8100/api/social/stats 2>/dev/null | head -c 300
echo ""
echo "--- /api/social/contacts/book ---"
curl -s -H "Authorization: Bearer placeholder" http://localhost:8100/api/social/contacts/book?limit=2 2>/dev/null | head -c 300
echo ""

echo ""
echo "=== Social engine container logs (last startup) ==="
docker logs fazle-social-engine 2>&1 | head -20
