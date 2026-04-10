#!/usr/bin/env python3
"""Test brain knowledge integration - runs INSIDE fazle-brain container."""
import httpx
import json
import sys
import time

BASE = "http://localhost:8200"

tests = [
    {"name": "job_seeker", "message": "chakri ache?", "caller_id": "test1", "owner_id": "owner1", "relationship": "social"},
    {"name": "client_service", "message": "guard lagbe", "caller_id": "test2", "owner_id": "owner1", "relationship": "social"},
    {"name": "salary_query", "message": "beton koto?", "caller_id": "test3", "owner_id": "owner1", "relationship": "social"},
    {"name": "complaint", "message": "problem ache guard er sathe", "caller_id": "test4", "owner_id": "owner1", "relationship": "social"},
    {"name": "emergency", "message": "urgent guard needed now", "caller_id": "test5", "owner_id": "owner1", "relationship": "social"},
    {"name": "fallback", "message": "hello there", "caller_id": "test6", "owner_id": "owner1", "relationship": "social"},
]

passed = 0
failed = 0

for t in tests:
    name = t.pop("name")
    print(f"\n--- Test: {name} ---")
    print(f"Input: {t['message']}")
    try:
        start = time.time()
        r = httpx.post(f"{BASE}/chat", json=t, timeout=120)
        elapsed = time.time() - start
        data = r.json()
        reply = data.get("reply", data.get("response", ""))
        print(f"Status: {r.status_code}")
        print(f"Reply: {reply[:200]}")
        print(f"Time: {elapsed:.1f}s")
        if r.status_code == 200 and len(reply) > 0:
            passed += 1
            print("PASS")
        else:
            failed += 1
            print("FAIL - empty or error")
    except Exception as e:
        failed += 1
        print(f"FAIL - {e}")

print(f"\n=== Results: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
