import urllib.request, json

# Test 1: Job message with phone
data = json.dumps({
    "message": "guard er chakri ache? 01812345678",
    "relationship": "social",
    "conversation_id": "test-lead-010"
}).encode()
req = urllib.request.Request(
    "http://fazle-brain:8200/chat",
    data=data,
    headers={"Content-Type": "application/json"},
)
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read().decode())
print("Test 1 - Job with phone:")
print("  Route:", result.get("route"))
print("  Reply:", result.get("reply", "")[:200])
print()

# Test 2: Complaint without phone
data2 = json.dumps({
    "message": "apnar guard duty te ase na",
    "relationship": "social",
    "conversation_id": "test-lead-020"
}).encode()
req2 = urllib.request.Request(
    "http://fazle-brain:8200/chat",
    data=data2,
    headers={"Content-Type": "application/json"},
)
resp2 = urllib.request.urlopen(req2, timeout=30)
result2 = json.loads(resp2.read().decode())
print("Test 2 - Complaint no phone:")
print("  Route:", result2.get("route"))
reply2 = result2.get("reply", "")
has_prompt = "মোবাইল" in reply2 or "নাম্বার" in reply2
print("  Has phone prompt:", has_prompt)
print("  Reply:", reply2[:200])
print()

# Test 3: Greeting (NOT lead-worthy)
data3 = json.dumps({
    "message": "hello bhai",
    "relationship": "social",
    "conversation_id": "test-lead-030"
}).encode()
req3 = urllib.request.Request(
    "http://fazle-brain:8200/chat",
    data=data3,
    headers={"Content-Type": "application/json"},
)
resp3 = urllib.request.urlopen(req3, timeout=30)
result3 = json.loads(resp3.read().decode())
print("Test 3 - Greeting (no lead):")
print("  Route:", result3.get("route"))
print("  Reply:", result3.get("reply", "")[:200])
print()

# Check leads
req4 = urllib.request.Request("http://fazle-api:8100/leads")
resp4 = urllib.request.urlopen(req4)
leads = json.loads(resp4.read().decode())
print(f"Total leads: {len(leads)}")
for l in leads:
    print(f"  id={l['id']} phone={l['phone']} intent={l['intent']} name={l['name']}")
