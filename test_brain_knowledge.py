#!/usr/bin/env python3
"""Test the upgraded brain knowledge integration."""
import requests
import time
import json

BRAIN_URL = "http://localhost:8200"

TEST_CASES = [
    {
        "name": "Test 1: Job Inquiry (BN)",
        "payload": {
            "message": "চাকরি আছে?",
            "relationship": "social",
            "user_name": "TestUser",
        },
        "expect_intent": "job_seeker",
    },
    {
        "name": "Test 2: Guard Service (BN)",
        "payload": {
            "message": "গার্ড লাগবে",
            "relationship": "social",
            "user_name": "TestClient",
        },
        "expect_intent": "client_service",
    },
    {
        "name": "Test 3: Salary Query (BN)",
        "payload": {
            "message": "বেতন কত?",
            "relationship": "social",
            "user_name": "TestApplicant",
        },
        "expect_intent": "salary",
    },
    {
        "name": "Test 4: Complaint (EN mixed)",
        "payload": {
            "message": "problem আছে",
            "relationship": "social",
            "user_name": "TestComplainer",
        },
        "expect_intent": "complaint",
    },
    {
        "name": "Test 5: Emergency (EN)",
        "payload": {
            "message": "urgent guard needed",
            "relationship": "social",
            "user_name": "TestEmergency",
        },
        "expect_intent": "emergency",
    },
    {
        "name": "Test 6: Random/Fallback",
        "payload": {
            "message": "hello there",
            "relationship": "social",
            "user_name": "RandomCaller",
        },
        "expect_intent": "fallback",
    },
]

print("=" * 60)
print("  Fazle Brain — Knowledge Integration Test Suite")
print("=" * 60)

results = []
for tc in TEST_CASES:
    print(f"\n--- {tc['name']} ---")
    print(f"  Message: {tc['payload']['message']}")
    print(f"  Expected intent: {tc['expect_intent']}")

    try:
        t0 = time.time()
        resp = requests.post(
            f"{BRAIN_URL}/chat",
            json=tc["payload"],
            timeout=60,
        )
        elapsed = time.time() - t0
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("reply", "")
        route = data.get("domain_route") or data.get("route", "")

        print(f"  Reply: {reply[:200]}")
        print(f"  Route: {route}")
        print(f"  Time: {elapsed:.2f}s")

        results.append({
            "name": tc["name"],
            "status": "OK" if reply else "EMPTY",
            "reply_len": len(reply),
            "time": f"{elapsed:.2f}s",
        })
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append({
            "name": tc["name"],
            "status": f"FAIL: {e}",
            "reply_len": 0,
            "time": "N/A",
        })

    time.sleep(1)  # Rate limit spacing

print("\n" + "=" * 60)
print("  RESULTS SUMMARY")
print("=" * 60)
for r in results:
    status_icon = "OK" if r["status"] == "OK" else "FAIL"
    print(f"  [{status_icon}] {r['name']} | reply={r['reply_len']}ch | {r['time']}")
print("=" * 60)
