import httpx
try:
    r = httpx.get("http://fazle-api:8100/health", timeout=5)
    print(f"API health: {r.status_code} {r.text[:100]}")
except Exception as e:
    print(f"API unreachable: {e}")

try:
    r = httpx.get("http://fazle-api:8100/knowledge/search?q=chakri&caller_id=test1&limit=3", timeout=5)
    print(f"Knowledge search: {r.status_code} {r.text[:300]}")
except Exception as e:
    print(f"Knowledge search failed: {e}")
