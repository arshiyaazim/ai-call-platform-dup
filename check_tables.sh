#!/bin/bash
echo "=== Tables with transaction/program/payment/ops ==="
docker exec ai-postgres psql -U postgres -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE '%transaction%' OR tablename LIKE '%program%' OR tablename LIKE '%payment%' OR tablename LIKE '%ops%' OR tablename LIKE '%escort%') ORDER BY tablename;"

echo ""
echo "=== ALL wbom_ tables ==="
docker exec ai-postgres psql -U postgres -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'wbom_%' ORDER BY tablename;"

echo ""
echo "=== ALL _legacy_ tables ==="
docker exec ai-postgres psql -U postgres -t -A -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE '_legacy_%' ORDER BY tablename;"

echo ""
echo "=== ops_payments columns (if exists) ==="
docker exec ai-postgres psql -U postgres -t -A -c "SELECT column_name || ' (' || data_type || ')' FROM information_schema.columns WHERE table_name='ops_payments' ORDER BY ordinal_position;" 2>/dev/null || echo "NOT FOUND"

echo ""
echo "=== escort_duty_programs columns (if exists) ==="
docker exec ai-postgres psql -U postgres -t -A -c "SELECT column_name || ' (' || data_type || ')' FROM information_schema.columns WHERE table_name='escort_duty_programs' ORDER BY ordinal_position;" 2>/dev/null || echo "NOT FOUND"
