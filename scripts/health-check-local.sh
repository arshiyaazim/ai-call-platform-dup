#!/usr/bin/env bash
# ============================================================
# health-check-local.sh — Local pre-deploy validation checks
# Runs WITHOUT SSH/Docker — validates files, configs, syntax
# Usage: bash scripts/health-check-local.sh
# ============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS+1)); printf "  ${GREEN}✓${NC} %s\n" "$1"; }
fail() { FAIL=$((FAIL+1)); printf "  ${RED}✗${NC} %s\n" "$1"; }
warn() { WARN=$((WARN+1)); printf "  ${YELLOW}⚠${NC} %s\n" "$1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo " Local Pre-Deploy Validation"
echo " $(date)"
echo "============================================"
echo ""

# ── Required Files ──────────────────────────────────────────
echo -e "${CYAN}── Required Files ──${NC}"
REQUIRED_FILES=(
    "ai-infra/docker-compose.yaml"
    "dograh/docker-compose.yaml"
    "fazle-ai/docker-compose.yaml"
    "scripts/phase5-standalone.yaml"
    ".env"
    "configs/nginx/iamazim.com.conf"
    "configs/nginx/api.iamazim.com.conf"
    "configs/nginx/livekit.iamazim.com.conf"
    "configs/nginx/fazle.iamazim.com.conf"
    "configs/livekit/livekit.yaml"
    "configs/coturn/turnserver.conf"
    "scripts/backup.sh"
    "scripts/deploy.sh"
    "scripts/health-check.sh"
)
for f in "${REQUIRED_FILES[@]}"; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        pass "$f exists"
    else
        fail "$f MISSING"
    fi
done
echo ""

# ── Shell Script Syntax ────────────────────────────────────
echo -e "${CYAN}── Shell Script Syntax ──${NC}"
for script in "$PROJECT_DIR"/scripts/*.sh; do
    name=$(basename "$script")
    if bash -n "$script" 2>/dev/null; then
        pass "$name — syntax OK"
    else
        fail "$name — syntax ERROR"
    fi
done
echo ""

# ── Docker Compose Validation ──────────────────────────────
echo -e "${CYAN}── Docker Compose ──${NC}"
if command -v docker >/dev/null 2>&1; then
    for compose in ai-infra/docker-compose.yaml dograh/docker-compose.yaml fazle-ai/docker-compose.yaml scripts/phase5-standalone.yaml; do
        if docker compose -f "$PROJECT_DIR/$compose" --env-file "$PROJECT_DIR/.env" config --quiet 2>/dev/null; then
            pass "$compose — valid"
        else
            fail "$compose — invalid"
        fi
    done
else
    warn "Docker not available locally — skipping compose validation"
fi
echo ""

# ── Secret Leaks ───────────────────────────────────────────
echo -e "${CYAN}── Secret Leak Check ──${NC}"
LEAK=false
for pattern in "password" "secret" "api_key" "private_key"; do
    # Exclude .env files, .gitignore, example files, and scripts that reference env vars
    MATCHES=$(grep -ril "$pattern" "$PROJECT_DIR" \
        --include="*.yaml" --include="*.yml" --include="*.conf" \
        --exclude-dir=".git" --exclude-dir="node_modules" \
        2>/dev/null | grep -v ".example" | grep -v ".env" || true)
    if [ -n "$MATCHES" ]; then
        while IFS= read -r match; do
            # Only flag if it looks like a hardcoded value (not an env var reference)
            if grep -qP '(?:password|secret|api_key|private_key)\s*[:=]\s*["\x27]?[a-zA-Z0-9]{8,}' "$match" 2>/dev/null; then
                warn "Possible hardcoded secret in: $match"
                LEAK=true
            fi
        done <<< "$MATCHES"
    fi
done
if [ "$LEAK" = false ]; then
    pass "No obvious hardcoded secrets found"
fi
echo ""

# ── Image Version Pinning ──────────────────────────────────
echo -e "${CYAN}── Image Version Pinning ──${NC}"
LATEST_COUNT=0
for compose in ai-infra/docker-compose.yaml dograh/docker-compose.yaml fazle-ai/docker-compose.yaml scripts/phase5-standalone.yaml; do
    LATEST_COUNT=$((LATEST_COUNT + $(grep -c ':latest' "$PROJECT_DIR/$compose" 2>/dev/null || echo 0)))
done
if [ "$LATEST_COUNT" -eq 0 ]; then
    pass "No :latest tags found"
else
    warn "$LATEST_COUNT :latest tag(s) — verify these are intentional (CI/CD images)"
fi
echo ""

# ── Stale File Check ───────────────────────────────────────
echo -e "${CYAN}── Stale Files ──${NC}"
STALE_FILES=("nginx-iamazim.conf")
for f in "${STALE_FILES[@]}"; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        fail "Stale file still present: $f"
    else
        pass "$f removed"
    fi
done
echo ""

# ── Git Status ──────────────────────────────────────────────
echo -e "${CYAN}── Git Status ──${NC}"
if command -v git >/dev/null 2>&1 && [ -d "$PROJECT_DIR/.git" ]; then
    UNCOMMITTED=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l)
    if [ "$UNCOMMITTED" -eq 0 ]; then
        pass "Working tree clean"
    else
        warn "$UNCOMMITTED uncommitted change(s)"
    fi
    # Check tracked secrets
    if git -C "$PROJECT_DIR" ls-files | grep -qE '\.env$|password' 2>/dev/null; then
        fail "Sensitive file tracked in git"
    else
        pass "No sensitive files in git tracking"
    fi
else
    warn "Git not available or not a git repo"
fi
echo ""

# ── Summary ─────────────────────────────────────────────────
echo "============================================"
printf " ${GREEN}✓ %d passed${NC}  ${RED}✗ %d failed${NC}  ${YELLOW}⚠ %d warnings${NC}\n" "$PASS" "$FAIL" "$WARN"
if [ "$FAIL" -eq 0 ]; then
    echo -e " ${GREEN}Ready for deployment${NC}"
else
    echo -e " ${RED}$FAIL issue(s) must be fixed before deploy${NC}"
fi
echo "============================================"

exit $FAIL
