#!/bin/bash
echo "=== Users table columns ==="
docker exec ai-postgres psql -U postgres -c "SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position;"

echo ""
echo "=== User accounts ==="
docker exec ai-postgres psql -U postgres -c "SELECT id, email, role FROM users LIMIT 5;"
