#!/bin/bash
echo "--- wbom_escort_programs ---"
docker exec ai-postgres psql -U postgres -t -A -c "SELECT column_name || ' (' || data_type || CASE WHEN character_maximum_length IS NOT NULL THEN '(' || character_maximum_length || ')' ELSE '' END || CASE WHEN is_nullable='NO' THEN ', NOT NULL' ELSE '' END || ')' FROM information_schema.columns WHERE table_name='wbom_escort_programs' ORDER BY ordinal_position;"

echo ""
echo "--- wbom_cash_transactions ---"
docker exec ai-postgres psql -U postgres -t -A -c "SELECT column_name || ' (' || data_type || CASE WHEN character_maximum_length IS NOT NULL THEN '(' || character_maximum_length || ')' ELSE '' END || CASE WHEN is_nullable='NO' THEN ', NOT NULL' ELSE '' END || ')' FROM information_schema.columns WHERE table_name='wbom_cash_transactions' ORDER BY ordinal_position;"

echo ""
echo "Row counts:"
echo -n "wbom_escort_programs: "; docker exec ai-postgres psql -U postgres -t -A -c "SELECT count(*) FROM wbom_escort_programs;"
echo -n "wbom_cash_transactions: "; docker exec ai-postgres psql -U postgres -t -A -c "SELECT count(*) FROM wbom_cash_transactions;"
