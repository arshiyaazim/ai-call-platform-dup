#!/usr/bin/env python3
"""Test Fazle AI v2 endpoints."""
import urllib.request
import json
import time

BASE = "http://fazle-brain:8200"

def test_route(msg):
    data = json.dumps({"message": msg}).encode()
    req = urllib.request.Request(f"{BASE}/route", data=data, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
    return resp["route"]

print("=== ROUTING TESTS ===")
for msg in ["hello", "hi there", "explain quantum physics in detail", "search the web for latest AI news", "remember my name is Azim"]:
    route = test_route(msg)
    print(f"  {route:15s} <- '{msg}'")

print("\n=== TTFB STREAMING ===")
url = f"{BASE}/chat/agent/stream"
for i in range(3):
    data = json.dumps({"message": "say hi", "user": "test"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    start = time.time()
    resp = urllib.request.urlopen(req, timeout=30)
    first = resp.read(1)
    ttfb = (time.time() - start) * 1000
    resp.read()
    print(f"  Run {i+1}: TTFB={ttfb:.0f}ms")

print("\n=== ALL TESTS DONE ===")
