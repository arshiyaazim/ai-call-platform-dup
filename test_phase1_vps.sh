#!/bin/bash
echo "=== BRAIN HEALTH ==="
curl -s localhost:8200/health
echo ""

echo "=== BRAIN CONTROL-PLANE STATUS ==="
curl -s localhost:8200/control-plane/status | python3 -c '
import sys, json
d = json.load(sys.stdin)
t = d["taxonomy"]
c = d["capabilities"]
print("Phase:", d["phase"])
print("Commands:", t["total_commands"], "(categories:", len(t["by_category"]), ")")
print("  Password-protected:", t["password_protected"])
print("  Confirmation-required:", t["confirmation_required"])
print("Capabilities:", c["total"])
print("  Implemented:", c["by_status"]["implemented"])
print("  Partial:", c["by_status"]["partial"])
print("  Missing:", c["by_status"]["missing"])
print("  Disallowed:", c["by_status"]["disallowed"])
'
echo ""

echo "=== GOVERNANCE FACTS ==="
curl -s localhost:8100/governance/facts | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("Total facts:", d["count"])
cats = {}
for f in d["facts"]:
    cats.setdefault(f["category"], []).append(f["fact_key"])
for cat, keys in sorted(cats.items()):
    print("  [" + cat + "]:", ", ".join(keys))
'
echo ""

echo "=== GOVERNANCE PHRASING ==="
curl -s localhost:8100/governance/phrasing | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("Total rules:", d["count"])
for r in d["rules"]:
    print("  " + r["topic"] + ": Say \"" + r["preferred_phrasing"][:40] + "...\"")
'
echo ""

echo "=== GOVERNANCE PROMPT (first 400 chars) ==="
curl -s localhost:8100/governance/prompt | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("Facts:", d["facts_count"], "Rules:", d["rules_count"])
print(d["prompt"][:400])
'
echo ""

echo "=== CORRECTIONS (should be empty) ==="
curl -s localhost:8100/governance/corrections
echo ""

echo "=== FACT HISTORY: training/training_duration ==="
curl -s localhost:8100/governance/facts/training/training_duration/history | python3 -c '
import sys, json
d = json.load(sys.stdin)
print("Versions:", len(d["versions"]))
for v in d["versions"]:
    print("  v" + str(v["version"]) + ": " + v["fact_value"] + " (" + v["status"] + ")")
'
echo ""

echo "=== ALL TESTS COMPLETE ==="
