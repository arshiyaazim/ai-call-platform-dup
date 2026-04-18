#!/bin/bash
set -e
cd /home/azim/ai-call-platform
KEY=$(grep INTERNAL_KEY .env | head -1 | cut -d= -f2)
API=http://localhost:8100
WBOM=http://localhost:9900
SE=http://localhost:9800

echo '=== 1. WBOM Health ==='
curl -sf $WBOM/health | python3 -m json.tool || echo 'FAIL'

echo ''
echo '=== 2. WBOM Employees ==='
curl -sf -H "X-INTERNAL-KEY: $KEY" "$WBOM/api/wbom/employees?limit=3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('employees:', len(d.get('employees',[])), 'rows')
" || echo 'FAIL'

echo ''
echo '=== 3. WBOM Contacts ==='
curl -sf -H "X-INTERNAL-KEY: $KEY" "$WBOM/api/wbom/contacts?limit=3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(json.dumps(d, indent=2)[:500])
" || echo 'FAIL'

echo ''
echo '=== 4. Social Engine Health ==='
curl -sf $SE/health | python3 -m json.tool || echo 'FAIL'

echo ''
echo '=== 5. Social Engine /contacts ==='
curl -sf -H "X-INTERNAL-KEY: $KEY" "$SE/contacts?limit=3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('contacts:', len(d) if isinstance(d,list) else d)
" || echo 'FAIL or empty'

echo ''
echo '=== 6. Social Engine /stats ==='
curl -sf -H "X-INTERNAL-KEY: $KEY" "$SE/stats" | python3 -m json.tool || echo 'FAIL'

echo ''
echo '=== 7. Social Engine /whatsapp/messages ==='
curl -sf -H "X-INTERNAL-KEY: $KEY" "$SE/whatsapp/messages?limit=3" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('messages:', len(d) if isinstance(d,list) else d)
" || echo 'FAIL or empty'

echo ''
echo '=== 8. API Health ==='
curl -sf $API/health | python3 -m json.tool || echo 'FAIL'

echo ''
echo '=== 9. Frontend Health ==='
CODE=$(curl -sf http://localhost:3020 -o /dev/null -w '%{http_code}' || true)
echo "HTTP $CODE"

echo ''
echo '=== 10. Frontend API proxy ==='
CODE=$(curl -s http://localhost:3020/api/social/contacts/book?limit=2 -o /dev/null -w '%{http_code}' || true)
echo "HTTP $CODE (401=needs auth, 200=ok)"

echo ''
echo '=== 11. DB: No active legacy tables ==='
docker exec ai-postgres psql -U postgres -t -A -c "SELECT coalesce(string_agg(tablename, ', '), 'NONE') FROM pg_tables WHERE schemaname='public' AND tablename IN ('ops_employees','ops_payments','fazle_contacts','fazle_social_contacts','fazle_social_messages')"

echo ''
echo '=== 12. DB: Legacy backups exist ==='
docker exec ai-postgres psql -U postgres -t -A -c "SELECT coalesce(string_agg(tablename, ', ' ORDER BY tablename), 'NONE') FROM pg_tables WHERE tablename LIKE '_legacy_%'"

echo ''
echo '=== 13. DB: WBOM row counts ==='
docker exec ai-postgres psql -U postgres -t -A -c "SELECT 'wbom_employees: ' || count(*) FROM wbom_employees"
docker exec ai-postgres psql -U postgres -t -A -c "SELECT 'wbom_contacts: ' || count(*) FROM wbom_contacts"
docker exec ai-postgres psql -U postgres -t -A -c "SELECT 'wbom_cash_transactions: ' || count(*) FROM wbom_cash_transactions"
docker exec ai-postgres psql -U postgres -t -A -c "SELECT 'wbom_whatsapp_messages: ' || count(*) FROM wbom_whatsapp_messages"

echo ''
echo '=== 14. Social-engine logs (errors) ==='
docker logs fazle-social-engine 2>&1 | grep -i 'error\|traceback\|exception' | tail -5 || echo 'No errors found'

echo ''
echo '=== 15. API logs (errors) ==='
docker logs fazle-api 2>&1 | grep -i 'error\|traceback\|exception' | tail -5 || echo 'No errors found'

echo ''
echo '=== 16. WBOM logs (errors) ==='
docker logs fazle-wbom 2>&1 | grep -i 'error\|traceback\|exception' | tail -5 || echo 'No errors found'

echo ''
echo '=== ALL 16 TESTS COMPLETE ==='
