#!/usr/bin/env bash
# ============================================================
# gen-secrets.sh — Generate / rotate secrets for the AI Voice
# Agent SaaS Platform (Dograh + Fazle).
#
# Usage:
#   ./scripts/gen-secrets.sh                        # generate missing secrets
#   ./scripts/gen-secrets.sh --check                # validate required vars
#   ./scripts/gen-secrets.sh --rotate-all           # rotate every managed secret
#   ./scripts/gen-secrets.sh --rotate VAR1,VAR2     # rotate specific secrets
#   ./scripts/gen-secrets.sh --env-file /path/.env  # use custom env file
# ============================================================
set -euo pipefail
IFS=$'\n\t'

# ── Managed secrets list ────────────────────────────────────
# Each entry: VAR_NAME:LENGTH:TYPE
#   TYPE: key = openssl rand -base64 <len> filtered to alnum
#         apiprefix = "API" + hex (for LiveKit API key)
MANAGED_SECRETS=(
  "POSTGRES_PASSWORD:32:key"
  "REDIS_PASSWORD:32:key"
  "MINIO_SECRET_KEY:32:key"
  "OSS_JWT_SECRET:48:key"
  "LIVEKIT_API_KEY:0:apiprefix"
  "LIVEKIT_API_SECRET:48:key"
  "TURN_SECRET:32:key"
  "FAZLE_API_KEY:48:key"
  "FAZLE_JWT_SECRET:48:key"
  "NEXTAUTH_SECRET:48:key"
  "GRAFANA_PASSWORD:24:key"
)

# ── Defaults ────────────────────────────────────────────────
ENV_FILE=".env"
MODE="generate"          # generate | check | rotate-all | rotate-csv
ROTATE_CSV=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Logging (never prints secret values) ────────────────────
log_info()  { echo "[gen-secrets] $*" >&2; }
log_error() { echo "[gen-secrets] ERROR: $*" >&2; }

# ── Parse arguments ─────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      shift
      ENV_FILE="${1:?--env-file requires a path}"
      ;;
    --check)
      MODE="check"
      ;;
    --rotate-all)
      MODE="rotate-all"
      ;;
    --rotate)
      MODE="rotate-csv"
      shift
      ROTATE_CSV="${1:?--rotate requires comma-separated VAR names}"
      ;;
    -h|--help)
      echo "Usage: $0 [--env-file <path>] [--check | --rotate-all | --rotate VAR,VAR]"
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      exit 1
      ;;
  esac
  shift
done

# Resolve env file relative to project root
if [[ "${ENV_FILE}" != /* ]]; then
  ENV_FILE="${PROJECT_DIR}/${ENV_FILE}"
fi

# ── Secret generation helpers ───────────────────────────────
generate_key() {
  local length="$1"
  # Generate enough random bytes and filter to alphanumeric
  openssl rand -base64 $(( length * 2 )) 2>/dev/null | tr -dc 'a-zA-Z0-9' | head -c "${length}"
}

generate_apiprefix() {
  echo "API$(openssl rand -hex 6 2>/dev/null)"
}

generate_secret() {
  local var_name="$1" length="$2" stype="$3"
  case "${stype}" in
    apiprefix) generate_apiprefix ;;
    key)       generate_key "${length}" ;;
    *)         log_error "Unknown secret type: ${stype}"; exit 1 ;;
  esac
}

# ── Env-file helpers ────────────────────────────────────────
# Read current value of a var from env file (empty if missing/unset)
read_env_var() {
  local var="$1" file="$2"
  if [[ ! -f "${file}" ]]; then
    echo ""
    return
  fi
  # Match VAR=value or VAR="value" (not commented lines)
  grep -E "^${var}=" "${file}" 2>/dev/null | tail -1 | sed "s/^${var}=//" | sed 's/^"//;s/"$//' || true
}

# Check if a value looks like an unset placeholder
is_placeholder() {
  local val="$1"
  [[ -z "${val}" ]] && return 0
  [[ "${val}" == CHANGE_ME* ]] && return 0
  [[ "${val}" == change-me* ]] && return 0
  [[ "${val}" == your-* ]] && return 0
  [[ "${val}" == your_* ]] && return 0
  [[ "${val}" == sk-your-* ]] && return 0
  return 1
}


# ── Check if a var should be rotated ────────────────────────
should_rotate() {
  local var="$1"
  case "${MODE}" in
    rotate-all) return 0 ;;
    rotate-csv)
      echo ",${ROTATE_CSV}," | grep -q ",${var}," && return 0
      return 1
      ;;
    *) return 1 ;;
  esac
}

# ── Mode: CHECK ─────────────────────────────────────────────
run_check() {
  local missing=0
  local placeholder=0

  if [[ ! -f "${ENV_FILE}" ]]; then
    log_error "Env file not found: ${ENV_FILE}"
    exit 1
  fi

  for entry in "${MANAGED_SECRETS[@]}"; do
    IFS=':' read -r var_name _len _type <<< "${entry}"
    local current
    current="$(read_env_var "${var_name}" "${ENV_FILE}")"
    if [[ -z "${current}" ]]; then
      log_error "MISSING: ${var_name}"
      missing=$((missing + 1))
    elif is_placeholder "${current}"; then
      log_error "PLACEHOLDER: ${var_name} (still has default value)"
      placeholder=$((placeholder + 1))
    else
      log_info "OK: ${var_name}"
    fi
  done

  if [[ ${missing} -gt 0 ]] || [[ ${placeholder} -gt 0 ]]; then
    log_error "Check failed: ${missing} missing, ${placeholder} placeholder(s)"
    exit 1
  fi

  log_info "All ${#MANAGED_SECRETS[@]} managed secrets are present and non-placeholder."
  exit 0
}

# ── Mode: GENERATE / ROTATE ────────────────────────────────
run_generate() {
  # Create env file from example if it doesn't exist
  if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f "${PROJECT_DIR}/.env.example" ]]; then
      cp "${PROJECT_DIR}/.env.example" "${ENV_FILE}"
      log_info "Created ${ENV_FILE} from .env.example"
    else
      touch "${ENV_FILE}"
      log_info "Created empty ${ENV_FILE}"
    fi
  fi

  # Read current env file into a variable
  local env_content
  env_content="$(cat "${ENV_FILE}")"

  local changed=0

  for entry in "${MANAGED_SECRETS[@]}"; do
    IFS=':' read -r var_name var_len var_type <<< "${entry}"
    local current
    current="$(read_env_var "${var_name}" "${ENV_FILE}")"

    local needs_gen=false

    # Decide whether to generate
    if should_rotate "${var_name}"; then
      needs_gen=true
    elif [[ -z "${current}" ]] || is_placeholder "${current}"; then
      needs_gen=true
    fi

    if [[ "${needs_gen}" == "true" ]]; then
      local new_value
      new_value="$(generate_secret "${var_name}" "${var_len}" "${var_type}")"

      # Update env content
      if echo "${env_content}" | grep -qE "^${var_name}="; then
        env_content="$(echo "${env_content}" | sed "s|^${var_name}=.*|${var_name}=${new_value}|")"
      else
        env_content="${env_content}
${var_name}=${new_value}"
      fi

      if should_rotate "${var_name}"; then
        log_info "ROTATED: ${var_name}"
      else
        log_info "SET: ${var_name}"
      fi
      changed=$((changed + 1))
    else
      log_info "KEPT: ${var_name} (already set)"
    fi
  done

  if [[ ${changed} -eq 0 ]]; then
    log_info "No changes needed. All managed secrets already set."
    return 0
  fi

  # Atomic write: write to temp file, then mv into place
  local tmp_file
  tmp_file="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"

  # Ensure cleanup on failure
  trap 'rm -f "${tmp_file}"' ERR

  echo "${env_content}" > "${tmp_file}"
  chmod 600 "${tmp_file}"
  mv -f "${tmp_file}" "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"

  log_info "Updated ${changed} secret(s) in ${ENV_FILE} (permissions: 600)"
}

# ── Main ────────────────────────────────────────────────────
case "${MODE}" in
  check)
    run_check
    ;;
  generate|rotate-all|rotate-csv)
    run_generate
    ;;
esac
