#!/bin/bash
echo "=========================================="
echo "BACKEND DB TABLE COLUMNS"
echo "=========================================="

for TBL in wbom_employees wbom_escort_duty_programs wbom_transactions wbom_salary_records wbom_attendance wbom_contacts wbom_whatsapp_messages; do
  echo ""
  echo "--- $TBL ---"
  docker exec ai-postgres psql -U postgres -t -A -c "
    SELECT column_name || ' (' || data_type || 
      CASE WHEN character_maximum_length IS NOT NULL THEN '(' || character_maximum_length || ')' ELSE '' END ||
      CASE WHEN is_nullable='NO' THEN ', NOT NULL' ELSE '' END || ')'
    FROM information_schema.columns 
    WHERE table_name='$TBL' 
    ORDER BY ordinal_position;"
done

echo ""
echo "=========================================="
echo "ROW COUNTS"
echo "=========================================="
for TBL in wbom_employees wbom_escort_duty_programs wbom_transactions wbom_salary_records wbom_attendance wbom_contacts wbom_whatsapp_messages; do
  CNT=$(docker exec ai-postgres psql -U postgres -t -A -c "SELECT count(*) FROM $TBL;" 2>/dev/null || echo "TABLE NOT FOUND")
  echo "$TBL: $CNT"
done
