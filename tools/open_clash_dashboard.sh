#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-}"

if [[ -z "$ENV_FILE" ]]; then
  if [[ -f "$ROOT_DIR/host/host-stack.env" ]]; then
    ENV_FILE="$ROOT_DIR/host/host-stack.env"
  elif [[ -f "$ROOT_DIR/docker/docker-stack.env" ]]; then
    ENV_FILE="$ROOT_DIR/docker/docker-stack.env"
  else
    echo "[ERROR] No env file found. Pass one explicitly, e.g.:"
    echo "        bash tools/open_clash_dashboard.sh host/host-stack.env"
    exit 1
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] Env file not found: $ENV_FILE"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

CLOUD_HOST="${CLOUD_HOST:-}"
REVERSE_PORT="${REVERSE_PORT:-2223}"
CLASH_API_PORT="${CLASH_API_PORT:-9090}"
LOCAL_DASHBOARD_PORT="${LOCAL_DASHBOARD_PORT:-9090}"
DASHBOARD_SSH_USER="${DASHBOARD_SSH_USER:-${TARGET_USER:-root}}"
DASHBOARD_URL="${DASHBOARD_URL:-https://metacubex.github.io/metacubexd/}"

if [[ -z "$CLOUD_HOST" ]]; then
  echo "[ERROR] CLOUD_HOST is empty in $ENV_FILE"
  exit 1
fi

safe_host="${CLOUD_HOST//[^[:alnum:]._-]/_}"
CTRL_SOCKET="${TMPDIR:-/tmp}/lab-clash-dashboard-${safe_host}-${REVERSE_PORT}-${LOCAL_DASHBOARD_PORT}.sock"

ssh_base=(
  -S "$CTRL_SOCKET"
  -p "$REVERSE_PORT"
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
)

if ssh "${ssh_base[@]}" "${DASHBOARD_SSH_USER}@${CLOUD_HOST}" -O check >/dev/null 2>&1; then
  echo "[INFO] Tunnel already running."
else
  echo "[INFO] Starting tunnel: localhost:${LOCAL_DASHBOARD_PORT} -> 127.0.0.1:${CLASH_API_PORT} via ${DASHBOARD_SSH_USER}@${CLOUD_HOST}:${REVERSE_PORT}"
  ssh -M -f -N \
    "${ssh_base[@]}" \
    -L "${LOCAL_DASHBOARD_PORT}:127.0.0.1:${CLASH_API_PORT}" \
    "${DASHBOARD_SSH_USER}@${CLOUD_HOST}"
fi

echo "[INFO] Clash API local endpoint: http://127.0.0.1:${LOCAL_DASHBOARD_PORT}"
echo "[INFO] Open dashboard and use API: http://127.0.0.1:${LOCAL_DASHBOARD_PORT}"
echo "       Dashboard URL: ${DASHBOARD_URL}"

if command -v open >/dev/null 2>&1; then
  open "$DASHBOARD_URL" >/dev/null 2>&1 || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$DASHBOARD_URL" >/dev/null 2>&1 || true
fi

echo
echo "To stop tunnel:"
echo "ssh -S '$CTRL_SOCKET' -p '$REVERSE_PORT' '${DASHBOARD_SSH_USER}@${CLOUD_HOST}' -O exit"
