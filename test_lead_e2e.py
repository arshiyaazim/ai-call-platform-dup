import urllib.request, json, sys

# Test 1: Job message with phone → should capture lead
tests = [
    {
        "name": "Job seeker with phone",
        "payload": {
            "message": "guard er chakri ache? 01812345678",
            "relationship": "social",
            "conversation_id": "test-lead-001"
        }
    },
    {
        "name": "Complaint (no phone → should get prompt)",
        "payload": {
            "message": "apnar guard duty te ase na",
            "relationship": "social",
            "conversation_id": "test-lead-002"
        }
    },
    {
        "name": "Greeting (NOT lead-worthy)",
        "payload": {
            "message": "hello bhai",
            "relationship": "social",
            "conversation_id": "test-lead-003"
        }
    },
]

for t in tests:
    data = json.dumps(t["payload"]).encode()
    req = urllib.request.Request(
        "http://localhost:8200/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        reply = result.get("reply", "")[:120]
        route = result.get("route", "")
        print(f"[{t['name']}] route={route} reply={reply}")
    except Exception as e:
        print(f"[{t['name']}] ERROR: {e}")
    print()

# Check leads table
req2 = urllib.request.Request("http://localhost:8100/leads")
resp2 = urllib.request.urlopen(req2)
leads = json.loads(resp2.read().decode())
print(f"Total leads in DB: {len(leads)}")
for lead in leads:
    print(f"  id={lead['id']} phone={lead['phone']} intent={lead['intent']} name={lead['name']}")
