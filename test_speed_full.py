#!/usr/bin/env python3
"""Full speed test including LLM-required queries."""
import httpx
import time
import sys

BASE = "http://localhost:8200"

tests = [
    # Fast path (short-circuit)
    {"name": "fast_chakri", "message": "chakri ache?", "relationship": "social"},
    {"name": "fast_beton", "message": "beton koto?", "relationship": "social"},
    {"name": "fast_guard", "message": "guard lagbe", "relationship": "social"},
    {"name": "fast_hello", "message": "hello there", "relationship": "social"},
    {"name": "fast_complaint", "message": "problem ache", "relationship": "social"},
    {"name": "fast_emergency", "message": "urgent guard needed", "relationship": "social"},
    # LLM path (no fast trigger match)
    {"name": "llm_custom1", "message": "apnader office kothay?", "relationship": "social"},
    {"name": "llm_custom2", "message": "ami ekta event er jonno security chai", "relationship": "social"},
    # Self path
    {"name": "self_fast", "message": "hey bro", "relationship": "self"},
    # Cache test (repeat)
    {"name": "cache_repeat", "message": "apnader office kothay?", "relationship": "social"},
]

passed = 0
failed = 0
times = []

for t in tests:
    name = t.pop("name")
    t["caller_id"] = f"speed_{name}"
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
        print(f"Route: {route} | Reply: {reply[:100]}")
        print(f"Time: {elapsed:.2f}s {'FAST' if elapsed < 5 else 'SLOW'}")
        times.append((name, elapsed, route))
        passed += 1 if r.status_code == 200 and reply else 0
        failed += 0 if r.status_code == 200 and reply else 1
    except Exception as e:
        failed += 1
        times.append((name, 999, "error"))
        print(f"FAIL - {e}")

print(f"\n{'='*60}")
print(f"Results: {passed} passed, {failed} failed\n")
print(f"{'Test':<20} {'Time':>8} {'Route':<22} {'Status'}")
print("-" * 60)
for name, t, route in times:
    status = "OK" if t < 5 else "SLOW" if t < 15 else "CRITICAL"
    print(f"  {name:<18} {t:>6.2f}s  {route:<22} {status}")
avg = sum(t for _, t, _ in times) / len(times) if times else 0
fast = sum(1 for _, t, _ in times if t < 5)
print(f"\nAverage: {avg:.2f}s | Fast (<5s): {fast}/{len(times)}")
sys.exit(0 if failed == 0 else 1)
