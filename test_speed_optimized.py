#!/usr/bin/env python3
"""Speed test for optimized brain. Runs inside fazle-brain container."""
import httpx
import json
import time
import sys

BASE = "http://localhost:8200"

tests = [
    {"name": "fast_chakri", "message": "chakri ache?", "relationship": "social"},
    {"name": "fast_beton", "message": "beton koto?", "relationship": "social"},
    {"name": "fast_guard", "message": "guard lagbe", "relationship": "social"},
    {"name": "llm_complaint", "message": "problem ache guard er sathe", "relationship": "social"},
    {"name": "llm_emergency", "message": "urgent guard needed now", "relationship": "social"},
    {"name": "llm_hello", "message": "hello there", "relationship": "social"},
    {"name": "cache_chakri_2", "message": "chakri ache?", "relationship": "social"},
    {"name": "self_fast", "message": "hey bro", "relationship": "self"},
]

passed = 0
failed = 0
times = []

for t in tests:
    name = t.pop("name")
    t["caller_id"] = f"speed_test_{name}"
    t["owner_id"] = "owner1"
    print(f"\n--- {name} ---")
    print(f"Input: {t['message']} (rel={t['relationship']})")
    try:
        start = time.time()
        r = httpx.post(f"{BASE}/chat", json=t, timeout=120)
        elapsed = time.time() - start
        data = r.json()
        reply = data.get("reply", "")
        route = data.get("route", "unknown")
        print(f"Status: {r.status_code} | Route: {route}")
        print(f"Reply: {reply[:120]}")
        print(f"Time: {elapsed:.2f}s {'FAST' if elapsed < 5 else 'SLOW'}")
        times.append((name, elapsed, route))
        if r.status_code == 200 and len(reply) > 0:
            passed += 1
        else:
            failed += 1
            print("FAIL - empty reply")
    except Exception as e:
        failed += 1
        times.append((name, 999, "error"))
        print(f"FAIL - {e}")

print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
print(f"\nTiming Summary:")
for name, t, route in times:
    status = "OK" if t < 5 else "SLOW" if t < 15 else "CRITICAL"
    print(f"  {name:20s} {t:6.2f}s  [{route:20s}] {status}")
avg = sum(t for _, t, _ in times) / len(times) if times else 0
fast_count = sum(1 for _, t, _ in times if t < 5)
print(f"\nAverage: {avg:.2f}s | Fast (<5s): {fast_count}/{len(times)}")
sys.exit(0 if failed == 0 else 1)
