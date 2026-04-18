#!/bin/bash
echo "=== User accounts ==="
docker exec ai-postgres psql -U postgres -c "SELECT id, email, name, role FROM users LIMIT 5;"
