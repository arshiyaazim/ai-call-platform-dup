#!/bin/bash
# Test commands for the telephony webhook handler
# Usage: bash test.sh [BASE_URL]

BASE=${1:-https://iamazim.com}

echo "=== 1. Health Check ==="
curl -s "$BASE/api/v1/telephony/health" | python3 -m json.tool 2>/dev/null || echo "(no json)"
echo ""

echo "=== 2. Simulate Twilio Inbound Call (workflow 1) ==="
curl -s -X POST "$BASE/api/v1/telephony/inbound/1" \
  -H "User-Agent: TwilioProxy/1.1" \
  -d "CallSid=CA_TEST_$(date +%s)" \
  -d "AccountSid=${TWILIO_ACCOUNT_SID:-AC_TEST_PLACEHOLDER}" \
  -d "From=+880123456789" \
  -d "To=+447863767879" \
  -d "CallStatus=ringing" \
  -d "Direction=inbound" \
  -d "ApiVersion=2010-04-01" \
  -d "Caller=+880123456789" \
  -d "Called=+447863767879"
echo ""
echo ""

echo "=== 3. Duplicate Detection (same CallSid) ==="
curl -s -X POST "$BASE/api/v1/telephony/inbound/1" \
  -d "CallSid=CA_DEDUP_TEST_001" \
  -d "From=+880123456789" \
  -d "To=+447863767879" \
  -d "CallStatus=ringing" \
  -d "ApiVersion=2010-04-01"
echo ""
echo "--- sending same CallSid again ---"
curl -s -X POST "$BASE/api/v1/telephony/inbound/1" \
  -d "CallSid=CA_DEDUP_TEST_001" \
  -d "From=+880123456789" \
  -d "To=+447863767879" \
  -d "CallStatus=ringing" \
  -d "ApiVersion=2010-04-01"
echo ""
echo ""

echo "=== 4. Missing CallSid (should Hangup) ==="
curl -s -X POST "$BASE/api/v1/telephony/inbound/1" \
  -d "From=+880123456789" \
  -d "To=+447863767879"
echo ""
echo ""

echo "=== 5. Invalid Workflow ID ==="
curl -s -X POST "$BASE/api/v1/telephony/inbound/0" \
  -d "CallSid=CA_BAD_WF" \
  -d "From=+880123456789"
echo ""
echo ""

echo "=== 6. Lookup Event ==="
curl -s "$BASE/api/v1/telephony/events/CA_DEDUP_TEST_001" | python3 -m json.tool 2>/dev/null || echo "(no json)"
echo ""

echo "=== Done ==="
