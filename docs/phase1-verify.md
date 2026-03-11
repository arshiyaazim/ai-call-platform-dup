# Phase 1 Verification Guide

Verification steps for Phase 1 (P0 critical fixes):
1. Secret generation/rotation — `gen-secrets.sh`
2. Content moderation fail-closed for child accounts — `safety.py`

---

## 1. Local Verification

### 1.1 Validate gen-secrets.sh syntax

```bash
# Bash syntax check
bash -n scripts/gen-secrets.sh

# ShellCheck (if installed)
shellcheck scripts/gen-secrets.sh
```

### 1.2 Test gen-secrets.sh with a temporary env file

```bash
# Copy example to a temp file
cp .env.example /tmp/test-phase1.env

# Generate secrets into the temp file
./scripts/gen-secrets.sh --env-file /tmp/test-phase1.env

# Validate all secrets are set
./scripts/gen-secrets.sh --env-file /tmp/test-phase1.env --check

# Verify no CHANGE_ME values remain in managed secrets
grep -c 'CHANGE_ME' /tmp/test-phase1.env  # should only match non-managed vars like OPENAI_API_KEY

# Verify permissions
stat -c '%a' /tmp/test-phase1.env   # should show 600

# Test rotation of specific secrets
./scripts/gen-secrets.sh --env-file /tmp/test-phase1.env --rotate GRAFANA_PASSWORD

# Test rotate-all
./scripts/gen-secrets.sh --env-file /tmp/test-phase1.env --rotate-all

# Clean up
rm -f /tmp/test-phase1.env
```

### 1.3 Run safety module tests

```bash
# Install test dependencies (one-time)
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/test_safety_fail_closed.py -v
```

Expected output: **13 tests passed**, including:
- `test_child_daughter_blocked_on_api_timeout` — PASS
- `test_child_son_blocked_on_api_timeout` — PASS
- `test_child_generic_blocked_on_api_error` — PASS
- `test_child_blocked_on_network_error` — PASS
- `test_adult_allowed_on_api_timeout` — PASS
- `test_adult_self_allowed_on_api_error` — PASS
- `test_adult_no_relationship_allowed_on_api_error` — PASS
- `test_safe_content_passes` — PASS
- `test_unsafe_content_blocked_for_child` — PASS
- `test_empty_text_passes` — PASS
- `test_no_api_key_passes` — PASS
- `test_child_thresholds_stricter_than_default` — PASS

---

## 2. VPS Deploy Verification

### 2.1 Deploy

```bash
# SSH to VPS
ssh root@5.189.131.48

# Pull latest code
cd /root/ai-call-platform
git pull origin main

# Generate/verify secrets
./scripts/gen-secrets.sh --check        # verify current secrets
# If any are missing:
./scripts/gen-secrets.sh                # generate only missing

# Deploy
docker compose up -d --build
```

### 2.2 Check container health

```bash
docker compose ps
# All services should show "healthy" or "running"
```

### 2.3 Verify health endpoints

```bash
# Fazle API
curl -sf https://fazle.iamazim.com/health && echo "FAZLE OK"

# Dograh API
curl -sf https://iamazim.com/api/v1/health && echo "DOGRAH OK"
```

### 2.4 Verify child fail-closed behavior on VPS

Run inside the fazle-brain container (no external API calls needed):

```bash
docker exec fazle-brain python -c "
import asyncio
from safety import check_content, CHILD_BLOCKED_RESPONSE

async def verify():
    # Test 1: child account + API error => must block
    result = await check_content(
        text='Hello',
        openai_api_key='sk-invalid-key-triggers-error',
        relationship='daughter',
    )
    assert result['safe'] is False, f'FAIL: child should be blocked, got {result}'
    assert result['reason'] == 'moderation_unavailable'
    assert result['blocked_reply'] == CHILD_BLOCKED_RESPONSE
    print('PASS: child account blocked when moderation unavailable')

    # Test 2: adult account + API error => must allow
    result = await check_content(
        text='Hello',
        openai_api_key='sk-invalid-key-triggers-error',
        relationship='wife',
    )
    assert result['safe'] is True, f'FAIL: adult should pass, got {result}'
    print('PASS: adult account allowed when moderation unavailable')

    print('ALL CHECKS PASSED')

asyncio.run(verify())
"
```

---

## 3. Acceptance Criteria Checklist

| # | Criterion | Verify Command | Expected |
|---|-----------|---------------|----------|
| 1 | gen-secrets.sh generates all 11 managed secrets | `./scripts/gen-secrets.sh --env-file /tmp/t.env && ./scripts/gen-secrets.sh --env-file /tmp/t.env --check` | Exit 0, all OK |
| 2 | gen-secrets.sh never prints secret values | `./scripts/gen-secrets.sh 2>&1 \| grep -E '[a-zA-Z0-9]{24,}'` | No output (no long random strings) |
| 3 | gen-secrets.sh preserves existing secrets | Set a known value, run script, verify value unchanged | Value preserved |
| 4 | gen-secrets.sh --rotate-all regenerates all | Compare values before/after | All 11 changed |
| 5 | gen-secrets.sh --rotate CSV rotates only named | Compare before/after | Only named vars changed |
| 6 | .env file permissions are 600 | `stat -c '%a' .env` | `600` |
| 7 | Child accounts blocked when moderation API down | `pytest tests/test_safety_fail_closed.py -k child` | All pass |
| 8 | Adult accounts allowed when moderation API down | `pytest tests/test_safety_fail_closed.py -k adult` | All pass |
| 9 | Child thresholds stricter than defaults | `pytest tests/test_safety_fail_closed.py -k thresholds` | Pass |
| 10 | All containers healthy on VPS | `docker compose ps` | All healthy |
| 11 | Health endpoints respond | `curl` commands above | HTTP 200 |
| 12 | In-container fail-closed verification | `docker exec` command above | ALL CHECKS PASSED |
