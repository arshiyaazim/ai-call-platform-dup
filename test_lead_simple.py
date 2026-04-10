import urllib.request, json
data = json.dumps({"message": "ami Karim, guard er chakri chai 01912345678", "relationship": "social", "conversation_id": "lead-test-100"}).encode()
req = urllib.request.Request("http://127.0.0.1:8200/chat", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read().decode())
print("route:", result.get("route"))
print("reply:", result.get("reply", "")[:300])
