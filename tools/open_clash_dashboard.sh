#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[INFO] tools/open_clash_dashboard.sh 已迁移到 local/open_clash_dashboard.sh"
exec "$ROOT_DIR/local/open_clash_dashboard.sh" "$@"
