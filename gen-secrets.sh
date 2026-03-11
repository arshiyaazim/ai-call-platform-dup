#!/usr/bin/env bash
# DEPRECATED: This file is kept for backward compatibility.
# Use scripts/gen-secrets.sh instead.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/scripts/gen-secrets.sh" "$@"
