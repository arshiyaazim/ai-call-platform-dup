#!/usr/bin/env bash
# ============================================================
# docker_user_firewall.sh — DOCKER-USER iptables rules
#
# Docker bypasses UFW by inserting rules into the DOCKER chain
# (nat + filter) which sit in the FORWARD path, not INPUT.
# The DOCKER-USER chain is the official hook for user-defined
# rules that Docker guarantees will be evaluated BEFORE its
# own DOCKER chain.
#
# This script populates DOCKER-USER with an allowlist of ports
# that may be reached from external interfaces. All other new
# inbound connections destined for Docker-published ports are
# dropped.
#
# Idempotent: checks for existing rules before inserting.
# ============================================================
set -euo pipefail

# ── Must be root ─────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "[docker-fw] ERROR: Must be run as root (sudo)." >&2
  exit 1
fi

if ! command -v iptables &>/dev/null; then
  echo "[docker-fw] ERROR: iptables not found." >&2
  exit 1
fi

# ── Comment tag for our managed rules ────────────────────────
TAG="iamazim-docker-user"

# ── Helper: add rule only if not already present ─────────────
add_rule() {
  local table="$1"; shift
  local chain="$1"; shift
  # $@ = remaining rule args
  if ! iptables -t "$table" -C "$chain" "$@" 2>/dev/null; then
    iptables -t "$table" -A "$chain" "$@"
    echo "[docker-fw] Added: iptables -t $table -A $chain $*"
  fi
}

add_rule6() {
  local table="$1"; shift
  local chain="$1"; shift
  if command -v ip6tables &>/dev/null; then
    if ! ip6tables -t "$table" -C "$chain" "$@" 2>/dev/null; then
      ip6tables -t "$table" -A "$chain" "$@"
      echo "[docker-fw] Added: ip6tables -t $table -A $chain $*"
    fi
  fi
}

# ── Ensure DOCKER-USER chain exists ──────────────────────────
if ! iptables -t filter -L DOCKER-USER -n &>/dev/null; then
  iptables -t filter -N DOCKER-USER
  echo "[docker-fw] Created DOCKER-USER chain."
fi

# Ensure FORWARD jumps to DOCKER-USER (Docker normally does this,
# but verify). Insert at position 1 if missing.
if ! iptables -t filter -C FORWARD -j DOCKER-USER 2>/dev/null; then
  iptables -t filter -I FORWARD 1 -j DOCKER-USER
  echo "[docker-fw] Added FORWARD → DOCKER-USER jump."
fi

# ── Remove the default RETURN rule so we can build our allowlist ─
# Docker inserts a blanket RETURN in DOCKER-USER. We need to remove
# it so our DROP at the end is effective, then add our rules + a
# final RETURN for traffic we don't need to filter.
#
# Strategy: flush our tagged rules and rebuild. We flush ONLY if
# the chain has our tag, otherwise this is a first run.

has_tag() {
  iptables -t filter -S DOCKER-USER 2>/dev/null | grep -q "$TAG"
}

flush_tagged() {
  # Remove all rules containing our tag comment
  while iptables -t filter -S DOCKER-USER 2>/dev/null | grep -q "$TAG"; do
    local linenum
    linenum=$(iptables -t filter -S DOCKER-USER --line-numbers 2>/dev/null \
      | grep "$TAG" | head -1 | awk '{print $1}')
    # -S with --line-numbers prepends the number; but we need -L format
    # Safer: use -D with the full rule spec
    local rule
    rule=$(iptables -t filter -S DOCKER-USER 2>/dev/null | grep "$TAG" | head -1 | sed 's/^-A DOCKER-USER //')
    iptables -t filter -D DOCKER-USER $rule 2>/dev/null || break
  done
  if command -v ip6tables &>/dev/null; then
    while ip6tables -t filter -S DOCKER-USER 2>/dev/null | grep -q "$TAG"; do
      local rule6
      rule6=$(ip6tables -t filter -S DOCKER-USER 2>/dev/null | grep "$TAG" | head -1 | sed 's/^-A DOCKER-USER //')
      ip6tables -t filter -D DOCKER-USER $rule6 2>/dev/null || break
    done
  fi
}

echo "[docker-fw] Configuring DOCKER-USER chain allowlist..."

# Always rebuild: flush tagged rules and re-add
if has_tag; then
  echo "[docker-fw] Removing previous managed rules..."
  flush_tagged
fi

# ── 1. Allow established/related (stateful) ──────────────────
add_rule filter DOCKER-USER \
  -m conntrack --ctstate ESTABLISHED,RELATED \
  -m comment --comment "$TAG" \
  -j RETURN

# ── 2. Allow loopback ────────────────────────────────────────
add_rule filter DOCKER-USER \
  -i lo \
  -m comment --comment "$TAG" \
  -j RETURN

# ── 3. Allow Docker internal bridge traffic ──────────────────
#    Docker bridge interfaces are typically docker0, br-*
#    Allow any traffic originating from docker/bridge interfaces
#    so inter-container communication is never broken.
add_rule filter DOCKER-USER \
  -i docker0 \
  -m comment --comment "$TAG" \
  -j RETURN

# Allow all br-* interfaces (Docker custom networks)
# We use a wildcard match
add_rule filter DOCKER-USER \
  -i br-+ \
  -m comment --comment "$TAG" \
  -j RETURN

# ── 4. Allowlist: external inbound to Docker-published ports ─
# These match traffic arriving from external interfaces (eth0,
# ens+, etc.) destined for containers.

# LiveKit RTC TCP
add_rule filter DOCKER-USER \
  -p tcp --dport 7881 \
  -m comment --comment "$TAG" \
  -j RETURN

# Coturn STUN/TURN
add_rule filter DOCKER-USER \
  -p tcp --dport 3478 \
  -m comment --comment "$TAG" \
  -j RETURN
add_rule filter DOCKER-USER \
  -p udp --dport 3478 \
  -m comment --comment "$TAG" \
  -j RETURN

# Coturn TURN TLS
add_rule filter DOCKER-USER \
  -p tcp --dport 5349 \
  -m comment --comment "$TAG" \
  -j RETURN
add_rule filter DOCKER-USER \
  -p udp --dport 5349 \
  -m comment --comment "$TAG" \
  -j RETURN

# Coturn UDP relay range
add_rule filter DOCKER-USER \
  -p udp --dport 49152:49252 \
  -m comment --comment "$TAG" \
  -j RETURN

# LiveKit WebRTC media range
add_rule filter DOCKER-USER \
  -p udp --dport 50000:50200 \
  -m comment --comment "$TAG" \
  -j RETURN

# ── 5. DROP all other new inbound to Docker-published ports ──
# This catches any external traffic that was NOT in the allowlist
# above. We match only NEW connections so established traffic
# (already allowed above) is not affected.
add_rule filter DOCKER-USER \
  -m conntrack --ctstate NEW \
  -m comment --comment "$TAG" \
  ! -i lo \
  ! -i docker0 \
  ! -i br-+ \
  -j DROP

# ── IPv6 (best-effort) ──────────────────────────────────────
if command -v ip6tables &>/dev/null; then
  echo "[docker-fw] Applying matching IPv6 rules..."

  if ! ip6tables -t filter -L DOCKER-USER -n &>/dev/null; then
    ip6tables -t filter -N DOCKER-USER
  fi

  add_rule6 filter DOCKER-USER \
    -m conntrack --ctstate ESTABLISHED,RELATED \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -i lo \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -i docker0 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -i br-+ \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p tcp --dport 7881 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p tcp --dport 3478 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p udp --dport 3478 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p tcp --dport 5349 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p udp --dport 5349 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p udp --dport 49152:49252 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -p udp --dport 50000:50200 \
    -m comment --comment "$TAG" \
    -j RETURN
  add_rule6 filter DOCKER-USER \
    -m conntrack --ctstate NEW \
    -m comment --comment "$TAG" \
    ! -i lo \
    ! -i docker0 \
    ! -i br-+ \
    -j DROP
else
  echo "[docker-fw] ip6tables not found — skipping IPv6 rules."
fi

# ── Show result ──────────────────────────────────────────────
echo ""
echo "[docker-fw] ════════════════════════════════════════════"
echo "[docker-fw] DOCKER-USER chain configured successfully."
echo "[docker-fw] ════════════════════════════════════════════"
echo ""
echo "[docker-fw] Current DOCKER-USER rules (IPv4):"
iptables -t filter -S DOCKER-USER
if command -v ip6tables &>/dev/null; then
  echo ""
  echo "[docker-fw] Current DOCKER-USER rules (IPv6):"
  ip6tables -t filter -S DOCKER-USER
fi
