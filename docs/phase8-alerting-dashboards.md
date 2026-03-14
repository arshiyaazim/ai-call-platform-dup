# Phase 8 — Alerting & Dashboards

## Overview

Phase 8 adds structured Prometheus alert rules and a pre-built Grafana
dashboard to the monitoring stack that was wired up in earlier phases.
Everything provisions automatically on `docker compose up`; no manual
Grafana UI steps are required.

---

## Files Added / Changed

| Path | Purpose |
|------|---------|
| `configs/prometheus/alerts/infra.yml` | Infrastructure alert rules (disk, memory, CPU, container restarts, service availability) |
| `configs/prometheus/alerts/app.yml` | Application-layer alert rules (Fazle API health, Loki, TLS cert expiry) |
| `configs/prometheus/prometheus.yml` | Updated to load `rule_files` from `/etc/prometheus/alerts/*.yml` |
| `docker-compose.yaml` | Added `configs/prometheus/alerts` volume mount to `prometheus` service |
| `configs/grafana/provisioning/dashboards/dashboards.yml` | Grafana file-based dashboard provisioning config |
| `configs/grafana/provisioning/dashboards/platform-overview.json` | Pre-built platform overview dashboard |
| `scripts/vps/monitoring_smoke.sh` | Smoke-test script; verifies every monitoring service end-to-end |

---

## Alert Rules

### Infrastructure (`configs/prometheus/alerts/infra.yml`)

| Alert | Threshold | Severity |
|-------|-----------|----------|
| `DiskUsageWarning` | `/` filesystem < 20 % free for 5 m | warning |
| `DiskUsageCritical` | `/` filesystem < 10 % free for 2 m | critical |
| `HighMemoryUsage` | RAM usage > 90 % for 5 m | warning |
| `CriticalMemoryUsage` | RAM usage > 95 % for 2 m | critical |
| `HighCPUUsage` | CPU utilisation > 85 % for 10 m | warning |
| `ContainerRestarting` | > 2 restarts in 15 m | warning |
| `ContainerCrashLoop` | > 5 restarts in 1 h | critical |
| `ServiceDown` | Prometheus target unreachable for 2 m | critical |
| `PrometheusConfigReloadFailed` | Config reload unsuccessful for 5 m | critical |

### Application (`configs/prometheus/alerts/app.yml`)

| Alert | Threshold | Severity |
|-------|-----------|----------|
| `FazleAPIDown` | `fazle-api` scrape target down for 2 m | critical |
| `FazleAPIHighErrorRate` | HTTP 5xx > 5 % of requests for 5 m | warning |
| `FazleAPISlowResponses` | p95 latency > 2 s for 5 m | warning |
| `LokiDown` | Loki scrape target down for 2 m | critical |
| `LokiHighIngestionErrors` | Chunk flush errors > 0.1/s for 5 m | warning |
| `CertificateExpiringSoon` | TLS cert expires in < 14 days | warning |
| `CertificateExpiringCritical` | TLS cert expires in < 3 days | critical |

---

## Grafana Dashboard

The **Platform Overview** dashboard (`uid: platform-overview-v1`) is
provisioned automatically into the _AI Call Platform_ folder.

### Panels

| Panel | Type | Data Source |
|-------|------|-------------|
| CPU Usage % | Gauge | Prometheus |
| Memory Usage % | Gauge | Prometheus |
| Disk Usage % (/) | Gauge | Prometheus |
| Network I/O (eth0) | Time series | Prometheus |
| Container Resource Usage | Table | Prometheus |
| Fazle API — Request Rate | Time series | Prometheus |
| Fazle API — Latency (p50/p95/p99) | Time series | Prometheus |
| Recent Errors (all services) | Logs | Loki |

Default time range: last 3 hours, auto-refresh every 30 s.

---

## Deploying on the VPS

```bash
# 1. Pull latest changes
cd /opt/ai-call-platform
git pull

# 2. Reload Prometheus config without downtime
docker compose exec prometheus \
  wget -q --post-data '' -O - http://localhost:9090/-/reload

# 3. Or do a full restart of monitoring services
docker compose up -d --no-deps prometheus grafana

# 4. Verify everything is healthy
bash scripts/vps/monitoring_smoke.sh
```

---

## Monitoring Smoke Test

```
scripts/vps/monitoring_smoke.sh
```

The script checks:
1. All six monitoring containers are **running**
2. Prometheus, Grafana, and Loki pass their **healthchecks**
3. Prometheus `/-/healthy` and `/-/ready` endpoints respond OK
4. Alert rule groups are loaded (count > 0)
5. Grafana `/api/health` responds `ok`
6. Loki `/ready` endpoint responds from inside its container
7. Node Exporter and cAdvisor are reachable from the Prometheus container
8. All Prometheus scrape targets report **UP**

Exit code `0` = all checks pass. Exit code equals the number of failures.

---

## Grafana Alert Notifications (Future)

To receive alert notifications (e.g. email, Slack, PagerDuty):

1. Open Grafana → **Alerting** → **Contact points**
2. Add a contact point for your channel
3. Open **Notification policies** and bind alerts to the contact point

Alternatively provision contact points via
`configs/grafana/provisioning/alerting/` (Grafana 9+ provisioning format).

---

## Verification Checklist

```
[ ] docker compose up -d → no errors for prometheus / grafana
[ ] curl -s http://127.0.0.1:9090/api/v1/rules | python3 -m json.tool | grep "name"
    → shows infra and app rule groups
[ ] Grafana → Dashboards → AI Call Platform → Platform Overview loads
[ ] bash scripts/vps/monitoring_smoke.sh → ALL CHECKS PASSED
```
