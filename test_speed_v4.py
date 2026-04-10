"""Speed test v4 — Tests fast triggers, LLM cache, and LLM path."""
import httpx, time, sys

BASE = "http://127.0.0.1:8200"
TESTS = [
    # Fast trigger tests (should be <0.5s)
    ("fast_chakri", "ami ekta chakri chai", "social"),
    ("fast_beton", "beton koto?", "social"),
    ("fast_guard", "guard lagbe", "social"),
    ("fast_hello", "hello", "social"),
    ("fast_office", "apnader office kothay?", "social"),
    ("fast_address", "apnar address ki?", "social"),
    ("fast_rate", "security rate koto?", "social"),
    # LLM path test — phrased to avoid all fast triggers
    ("llm_unique", "apni koto bochhor dhore ei kaj korchen?", "social"),
    # Self fast test
    ("self_fast", "hey bro", "self"),
    # Cache repeat — same as llm_unique, should use LLM cache on 2nd call
    ("cache_repeat", "apni koto bochhor dhore ei kaj korchen?", "social"),
]

results = []
for name, msg, rel in TESTS:
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE}/chat", json={
            "message": msg,
            "user_name": "SpeedTest",
            "user_identifier": "speed-test-001",
            "relationship": rel,
            "language": "bn",
        }, timeout=60)
        elapsed = time.time() - t0
        data = r.json()
        route = data.get("route", "unknown")
        reply = data.get("reply", "")[:60]
        results.append((name, elapsed, route, reply))
        print(f"  {name}: {elapsed:.2f}s [{route}] → {reply}")
    except Exception as e:
        elapsed = time.time() - t0
        results.append((name, elapsed, "ERROR", str(e)[:60]))
        print(f"  {name}: {elapsed:.2f}s [ERROR] → {e}")

# Summary
print("\n" + "="*60)
fast_count = sum(1 for _, t, _, _ in results if t < 5)
avg = sum(t for _, t, _, _ in results) / len(results)
print(f"RESULTS: {fast_count}/{len(results)} under 5s | Average: {avg:.2f}s")
for name, t, route, _ in results:
    status = "✓" if t < 5 else "✗ SLOW"
    print(f"  {status} {name}: {t:.2f}s [{route}]")
