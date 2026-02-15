#!/usr/bin/env bash
set -euo pipefail

REVERSE_PORT="${1:-2223}"

if [[ $EUID -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

SSHD_CONFIG="/etc/ssh/sshd_config"

ensure_sshd_key_value() {
  local key="$1"
  local value="$2"
  if grep -Eq "^#?${key}\\b" "$SSHD_CONFIG"; then
    "${SUDO[@]}" sed -i "s|^#\?${key}.*|${key} ${value}|" "$SSHD_CONFIG"
  else
    echo "${key} ${value}" | "${SUDO[@]}" tee -a "$SSHD_CONFIG" >/dev/null
  fi
}

ensure_sshd_key_value "AllowTcpForwarding" "yes"
ensure_sshd_key_value "GatewayPorts" "clientspecified"
ensure_sshd_key_value "ClientAliveInterval" "60"
ensure_sshd_key_value "ClientAliveCountMax" "3"

if command -v ufw >/dev/null 2>&1; then
  if "${SUDO[@]}" ufw status | grep -qi "Status: active"; then
    "${SUDO[@]}" ufw allow "${REVERSE_PORT}/tcp"
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  "${SUDO[@]}" systemctl restart sshd 2>/dev/null || "${SUDO[@]}" systemctl restart ssh
else
  "${SUDO[@]}" service ssh restart
fi

echo "Cloud SSH is ready for reverse tunnel on TCP ${REVERSE_PORT}."
