#!/bin/bash
# Fix WBOM 403: Remove direct nginx→WBOM:9900 proxy, let requests go through API:8100
# The API's wbom_routes.py adds the X-INTERNAL-KEY header

set -e
PASS="$1"

fix_config() {
    local file="$1"
    echo "=== Fixing $file ==="
    
    # Use sed to comment out the WBOM location block
    # Match from "# ── WBOM" comment through the closing "}"
    echo "$PASS" | sudo -S sed -i.bak \
        '/# .*WBOM.*routes/,/^    }/ {
            s/^/# DISABLED: /
        }' "$file"
    
    echo "Done: $file"
}

# Fix fazle.iamazim.com.conf
fix_config /etc/nginx/sites-available/fazle.iamazim.com.conf

# Fix iamazim.com.conf
fix_config /etc/nginx/sites-available/iamazim.com.conf

# Fix api.iamazim.com.conf 
fix_config /etc/nginx/sites-available/api.iamazim.com.conf

# Verify configs
echo ""
echo "=== Testing nginx config ==="
echo "$PASS" | sudo -S nginx -t 2>&1

echo ""
echo "=== Reloading nginx ==="
echo "$PASS" | sudo -S nginx -s reload 2>&1

echo ""
echo "=== Verify WBOM blocks are commented ==="
grep -n "DISABLED.*WBOM\|DISABLED.*wbom\|DISABLED.*9900" /etc/nginx/sites-available/fazle.iamazim.com.conf || echo "No WBOM in fazle"
echo "---"
grep -n "DISABLED.*WBOM\|DISABLED.*wbom\|DISABLED.*9900" /etc/nginx/sites-available/iamazim.com.conf || echo "No WBOM in iamazim"
echo "---"
grep -n "DISABLED.*WBOM\|DISABLED.*wbom\|DISABLED.*9900" /etc/nginx/sites-available/api.iamazim.com.conf || echo "No WBOM in api"

echo ""
echo "=== DONE ==="
