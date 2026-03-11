# Secrets Rotation Guide

## Overview

The platform manages **11 secrets** via `scripts/gen-secrets.sh`. All secrets
are stored in a single `.env` file (default: project root `.env`) with
`chmod 600` permissions.

The script **never prints secret values** — only variable names are logged.

## Managed Secrets

| Variable | Purpose | Rotation Impact |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL database password | Requires DB password update + service restart |
| `REDIS_PASSWORD` | Redis auth password | Requires all Redis clients to restart |
| `MINIO_SECRET_KEY` | MinIO object storage secret | Requires MinIO + dependent services restart |
| `OSS_JWT_SECRET` | Dograh platform JWT signing | Invalidates all active Dograh sessions |
| `LIVEKIT_API_KEY` | LiveKit API authentication key | Breaks active voice calls; restart all voice services |
| `LIVEKIT_API_SECRET` | LiveKit API authentication secret | Breaks active voice calls; restart all voice services |
| `TURN_SECRET` | TURN/STUN shared secret with LiveKit | Breaks NAT traversal; restart LiveKit + Coturn |
| `FAZLE_API_KEY` | Fazle service-to-service auth | Requires all Fazle services restart |
| `FAZLE_JWT_SECRET` | Fazle user JWT signing | **Invalidates all active Fazle user sessions** |
| `NEXTAUTH_SECRET` | NextAuth.js session encryption | **Invalidates all active Fazle UI sessions** |
| `GRAFANA_PASSWORD` | Grafana admin password | Only affects Grafana login |

## Commands

### Check all secrets are present and non-placeholder

```bash
./scripts/gen-secrets.sh --check
```

Returns exit code 0 if all 11 secrets exist and are not placeholder values.
Returns exit code 1 with details on any missing/placeholder secrets.

### Generate missing secrets (first-time setup)

```bash
cp .env.example .env
./scripts/gen-secrets.sh
```

Only generates values for vars that are missing or still have `CHANGE_ME_*`
placeholder values. Existing real secrets are preserved.

### Rotate all secrets

```bash
./scripts/gen-secrets.sh --rotate-all
```

**Warning:** This regenerates every managed secret. All active sessions will be
invalidated and all services must be restarted:

```bash
docker compose down
./scripts/gen-secrets.sh --rotate-all
docker compose up -d
```

### Rotate specific secrets

```bash
./scripts/gen-secrets.sh --rotate FAZLE_JWT_SECRET,NEXTAUTH_SECRET
```

Only rotates the named secrets. Other secrets remain unchanged.

**Common rotation scenarios:**

| Scenario | Command |
|---|---|
| Suspected JWT leak | `--rotate FAZLE_JWT_SECRET,NEXTAUTH_SECRET,OSS_JWT_SECRET` |
| Rotate DB credentials | `--rotate POSTGRES_PASSWORD` (then restart all DB-connected services) |
| Rotate API keys only | `--rotate FAZLE_API_KEY,LIVEKIT_API_KEY,LIVEKIT_API_SECRET` |
| Grafana password only | `--rotate GRAFANA_PASSWORD` |

### Use a custom env file

```bash
./scripts/gen-secrets.sh --env-file /path/to/.env
```

## After Rotation

1. Restart affected services:
   ```bash
   docker compose up -d --force-recreate
   ```
2. Verify health:
   ```bash
   docker compose ps
   curl -sf https://fazle.iamazim.com/health
   curl -sf https://iamazim.com/api/v1/health
   ```
3. Re-login to any invalidated sessions (Fazle UI, Dograh UI, Grafana).

## Security Notes

- The `.env` file is created with `chmod 600` (owner read/write only).
- Secret values are never echoed to stdout or stderr.
- The script uses `set -euo pipefail` and strict IFS.
- Atomic writes: a temp file is written first, then `mv`'d into place.
- Secrets are generated via `openssl rand` with alphanumeric filtering.
