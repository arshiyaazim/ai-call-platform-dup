#!/usr/bin/env bash
# ============================================================
# cert_expiry_metric.sh — Output Prometheus textfile metric for
#                          certificate days remaining.
#
# Usage:
#   ./scripts/vps/cert_expiry_metric.sh                  (stdout)
#   ./scripts/vps/cert_expiry_metric.sh --out /path/to/file.prom
#
# Metric:
#   iamazim_tls_cert_days_remaining{domain="iamazim.com"} 42
#
# Intended for node-exporter textfile collector. See docs for
# how to enable the collector.
# ============================================================
set -euo pipefail

CERT_DIR="/etc/letsencrypt/live/iamazim.com"
FULLCHAIN="${CERT_DIR}/fullchain.pem"
OUT_FILE=""

# ── Parse args ──
while [ $# -gt 0 ]; do
  case "$1" in
    --out)
      OUT_FILE="$2"
      shift 2
      ;;
    --cert-dir)
      CERT_DIR="$2"
      FULLCHAIN="${CERT_DIR}/fullchain.pem"
      shift 2
      ;;
    *)
      echo "Usage: $0 [--out /path/to/file.prom] [--cert-dir /path/to/cert]" >&2
      exit 1
      ;;
  esac
done

# ── Compute days remaining ──
if [ ! -f "$FULLCHAIN" ]; then
  DAYS=-1
else
  NOT_AFTER=$(openssl x509 -in "$FULLCHAIN" -noout -enddate 2>/dev/null | sed 's/^notAfter=//')
  EXPIRY_EPOCH=$(date -d "$NOT_AFTER" +%s 2>/dev/null) || EXPIRY_EPOCH=0
  NOW_EPOCH=$(date +%s)
  DAYS=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
fi

# ── Build metric output ──
METRIC_HELP="# HELP iamazim_tls_cert_days_remaining Days until TLS certificate expires."
METRIC_TYPE="# TYPE iamazim_tls_cert_days_remaining gauge"
METRIC_LINE="iamazim_tls_cert_days_remaining{domain=\"iamazim.com\"} ${DAYS}"

OUTPUT="${METRIC_HELP}
${METRIC_TYPE}
${METRIC_LINE}"

# ── Write or print ──
if [ -n "$OUT_FILE" ]; then
  # Atomic write: write to temp then rename (avoids partial reads by collector)
  TMP_FILE="${OUT_FILE}.$$"
  mkdir -p "$(dirname "$OUT_FILE")"
  echo "$OUTPUT" > "$TMP_FILE"
  mv "$TMP_FILE" "$OUT_FILE"
else
  echo "$OUTPUT"
fi
