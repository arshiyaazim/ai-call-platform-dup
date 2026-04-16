import re

with open('/etc/nginx/sites-enabled/fazle.iamazim.com.conf') as f:
    c = f.read()

wbom_block = """    # ── WBOM API routes (before general fazle catch-all) ────
    location /api/fazle/wbom/ {
        limit_req zone=fazle_limit burst=30 nodelay;

        proxy_pass http://127.0.0.1:9900/api/wbom/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

"""

marker = '    # ── Fazle API routes'
if 'WBOM API routes' not in c:
    c = c.replace(marker, wbom_block + marker)
    with open('/tmp/fazle-nginx-new.conf', 'w') as f:
        f.write(c)
    print('PATCHED - written to /tmp/fazle-nginx-new.conf')
else:
    print('ALREADY_PATCHED')
