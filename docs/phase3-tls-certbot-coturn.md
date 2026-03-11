# Phase 3 — TLS, Certbot & Coturn Certificate Management

Covers Let's Encrypt certificate lifecycle, SAN validation, TURN TLS verification,
auto-renewal with deploy hooks, and optional Prometheus expiry monitoring.

---

## Overview

| Layer | What | Script |
|-------|------|--------|
| Certificate status | Expiry, issuer, subject, days remaining | `scripts/vps/cert_status.sh` |
| SAN validation | Verify all production hostnames in cert | `scripts/vps/cert_san_check.sh` |
| TURN TLS check | TLS handshake on port 5349 | `scripts/vps/turn_tls_check.sh` |
| Deploy hook | Reload Nginx + restart Coturn on renewal | `ops/letsencrypt/deploy-hook-reload.sh` |
| Hook installer | Install deploy hook into certbot paths | `scripts/vps/install_certbot_deploy_hook.sh` |
| Expiry metric | Prometheus textfile metric (optional) | `scripts/vps/cert_expiry_metric.sh` |

---

## A) Quick Status Checks

Run on VPS after `git pull` and `chmod +x scripts/vps/*.sh`:

```bash
# 1. Certificate expiry and basic info
sudo ./scripts/vps/cert_status.sh

# 2. SAN list covers all required domains
sudo ./scripts/vps/cert_san_check.sh

# 3. TURN TLS handshake on port 5349
sudo ./scripts/vps/turn_tls_check.sh
```

All three scripts exit non-zero on failure. Expected output on a healthy system:

- `cert_status.sh` — shows ≥14 days remaining, Subject CN, Issuer (Let's Encrypt)
- `cert_san_check.sh` — all 4 required domains show `OK`; `turn.iamazim.com` checked only if DNS resolves
- `turn_tls_check.sh` — TCP connect OK, TLS handshake OK, verify code 0, cert expiry shown

---

## B) Verify Renewal Automation

### Check certbot timer

```bash
systemctl list-timers | grep certbot
```

Expected: `certbot.timer` active, runs twice daily.

If not found:

```bash
sudo systemctl enable --now certbot.timer
```

Or verify cron-based renewal:

```bash
crontab -l | grep certbot
```

### Test renewal (dry-run)

```bash
sudo certbot renew --dry-run
```

This does NOT issue a real certificate — it validates the renewal pipeline works.

---

## C) Install Deploy Hook

The deploy hook ensures Nginx and Coturn pick up renewed certificates automatically.

### What the hook does

1. **Reload Nginx** — `systemctl reload nginx` (host) or `docker exec nginx -s reload` (container)
2. **Restart Coturn** — `docker compose restart coturn` (cert is bind-mounted, restart re-reads it)
3. **Log** — writes to `/var/log/iamazim-certbot-deploy.log` and syslog

### Install

```bash
# Install the hook (does not trigger renewal)
sudo ./scripts/vps/install_certbot_deploy_hook.sh --install-only

# Install + run certbot dry-run to validate
sudo ./scripts/vps/install_certbot_deploy_hook.sh --dry-run
```

### Verify installation

```bash
ls -la /etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh
cat /etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh | head -5
```

### Why Coturn needs a restart

Coturn reads TLS certificates at startup. The Docker volume mount
(`/etc/letsencrypt/live/iamazim.com/fullchain.pem:/etc/coturn/certs/fullchain.pem:ro`)
reflects renewed files on disk, but Coturn's in-memory copy is stale.
A container restart forces Coturn to re-read the cert files.

### Note on existing cron

`scripts/setup-ssl.sh` installs a cron entry:
```
0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'
```

This **only reloads Nginx** and does NOT restart Coturn. The new deploy hook
in `/etc/letsencrypt/renewal-hooks/deploy/` is called automatically by certbot
regardless of how renewal is triggered (timer, cron, or manual), so it covers
the Coturn gap. You may optionally clean up the old `--deploy-hook` cron flag
since the hook directory approach is the recommended certbot pattern.

---

## D) If SANs Are Missing

### Check current SANs

```bash
sudo ./scripts/vps/cert_san_check.sh
```

### Required SANs

| Domain | Used By |
|--------|---------|
| `iamazim.com` | Main site / Dograh UI |
| `api.iamazim.com` | Dograh API |
| `livekit.iamazim.com` | LiveKit signaling |
| `fazle.iamazim.com` | Fazle API + UI |
| `turn.iamazim.com` | Coturn realm (checked if DNS resolves) |

### Re-issue with expanded SANs

If `cert_san_check.sh` reports missing SANs:

```bash
sudo certbot certonly --nginx \
  --cert-name iamazim.com \
  -d iamazim.com \
  -d api.iamazim.com \
  -d livekit.iamazim.com \
  -d fazle.iamazim.com \
  -d turn.iamazim.com \
  --expand
```

**Prerequisites:**
- All listed domains must have DNS A records pointing to `5.189.131.48`
- Nginx must be running with server blocks for all domains (for HTTP-01 challenge)
- If `turn.iamazim.com` has no Nginx server block, either:
  - Add a minimal Nginx config for it, or
  - Use `--preferred-challenges dns` with a DNS plugin instead

**After re-issue:**

```bash
# Confirm new SANs
sudo ./scripts/vps/cert_san_check.sh

# Restart Coturn to pick up new cert
docker compose restart coturn

# Verify TURN TLS handshake
sudo ./scripts/vps/turn_tls_check.sh
```

---

## E) Optional: Prometheus Certificate Expiry Metric

### Generate metric (stdout)

```bash
sudo ./scripts/vps/cert_expiry_metric.sh
```

Output:
```
# HELP iamazim_tls_cert_days_remaining Days until TLS certificate expires.
# TYPE iamazim_tls_cert_days_remaining gauge
iamazim_tls_cert_days_remaining{domain="iamazim.com"} 42
```

### Write to textfile collector

```bash
sudo ./scripts/vps/cert_expiry_metric.sh \
  --out /var/lib/node_exporter/textfile_collector/iamazim_tls_cert.prom
```

### Enable textfile collector on node-exporter

#### If node-exporter runs on the host:

Ensure the service starts with:
```
--collector.textfile.directory=/var/lib/node_exporter/textfile_collector
```

Then create a cron to refresh the metric daily:
```bash
sudo mkdir -p /var/lib/node_exporter/textfile_collector

# Add cron (run twice daily, after certbot's typical renewal window)
(crontab -l 2>/dev/null; echo '30 4,16 * * * /opt/vps-deploy/scripts/vps/cert_expiry_metric.sh --out /var/lib/node_exporter/textfile_collector/iamazim_tls_cert.prom') | sudo crontab -
```

#### If node-exporter is a Docker container (current setup):

The current `docker-compose.yaml` node-exporter does **not** have the textfile
collector enabled. To opt in, you would add:

```yaml
# In docker-compose.yaml, under node-exporter:
    command:
      - "--path.rootfs=/host"
      - "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($|/)"
      - "--collector.textfile.directory=/host/var/lib/node_exporter/textfile_collector"
```

And ensure the host directory exists:
```bash
sudo mkdir -p /var/lib/node_exporter/textfile_collector
```

**This compose change is NOT applied automatically in Phase 3.** Apply it
manually only if you want Prometheus-based cert monitoring.

### Grafana alert (optional)

Once the metric is scraped, add a Grafana alert rule:

- Expression: `iamazim_tls_cert_days_remaining < 14`
- Alert name: `TLS Certificate Expiring Soon`
- Notification channel: your preferred (email, Slack, etc.)

---

## F) Acceptance Criteria

| # | Criterion | Verify Command |
|---|-----------|----------------|
| 1 | Certificate exists and is readable | `sudo ./scripts/vps/cert_status.sh` |
| 2 | Certificate expires in > 14 days | Same as above (exit code 0) |
| 3 | All required SANs present | `sudo ./scripts/vps/cert_san_check.sh` |
| 4 | TURN TLS handshake succeeds on 5349 | `sudo ./scripts/vps/turn_tls_check.sh` |
| 5 | Certbot renewal is scheduled | `systemctl list-timers \| grep certbot` |
| 6 | Deploy hook is installed and executable | `ls -la /etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh` |
| 7 | Deploy hook reloads Nginx | Check `/var/log/iamazim-certbot-deploy.log` after renewal |
| 8 | Deploy hook restarts Coturn | Same log file |
| 9 | Dry-run renewal succeeds | `sudo certbot renew --dry-run` |
| 10 | cert_expiry_metric.sh runs without error | `sudo ./scripts/vps/cert_expiry_metric.sh` |

---

## G) Troubleshooting

### Certbot renewal fails

```bash
# Check certbot logs
sudo cat /var/log/letsencrypt/letsencrypt.log | tail -50

# Verify Nginx is running (needed for HTTP-01 challenge)
systemctl status nginx

# Verify port 80 is open
sudo ss -lntp | grep ':80'
```

### Coturn TLS handshake fails

```bash
# Check Coturn is running
docker ps | grep coturn

# Check Coturn logs for cert errors
docker logs coturn --tail 50 2>&1 | grep -iE 'cert|tls|perm|denied'

# Verify cert files are readable inside container
docker exec coturn ls -la /etc/coturn/certs/

# Restart Coturn after fixing
docker compose restart coturn
```

### Certificate file permission issues

Coturn runs as `user: root` in docker-compose, so permission issues are unlikely
for the bind-mounted cert files. If they occur:

```bash
# Check host permissions
ls -la /etc/letsencrypt/live/iamazim.com/
ls -la /etc/letsencrypt/archive/iamazim.com/

# The live/ directory contains symlinks to archive/
# Ensure archive files are readable
sudo chmod 644 /etc/letsencrypt/archive/iamazim.com/fullchain*.pem
sudo chmod 600 /etc/letsencrypt/archive/iamazim.com/privkey*.pem
```

### Deploy hook not running after renewal

```bash
# Verify hook is in the correct path
ls -la /etc/letsencrypt/renewal-hooks/deploy/

# Test the hook manually (simulates renewal)
sudo RENEWED_DOMAINS="iamazim.com" /etc/letsencrypt/renewal-hooks/deploy/iamazim-reload.sh

# Check hook log
cat /var/log/iamazim-certbot-deploy.log
```

---

## Files Added in Phase 3

| File | Purpose |
|------|---------|
| `scripts/vps/cert_status.sh` | Certificate expiry and info check |
| `scripts/vps/cert_san_check.sh` | SAN list validator |
| `scripts/vps/turn_tls_check.sh` | TURN TLS handshake check on 5349 |
| `ops/letsencrypt/deploy-hook-reload.sh` | Deploy hook template (Nginx + Coturn) |
| `scripts/vps/install_certbot_deploy_hook.sh` | Hook installer with dry-run flag |
| `scripts/vps/cert_expiry_metric.sh` | Prometheus textfile metric (optional) |
| `docs/phase3-tls-certbot-coturn.md` | This documentation |
