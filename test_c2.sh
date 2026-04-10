#!/bin/bash
curl -s -X POST http://localhost:8200/chat/agent \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello test","user_id":"test-c2","platform":"api"}' | python3 -m json.tool | head -15
