#!/bin/bash
# Test C2: /chat/agent should return proper JSON
echo "=== Testing C2: /chat/agent ==="
curl -s -X POST http://localhost:8200/chat/agent \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello test","user_id":"test-c2","platform":"api"}' 2>&1

echo ""
echo "=== Testing C1: /owner/senders ==="
curl -s -H 'X-API-Key: 2aMFFfIaGDfgfP6JiXaevEgMRx9aZtgAzYriHGRcpvdEcWCtp7Xpqul0BYdjFchq' http://localhost:8100/owner/senders?hours=24 2>&1 | head -5

echo ""
echo "=== Checking container logs for errors ==="
docker logs fazle-brain --tail 20 2>&1 | grep -i "error\|exception\|traceback" || echo "No errors in brain logs"
docker logs fazle-api --tail 20 2>&1 | grep -i "error\|exception\|traceback" || echo "No errors in API logs"
docker logs fazle-social-engine --tail 20 2>&1 | grep -i "error\|exception\|traceback" || echo "No errors in social-engine logs"
