#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ERROR] docker/setup_docker_mirror_cn.sh must run on a Linux host."
  exit 1
fi

usage() {
  cat <<USAGE
Usage:
  bash docker/setup_docker_mirror_cn.sh [--enable-proxy] [--proxy-url URL] [--mirrors CSV]
  bash docker/setup_docker_mirror_cn.sh --disable-proxy

Options:
  --enable-proxy       Configure Docker daemon HTTP/HTTPS proxy (default: disabled)
  --disable-proxy      Remove Docker daemon proxy drop-in only
  --proxy-url URL      Proxy URL used with --enable-proxy (default: http://127.0.0.1:7890)
  --mirrors CSV        Comma-separated mirror list
USAGE
}

DEFAULT_MIRRORS="https://docker.m.daocloud.io,https://dockerproxy.com,https://hub-mirror.c.163.com"
DOCKER_REGISTRY_MIRRORS="${DOCKER_REGISTRY_MIRRORS:-$DEFAULT_MIRRORS}"
CLASH_PROXY_URL="${CLASH_PROXY_URL:-http://127.0.0.1:7890}"
ENABLE_PROXY=0
DISABLE_PROXY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-proxy)
      ENABLE_PROXY=1
      shift
      ;;
    --disable-proxy)
      DISABLE_PROXY=1
      shift
      ;;
    --proxy-url)
      [[ $# -ge 2 ]] || { usage; exit 1; }
      CLASH_PROXY_URL="$2"
      shift 2
      ;;
    --mirrors)
      [[ $# -ge 2 ]] || { usage; exit 1; }
      DOCKER_REGISTRY_MIRRORS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ $ENABLE_PROXY -eq 1 && $DISABLE_PROXY -eq 1 ]]; then
  echo "[ERROR] --enable-proxy and --disable-proxy cannot be used together."
  exit 1
fi

if [[ $EUID -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed. Install Docker first."
  exit 1
fi

DAEMON_JSON="/etc/docker/daemon.json"
DROPIN_DIR="/etc/systemd/system/docker.service.d"
PROXY_DROPIN="$DROPIN_DIR/http-proxy.conf"
TMP_JSON="$(mktemp "${TMPDIR:-/tmp}/daemon.XXXXXX.json")"
trap 'rm -f "$TMP_JSON"' EXIT

MIRRORS_CSV="$DOCKER_REGISTRY_MIRRORS"

"${SUDO[@]}" mkdir -p /etc/docker

if [[ -f "$DAEMON_JSON" ]]; then
  backup="${DAEMON_JSON}.bak.$(date +%Y%m%d%H%M%S)"
  echo "[INFO] Backup existing daemon.json -> $backup"
  "${SUDO[@]}" cp "$DAEMON_JSON" "$backup"
fi

python3 - "$DAEMON_JSON" "$TMP_JSON" "$MIRRORS_CSV" <<'PY'
import json
import os
import sys

src, dst, mirrors_csv = sys.argv[1], sys.argv[2], sys.argv[3]
mirrors = [m.strip() for m in mirrors_csv.split(',') if m.strip()]
if not mirrors:
    raise SystemExit("No valid mirrors provided")

obj = {}
if os.path.exists(src) and os.path.getsize(src) > 0:
    with open(src, 'r', encoding='utf-8') as f:
        obj = json.load(f)

obj['registry-mirrors'] = mirrors

with open(dst, 'w', encoding='utf-8') as f:
    json.dump(obj, f, indent=2, ensure_ascii=False)
    f.write('\n')
PY

"${SUDO[@]}" install -m 644 "$TMP_JSON" "$DAEMON_JSON"
echo "[INFO] Updated $DAEMON_JSON"

if [[ $DISABLE_PROXY -eq 1 ]]; then
  if [[ -f "$PROXY_DROPIN" ]]; then
    "${SUDO[@]}" rm -f "$PROXY_DROPIN"
    echo "[INFO] Removed Docker proxy drop-in: $PROXY_DROPIN"
  else
    echo "[INFO] No Docker proxy drop-in found to remove."
  fi
elif [[ $ENABLE_PROXY -eq 1 ]]; then
  "${SUDO[@]}" mkdir -p "$DROPIN_DIR"
  cat <<PROXY | "${SUDO[@]}" tee "$PROXY_DROPIN" >/dev/null
[Service]
Environment="HTTP_PROXY=$CLASH_PROXY_URL"
Environment="HTTPS_PROXY=$CLASH_PROXY_URL"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
PROXY
  echo "[INFO] Wrote Docker proxy drop-in: $PROXY_DROPIN"
fi

"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl restart docker

if ! "${SUDO[@]}" systemctl is-active docker >/dev/null; then
  echo "[ERROR] Docker failed to start after configuration."
  "${SUDO[@]}" systemctl status docker --no-pager -l || true
  exit 1
fi

echo "[INFO] Docker restarted. Current mirrors:"
"${SUDO[@]}" docker info 2>/dev/null | sed -n '/Registry Mirrors/,+6p' || true

echo "[INFO] Done. You can test with: sudo docker pull ubuntu:22.04"
