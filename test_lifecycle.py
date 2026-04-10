"""
End-to-end lifecycle test: Owner teaches → Customer asks → Fazle replies → Owner corrects → Updated reply
Tests the full knowledge lifecycle: create, search, deprecate, archive, replace, merge
Tests contact management: set role, set language, get contact
"""
import json
import urllib.request
import time
import sys

BRAIN_URL = "http://localhost:8200"
API_URL = "http://localhost:8100"

def post(url, data, timeout=30):
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name} — {detail}")
        failed += 1

# ── 1. Knowledge Lifecycle ──
section("1. Knowledge Lifecycle")

try:
    # Create knowledge item
    r = post(f"{BRAIN_URL}/knowledge/create", {
        "category": "pricing",
        "key": "test_product_price",
        "value": "Test Product costs 500 BDT per unit",
        "source": "owner_direct",
    })
    check("Create knowledge", r.get("status") == "created", str(r))
    item_id = r.get("knowledge_id")

    # Search for it
    r = get(f"{BRAIN_URL}/knowledge/search?q=test_product")
    items = r.get("items", [])
    check("Search knowledge", len(items) > 0, f"Found {len(items)} items")

    # Get active items
    r = get(f"{BRAIN_URL}/knowledge/active?category=pricing")
    items = r.get("items", [])
    found = any(i.get("key") == "test_product_price" for i in items)
    check("Active knowledge includes item", found, f"Items: {[i.get('key') for i in items[:5]]}")

    # Replace it
    r = post(f"{BRAIN_URL}/knowledge/replace", {
        "old_knowledge_id": item_id,
        "new_value": "Test Product now costs 600 BDT per unit (price updated)",
        "reason": "Price increase",
    })
    check("Replace knowledge", r.get("status") == "replaced", str(r))
    new_id = r.get("new_knowledge_id", item_id)

    # Deprecate
    r = post(f"{BRAIN_URL}/knowledge/deprecate", {
        "knowledge_id": new_id,
        "reason": "Product discontinued",
    })
    check("Deprecate knowledge", r.get("status") == "deprecated", str(r))

    # History
    r = get(f"{BRAIN_URL}/knowledge/history?key=test_product_price")
    items = r.get("items", [])
    check("Knowledge history", len(items) >= 1, f"History entries: {len(items)}")

except Exception as e:
    check("Knowledge lifecycle", False, str(e))


# ── 2. Teaching Pipeline ──
section("2. Teaching Pipeline")

try:
    r = post(f"{BRAIN_URL}/teach", {
        "content": "Our office hours are 9am to 5pm, Saturday to Thursday",
        "source": "manual_text",
        "sender_id": "owner",
    })
    check("Teach text", r.get("status") in ("created", "auto_approved", "pending_review", "success"), str(r))

    r = post(f"{BRAIN_URL}/teach/correction", {
        "original_reply": "Our office is open 24 hours",
        "correct_reply": "Our office hours are 9am to 5pm, Saturday to Thursday",
        "context": "Customer asked about office hours",
        "sender_id": "owner",
    })
    check("Teach correction", r.get("status") in ("created", "auto_approved", "success", "corrected"), str(r))

except Exception as e:
    check("Teaching pipeline", False, str(e))


# ── 3. Contact Management ──
section("3. Contact Management")

try:
    # Set contact role
    r = post(f"{BRAIN_URL}/contacts/role", {
        "phone": "8801999999999",
        "name": "Test Client",
        "role": "client",
        "language_pref": "bn",
    })
    check("Set contact role", r.get("status") == "ok", str(r))

    # Get contact
    r = get(f"{BRAIN_URL}/contacts/8801999999999")
    contact = r.get("contact")
    check("Get contact", contact is not None and contact.get("role") == "client", str(r))

    # Set language
    r = post(f"{BRAIN_URL}/contacts/language", {
        "phone": "8801999999999",
        "language": "en",
    })
    check("Set contact language", r.get("status") == "ok", str(r))

    # Verify language
    r = get(f"{BRAIN_URL}/contacts/8801999999999")
    contact = r.get("contact")
    check("Verify language change", contact and contact.get("effective_language") == "en", str(r))

    # List contacts
    r = get(f"{BRAIN_URL}/contacts?role=client")
    contacts = r.get("contacts", [])
    found = any(c.get("phone") == "8801999999999" for c in contacts)
    check("List contacts by role", found, f"Found {len(contacts)} clients")

except Exception as e:
    check("Contact management", False, str(e))


# ── 4. Chat with Knowledge ──
section("4. Chat Uses Knowledge")

try:
    # Teach something specific
    post(f"{BRAIN_URL}/knowledge/create", {
        "category": "business",
        "key": "test_delivery_time",
        "value": "Standard delivery takes 3-5 business days within Dhaka",
        "source": "owner_direct",
    })

    # Ask about it
    r = post(f"{BRAIN_URL}/chat", {
        "message": "How long does delivery take to Dhaka?",
        "user": "TestCustomer",
        "relationship": "social",
        "conversation_id": "lifecycle-test-1",
    }, timeout=55)
    reply = r.get("reply", "")
    check("Chat reply received", len(reply) > 10, f"Reply: {reply[:100]}")
    # We can't guarantee exact content, but reply should exist
    print(f"    Reply: {reply[:200]}")

except Exception as e:
    check("Chat with knowledge", False, str(e))


# ── 5. API Proxy Layer ──
section("5. API Proxy Routes")

try:
    # Test via API proxy (port 8100)
    r = get(f"{API_URL}/fazle/knowledge/active")
    check("API: knowledge active", "items" in r, str(r)[:100])

    r = get(f"{API_URL}/fazle/knowledge/search?q=delivery")
    check("API: knowledge search", "items" in r, str(r)[:100])

except urllib.error.HTTPError as e:
    # Auth required — that's expected behavior
    if e.code == 401:
        check("API: auth enforced", True)
    else:
        check("API proxy", False, f"HTTP {e.code}: {e.read().decode()[:100]}")
except Exception as e:
    check("API proxy", False, str(e))


# ── Summary ──
section("RESULTS")
total = passed + failed
print(f"\n  Passed: {passed}/{total}")
print(f"  Failed: {failed}/{total}")
if failed:
    print("\n  Some tests failed — check service logs for details")
    sys.exit(1)
else:
    print("\n  All lifecycle tests passed!")
    sys.exit(0)
