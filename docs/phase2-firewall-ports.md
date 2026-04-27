# Phase 2 — Firewall & Port Security

VPS: `5.189.131.48` · Domain: `iamazim.com` · OS: Ubuntu + Docker Compose V2

## Overview

Two layers of firewall protection:

| Layer | Protects | Tool |
|-------|----------|------|
| **UFW** | Host-level INPUT chain (SSH, Nginx, non-Docker) | `scripts/vps/ufw_apply.sh` |
| **DOCKER-USER** | Docker-published ports (FORWARD chain) | `scripts/vps/docker_user_firewall.sh` |

> **Why both?** Docker inserts its own iptables rules in the FORWARD chain, bypassing UFW entirely. A service published on `0.0.0.0:PORT` is reachable from the internet regardless of UFW. The DOCKER-USER chain is Docker's official hook for user-defined filtering before Docker's own rules.

## Allowed External Ports

| Port | Protocol | Service |
|------|----------|---------|
| 22 | TCP | SSH (rate-limited) |
| 80 | TCP | HTTP → Nginx |
| 443 | TCP | HTTPS → Nginx |
| 3478 | TCP+UDP | STUN/TURN → Coturn |
| 5349 | TCP+UDP | TURN TLS → Coturn |
| 7881 | TCP | LiveKit RTC direct |
| 49152–49252 | UDP | Coturn relay range |
| 50000–50200 | UDP | LiveKit WebRTC media |

**All other inbound ports are blocked.**

## Docker Compose Port Audit

All internal services are already bound to `127.0.0.1` (no changes needed):

| Service | Binding | Status |
|---------|---------|--------|
| livekit HTTP | `127.0.0.1:7880` | ✓ Internal |
| dograh-api | `127.0.0.1:8000` | ✓ Internal |
| dograh-ui | `127.0.0.1:3010` | ✓ Internal |
| fazle-api | `127.0.0.1:8100` | ✓ Internal |
| fazle-ui | `127.0.0.1:3020` | ✓ Internal |
| grafana | `127.0.0.1:3030` | ✓ Internal |
| livekit RTC | `0.0.0.0:7881` | ✓ Required public |
| livekit UDP | `0.0.0.0:50000-50200` | ✓ Required public |
| coturn | `0.0.0.0:3478,5349,relay` | ✓ Required public |

PostgreSQL, Redis, MinIO, Qdrant, Ollama, Prometheus, Loki — **no port mappings** (Docker-internal only).

---

## Apply Steps (on VPS)

### Step 1: Upload code

```bash
cd /path/to/vps-deploy
git pull origin main
chmod +x scripts/vps/*.sh
```

### Step 2: Apply UFW rules

```bash
sudo ./scripts/vps/ufw_apply.sh
```

### Step 3: Apply DOCKER-USER iptables rules

```bash
sudo ./scripts/vps/docker_user_firewall.sh
```

### Step 4: Install systemd service (persist after reboot)

```bash
sudo ./scripts/vps/install_docker_user_firewall_service.sh
sudo systemctl start docker-user-firewall
```

### Step 5: Run port audit

```bash
sudo ./scripts/vps/ports_audit.sh
```

Audit exits 0 if all bindings match the allowlist. Non-zero means unexpected exposures were found.

---

## Verification Commands

### UFW Status

```bash
sudo ufw status verbose
```

Expected output includes:
```
Status: active
Default: deny (incoming), allow (outgoing), disabled (routed)

To                         Action      From
--                         ------      ----
80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
22/tcp                     LIMIT IN    Anywhere
3478/tcp                   ALLOW IN    Anywhere
3478/udp                   ALLOW IN    Anywhere
5349/tcp                   ALLOW IN    Anywhere
5349/udp                   ALLOW IN    Anywhere
7881/tcp                   ALLOW IN    Anywhere
49152:49252/udp            ALLOW IN    Anywhere
50000:50200/udp            ALLOW IN    Anywhere
```

### DOCKER-USER iptables

```bash
sudo iptables -S DOCKER-USER
```

Should show rules with `iamazim-docker-user` comment tags — allowlist followed by a final DROP for new connections.

### Listening Ports

```bash
sudo ss -lntup
```

### Docker Port Mappings

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

### External Port Scan (from laptop or another server)

TCP ports:
```bash
nmap -Pn -p 22,80,443,3478,5349,7881 iamazim.com
```

UDP ports (slower):
```bash
nmap -Pn -sU -p 3478,5349 iamazim.com
```

Targeted UDP range check (optional, slow):
```bash
nmap -Pn -sU -p 49152-49155 iamazim.com
```

Verify a blocked port is actually blocked:
```bash
# Should timeout / show filtered:
nmap -Pn -p 5432,6379,9090,3000 iamazim.com
```

---

## TURN/TLS Connectivity Checks

### TCP reachability

```bash
nc -vz iamazim.com 3478
nc -vz iamazim.com 7881
```

### TLS handshake (TURN TLS on port 5349)

```bash
openssl s_client -connect iamazim.com:5349 -servername iamazim.com -brief
```

Expected: TLS handshake succeeds, shows certificate info for `iamazim.com`.

### Full STUN/TURN test (requires coturn's turnutils — optional)

```bash
# Install if needed: sudo apt-get install coturn-utils
# Basic STUN binding test:
turnutils_stunclient iamazim.com

# Full TURN allocation test (requires valid credentials):
turnutils_uclient -T -p 5349 iamazim.com
```

> **Note:** The TURN allocation test needs valid credentials configured in Coturn. The STUN binding test works without auth.

---

## Systemd Service Management

```bash
# Status
sudo systemctl status docker-user-firewall

# Re-apply rules manually
sudo systemctl restart docker-user-firewall

# View logs
journalctl -u docker-user-firewall --no-pager -l

# Disable (stop on next boot)
sudo systemctl disable docker-user-firewall
```

---

## Acceptance Criteria

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | UFW active | `sudo ufw status` | Status: active |
| 2 | UFW defaults | `sudo ufw status verbose` | deny incoming, allow outgoing |
| 3 | SSH rate-limited | `sudo ufw status` | 22/tcp LIMIT |
| 4 | DOCKER-USER chain | `sudo iptables -S DOCKER-USER` | Rules with `iamazim-docker-user` tag |
| 5 | DROP rule present | `sudo iptables -S DOCKER-USER \| tail -1` | `-j DROP` for NEW non-local |
| 6 | Port audit clean | `sudo ./scripts/vps/ports_audit.sh` | Exit code 0 |
| 7 | No public Postgres | `nmap -Pn -p 5432 iamazim.com` | filtered/closed |
| 8 | No public Redis | `nmap -Pn -p 6379 iamazim.com` | filtered/closed |
| 9 | No public Grafana | `nmap -Pn -p 3000 iamazim.com` | filtered/closed |
| 10 | HTTPS works | `curl -sI https://iamazim.com` | HTTP/2 200 |
| 11 | TURN TLS handshake | `openssl s_client -connect iamazim.com:5349 ...` | TLS OK |
| 12 | Systemd service | `systemctl is-enabled docker-user-firewall` | enabled |
| 13 | Survives reboot | Reboot VPS, re-run port audit | Exit code 0 |

---

## Troubleshooting

**Locked out of SSH?**
Contabo provides a VNC console in their dashboard. Use it to run `sudo ufw allow 22/tcp && sudo ufw enable`.

**SSH login fails / root login denied?**
Root SSH login is disabled by the SSH hardening script. Always login as the deploy user:
```bash
ssh azim@5.189.131.48
# You will land in /home/azim — the project is at /home/azim/ai-call-platform
cd /home/azim/ai-call-platform
```
If you haven't applied SSH hardening yet, run:
```bash
sudo bash scripts/vps/ssh_hardening.sh
```
The script automatically fixes `/home/azim/.ssh` (700) and `authorized_keys` (600) permissions, which are the most common cause of key-based login failures. It also requires at least one public key to already be present in `authorized_keys` before it disables password auth. Use `--dry-run` to preview changes without applying them.

**Docker containers can't reach the internet?**
The DOCKER-USER DROP rule only targets NEW inbound from non-internal interfaces. If outbound is broken, check the rule order — ESTABLISHED,RELATED must be first.

**Rules lost after reboot?**
Ensure the systemd service is installed and enabled:
```bash
sudo systemctl is-enabled docker-user-firewall
```

**Need to temporarily allow a port?**
```bash
sudo ufw allow <port>/tcp
# For Docker-published ports, also add to DOCKER-USER or re-run
# docker_user_firewall.sh after editing the allowlist
```
