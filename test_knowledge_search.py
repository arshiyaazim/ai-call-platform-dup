import httpx
base = "http://fazle-api:8100"

# Check what's actually in the DB
print("=== All conversation entries (first 10) ===")
r = httpx.get(f"{base}/knowledge/search", params={"q": "%", "category": "conversation", "limit": 10})
print(f"Status: {r.status_code}")
for item in r.json().get("results", []):
    print(f"  [{item.get('subcategory','')}] {item['key']}: {item['value'][:80]}")

print("\n=== Search with Bangla 'চাকরি' ===")
r = httpx.get(f"{base}/knowledge/search", params={"q": "চাকরি", "category": "conversation", "limit": 5})
print(f"Status: {r.status_code}, Count: {r.json().get('count',0)}")
for item in r.json().get("results", []):
    print(f"  {item['key']}: {item['value'][:80]}")

print("\n=== Search with 'job_seeker' ===")
r = httpx.get(f"{base}/knowledge/search", params={"q": "job_seeker", "category": "conversation", "limit": 5})
print(f"Status: {r.status_code}, Count: {r.json().get('count',0)}")
for item in r.json().get("results", []):
    print(f"  {item['key']}: {item['value'][:80]}")

print("\n=== Search with 'chakri ache?' ===")
r = httpx.get(f"{base}/knowledge/search", params={"q": "chakri ache?", "limit": 5})
print(f"Status: {r.status_code}, Count: {r.json().get('count',0)}")
for item in r.json().get("results", []):
    print(f"  {item['key']}: {item['value'][:80]}")
