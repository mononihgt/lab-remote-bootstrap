#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/host-stack.env}"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

TARGET_USER="${TARGET_USER:-${SUDO_USER:-$USER}}"
INSTALL_ROOT="${INSTALL_ROOT:-/opt/lab-remote-stack}"
CLASH_SOURCE_DIR="${CLASH_SOURCE_DIR:-}"
CLASH_CORE_FILE="${CLASH_CORE_FILE:-}"
CLASH_CONFIG_FILE="${CLASH_CONFIG_FILE:-config.yaml}"
SSH_KEY_SOURCE="${SSH_KEY_SOURCE:-}"

CLOUD_USER="${CLOUD_USER:-}"
CLOUD_HOST="${CLOUD_HOST:-}"
CLOUD_SSH_PORT="${CLOUD_SSH_PORT:-22}"
REVERSE_PORT="${REVERSE_PORT:-2223}"
LOCAL_SSH_PORT="${LOCAL_SSH_PORT:-22}"

HOST_TIMEZONE="${HOST_TIMEZONE:-Asia/Shanghai}"
CLASH_HTTP_PORT="${CLASH_HTTP_PORT:-7890}"
CLASH_SOCKS_PORT="${CLASH_SOCKS_PORT:-7891}"
CLASH_API_PORT="${CLASH_API_PORT:-9090}"

detect_target_home() {
  local user_name="$1"
  local home_dir=""
  if command -v getent >/dev/null 2>&1; then
    home_dir="$(getent passwd "$user_name" | awk -F: '{print $6}' || true)"
  fi
  if [[ -z "$home_dir" ]]; then
    home_dir="$(eval "echo ~$user_name" 2>/dev/null || true)"
  fi
  printf '%s\n' "$home_dir"
}

normalize_clash_source_dir() {
  local path="${1:-}"
  if [[ -z "$path" || "$path" == "/path/to/lab-remote-bootstrap/assets/clash" ]]; then
    path="$ROOT_DIR/assets/clash"
  elif [[ "$path" != /* ]]; then
    path="$ROOT_DIR/$path"
  fi
  printf '%s\n' "$path"
}

TARGET_HOME="${TARGET_HOME:-$(detect_target_home "$TARGET_USER")}"
CLASH_SOURCE_DIR="$(normalize_clash_source_dir "$CLASH_SOURCE_DIR")"
SSH_KEY_SOURCE="${SSH_KEY_SOURCE:-$TARGET_HOME/.ssh/id_ed25519_autossh}"

if [[ -z "$TARGET_HOME" ]]; then
  echo "[ERROR] Cannot determine home directory for TARGET_USER=$TARGET_USER"
  exit 1
fi
if [[ -z "$CLOUD_USER" || -z "$CLOUD_HOST" ]]; then
  echo "[ERROR] CLOUD_USER and CLOUD_HOST must be set in $CONFIG_FILE"
  exit 1
fi

if [[ $EUID -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

TARGET_GROUP="$(id -gn "$TARGET_USER")"

log() {
  printf "\n[INFO] %s\n" "$1"
}

need_file() {
  local file_path="$1"
  if [[ ! -f "$file_path" ]]; then
    echo "[ERROR] Missing required file: $file_path"
    exit 1
  fi
}

resolve_clash_core() {
  local dir="$1"
  local core_path="${CLASH_CORE_FILE:-}"
  if [[ -n "$core_path" ]]; then
    [[ "$core_path" = /* ]] || core_path="$dir/$core_path"
    printf '%s\n' "$core_path"
    return 0
  fi
  local picked
  picked="$(find "$dir" -maxdepth 1 -type f \
    \( -name 'CrashCore' -o -name 'mihomo*' -o -name 'clash*' \) \
    ! -name '*.gz' | sort | head -n 1)"
  if [[ -n "$picked" ]]; then
    printf '%s\n' "$picked"
    return 0
  fi
  return 1
}

resolve_clash_config() {
  local dir="$1"
  local config_path="${CLASH_CONFIG_FILE:-config.yaml}"
  [[ "$config_path" = /* ]] || config_path="$dir/$config_path"
  printf '%s\n' "$config_path"
}

run_as_target() {
  local cmd="$1"
  if [[ "$USER" == "$TARGET_USER" ]]; then
    bash -lc "$cmd"
  else
    "${SUDO[@]}" -u "$TARGET_USER" bash -lc "$cmd"
  fi
}

run_cloud_cmd() {
  ssh -i "$SSH_KEY_SOURCE" \
    -p "$CLOUD_SSH_PORT" \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=accept-new \
    "${CLOUD_USER}@${CLOUD_HOST}" "$@"
}

detect_pkg_manager() {
  for pm in apt-get dnf yum pacman zypper apk; do
    if command -v "$pm" >/dev/null 2>&1; then
      echo "$pm"
      return 0
    fi
  done
  return 1
}

install_core_packages() {
  local pm="$1"
  case "$pm" in
    apt-get)
      "${SUDO[@]}" apt-get update
      "${SUDO[@]}" apt-get install -y autossh curl git openssh-client openssh-server python3 tmux zsh
      "${SUDO[@]}" apt-get install -y fastfetch >/dev/null 2>&1 || true
      ;;
    dnf)
      "${SUDO[@]}" dnf install -y autossh curl git openssh-clients openssh-server python3 tmux zsh
      "${SUDO[@]}" dnf install -y fastfetch >/dev/null 2>&1 || true
      ;;
    yum)
      "${SUDO[@]}" yum install -y autossh curl git openssh-clients openssh-server python3 tmux zsh
      "${SUDO[@]}" yum install -y fastfetch >/dev/null 2>&1 || true
      ;;
    pacman)
      "${SUDO[@]}" pacman -Sy --noconfirm autossh curl git openssh python tmux zsh
      "${SUDO[@]}" pacman -Sy --noconfirm fastfetch >/dev/null 2>&1 || true
      ;;
    zypper)
      "${SUDO[@]}" zypper --non-interactive install autossh curl git openssh python3 tmux zsh
      "${SUDO[@]}" zypper --non-interactive install fastfetch >/dev/null 2>&1 || true
      ;;
    apk)
      "${SUDO[@]}" apk add autossh curl git openssh python3 tmux zsh
      "${SUDO[@]}" apk add fastfetch >/dev/null 2>&1 || true
      ;;
    *)
      echo "[ERROR] Unsupported package manager: $pm"
      exit 1
      ;;
  esac
}

ssh_service_name() {
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files | grep -q '^ssh\.service'; then
      echo ssh
      return 0
    fi
    if systemctl list-unit-files | grep -q '^sshd\.service'; then
      echo sshd
      return 0
    fi
  fi
  echo ssh
}

set_yaml_scalar() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -Eq "^[[:space:]]*${key}:" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}:.*|${key}: ${value}|" "$file"
  else
    printf '%s: %s\n' "$key" "$value" >> "$file"
  fi
}

write_managed_zsh_block() {
  local zshrc="$TARGET_HOME/.zshrc"
  local start_marker="# >>> lab-remote-bootstrap >>>"
  local end_marker="# <<< lab-remote-bootstrap <<<"
  local block
  block=$(cat <<BLOCK
${start_marker}
export CLASH_HTTP_PORT=${CLASH_HTTP_PORT}
export CLASH_SOCKS_PORT=${CLASH_SOCKS_PORT}
export CLASH_API_PORT=${CLASH_API_PORT}

export http_proxy="http://127.0.0.1:${CLASH_HTTP_PORT}"
export https_proxy="http://127.0.0.1:${CLASH_HTTP_PORT}"
export HTTP_PROXY="http://127.0.0.1:${CLASH_HTTP_PORT}"
export HTTPS_PROXY="http://127.0.0.1:${CLASH_HTTP_PORT}"
export ftp_proxy="http://127.0.0.1:${CLASH_HTTP_PORT}"
export FTP_PROXY="http://127.0.0.1:${CLASH_HTTP_PORT}"
export all_proxy="socks5://127.0.0.1:${CLASH_SOCKS_PORT}"
export ALL_PROXY="socks5://127.0.0.1:${CLASH_SOCKS_PORT}"

autoload -Uz compinit
compinit
zstyle ':completion:*' menu select

HISTFILE=\$HOME/.zhistory
SAVEHIST=5000
HISTSIZE=5000
setopt share_history
setopt hist_expire_dups_first
setopt hist_ignore_dups
setopt hist_verify

bindkey '^[[A' history-search-backward
bindkey '^[[B' history-search-forward

if [[ -r \$HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source \$HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
fi
if [[ -r \$HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source \$HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi
if [[ -r \$HOME/.zsh/plugins/zsh-completions/zsh-completions.plugin.zsh ]]; then
  source \$HOME/.zsh/plugins/zsh-completions/zsh-completions.plugin.zsh
fi

if [[ -r \$HOME/.zsh/themes/powerlevel10k/powerlevel10k.zsh-theme ]]; then
  export POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true
  source \$HOME/.zsh/themes/powerlevel10k/powerlevel10k.zsh-theme
  [[ -f \$HOME/.p10k.zsh ]] && source \$HOME/.p10k.zsh
fi

[[ -f \$HOME/.zshrc.local ]] && source \$HOME/.zshrc.local

if [[ -o interactive ]] && command -v fastfetch >/dev/null 2>&1; then
  fastfetch
fi
${end_marker}
BLOCK
)

  run_as_target "mkdir -p '$TARGET_HOME/.zsh/plugins' '$TARGET_HOME/.zsh/themes'"

  run_as_target "python3 - <<'PY'
from pathlib import Path
zshrc = Path(${zshrc@Q})
start = ${start_marker@Q}
end = ${end_marker@Q}
block = ${block@Q}
text = zshrc.read_text() if zshrc.exists() else ''
if start in text and end in text:
    before = text.split(start, 1)[0].rstrip() + '\n\n'
    after = text.split(end, 1)[1].lstrip('\n')
    text = before + block + '\n\n' + after
else:
    text = text.rstrip() + ('\n\n' if text.strip() else '') + block + '\n'
zshrc.write_text(text)
PY"
}

CLASH_CORE_SOURCE="$(resolve_clash_core "$CLASH_SOURCE_DIR" || true)"
CLASH_CONFIG_SOURCE="$(resolve_clash_config "$CLASH_SOURCE_DIR")"
if [[ -z "$CLASH_CORE_SOURCE" ]]; then
  echo "[ERROR] No clash core binary found in $CLASH_SOURCE_DIR"
  echo "        Provide CrashCore/mihomo*/clash* (non-.gz), or set CLASH_CORE_FILE in env."
  exit 1
fi

log "Checking required local files"
need_file "$SSH_KEY_SOURCE"
need_file "$CLASH_CORE_SOURCE"
need_file "$CLASH_CONFIG_SOURCE"
need_file "$CLASH_SOURCE_DIR/geoip.dat"
need_file "$CLASH_SOURCE_DIR/geosite.dat"

log "Checking access to cloud host"
if ! run_cloud_cmd "echo cloud-ok" >/dev/null; then
  echo "[ERROR] Cannot access ${CLOUD_USER}@${CLOUD_HOST}:${CLOUD_SSH_PORT} using key: $SSH_KEY_SOURCE"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "[ERROR] systemd/systemctl is required for host-mode services"
  exit 1
fi

PM="$(detect_pkg_manager || true)"
if [[ -z "$PM" ]]; then
  echo "[ERROR] No supported package manager found"
  exit 1
fi

log "Installing required packages via $PM"
install_core_packages "$PM"

log "Enabling local SSH service"
SSH_SERVICE="$(ssh_service_name)"
"${SUDO[@]}" systemctl enable --now "$SSH_SERVICE" >/dev/null 2>&1 || true

log "Preparing install directories"
"${SUDO[@]}" mkdir -p "$INSTALL_ROOT"/{bin,clash,ssh,logs}
"${SUDO[@]}" install -m 600 "$SSH_KEY_SOURCE" "$INSTALL_ROOT/ssh/cloud_key"
"${SUDO[@]}" install -m 755 "$CLASH_CORE_SOURCE" "$INSTALL_ROOT/clash/CrashCore"
"${SUDO[@]}" install -m 644 "$CLASH_CONFIG_SOURCE" "$INSTALL_ROOT/clash/config.yaml"
"${SUDO[@]}" install -m 644 "$CLASH_SOURCE_DIR/geoip.dat" "$INSTALL_ROOT/clash/geoip.dat"
"${SUDO[@]}" install -m 644 "$CLASH_SOURCE_DIR/geosite.dat" "$INSTALL_ROOT/clash/geosite.dat"
"${SUDO[@]}" chown -R "$TARGET_USER:$TARGET_GROUP" "$INSTALL_ROOT"

# Keep Clash ports in sync with env.
set_yaml_scalar "$INSTALL_ROOT/clash/config.yaml" "port" "${CLASH_HTTP_PORT}"
set_yaml_scalar "$INSTALL_ROOT/clash/config.yaml" "socks-port" "${CLASH_SOCKS_PORT}"
set_yaml_scalar "$INSTALL_ROOT/clash/config.yaml" "external-controller" "\"127.0.0.1:${CLASH_API_PORT}\""

log "Installing zsh plugins/themes for $TARGET_USER"
run_as_target "mkdir -p '$TARGET_HOME/.zsh/plugins' '$TARGET_HOME/.zsh/themes'"
run_as_target "[[ -d '$TARGET_HOME/.zsh/plugins/zsh-autosuggestions/.git' ]] || git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions '$TARGET_HOME/.zsh/plugins/zsh-autosuggestions' || true"
run_as_target "[[ -d '$TARGET_HOME/.zsh/plugins/zsh-syntax-highlighting/.git' ]] || git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting '$TARGET_HOME/.zsh/plugins/zsh-syntax-highlighting' || true"
run_as_target "[[ -d '$TARGET_HOME/.zsh/plugins/zsh-completions/.git' ]] || git clone --depth=1 https://github.com/zsh-users/zsh-completions '$TARGET_HOME/.zsh/plugins/zsh-completions' || true"
run_as_target "[[ -d '$TARGET_HOME/.zsh/themes/powerlevel10k/.git' ]] || git clone --depth=1 https://github.com/romkatv/powerlevel10k '$TARGET_HOME/.zsh/themes/powerlevel10k' || true"
write_managed_zsh_block

if command -v zsh >/dev/null 2>&1; then
  log "Setting default shell to zsh for $TARGET_USER"
  "${SUDO[@]}" usermod -s "$(command -v zsh)" "$TARGET_USER" || true
fi

log "Writing profile-wide proxy env"
"${SUDO[@]}" tee /etc/profile.d/lab-proxy.sh >/dev/null <<PROXY
export CLASH_HTTP_PORT=${CLASH_HTTP_PORT}
export CLASH_SOCKS_PORT=${CLASH_SOCKS_PORT}
export CLASH_API_PORT=${CLASH_API_PORT}
export http_proxy=http://127.0.0.1:${CLASH_HTTP_PORT}
export https_proxy=http://127.0.0.1:${CLASH_HTTP_PORT}
export HTTP_PROXY=http://127.0.0.1:${CLASH_HTTP_PORT}
export HTTPS_PROXY=http://127.0.0.1:${CLASH_HTTP_PORT}
export ftp_proxy=http://127.0.0.1:${CLASH_HTTP_PORT}
export FTP_PROXY=http://127.0.0.1:${CLASH_HTTP_PORT}
export all_proxy=socks5://127.0.0.1:${CLASH_SOCKS_PORT}
export ALL_PROXY=socks5://127.0.0.1:${CLASH_SOCKS_PORT}
PROXY
"${SUDO[@]}" chmod 644 /etc/profile.d/lab-proxy.sh

log "Writing systemd services"
AUTOSSH_BIN="$(command -v autossh)"
"${SUDO[@]}" tee /etc/systemd/system/lab-clash.service >/dev/null <<SERVICE
[Unit]
Description=Lab Clash (Mihomo)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
Group=${TARGET_GROUP}
WorkingDirectory=${INSTALL_ROOT}/clash
ExecStart=${INSTALL_ROOT}/clash/CrashCore -d ${INSTALL_ROOT}/clash -f ${INSTALL_ROOT}/clash/config.yaml
Restart=always
RestartSec=5
Environment=TZ=${HOST_TIMEZONE}
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
SERVICE

"${SUDO[@]}" tee /etc/systemd/system/lab-autossh.service >/dev/null <<SERVICE
[Unit]
Description=Lab AutoSSH Reverse Tunnel
After=network-online.target ${SSH_SERVICE}.service
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
Group=${TARGET_GROUP}
Environment=AUTOSSH_GATETIME=0
Environment=AUTOSSH_POLL=30
Environment=AUTOSSH_LOGFILE=${INSTALL_ROOT}/logs/autossh.log
ExecStart=${AUTOSSH_BIN} -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -R 0.0.0.0:${REVERSE_PORT}:127.0.0.1:${LOCAL_SSH_PORT} -p ${CLOUD_SSH_PORT} -i ${INSTALL_ROOT}/ssh/cloud_key ${CLOUD_USER}@${CLOUD_HOST}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable --now lab-clash.service
"${SUDO[@]}" systemctl enable --now lab-autossh.service

log "Checking reverse tunnel on cloud host"
for _ in {1..10}; do
  if run_cloud_cmd "ss -tnl | grep -E ':${REVERSE_PORT}\\s'" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if run_cloud_cmd "ss -tnl | grep -E ':${REVERSE_PORT}\\s'" >/dev/null 2>&1; then
  log "Done. Connect from local machine: ssh -p ${REVERSE_PORT} ${TARGET_USER}@${CLOUD_HOST}"
else
  echo "[WARN] Tunnel port ${REVERSE_PORT} not detected on cloud host."
  echo "       Check cloud sshd_config: AllowTcpForwarding yes, GatewayPorts clientspecified"
fi

log "Service status"
"${SUDO[@]}" systemctl --no-pager --full status lab-clash.service | sed -n '1,12p' || true
"${SUDO[@]}" systemctl --no-pager --full status lab-autossh.service | sed -n '1,12p' || true

cat <<EOT

Next checks:
1) ssh -p ${REVERSE_PORT} ${TARGET_USER}@${CLOUD_HOST}
2) On host, check clash: systemctl status lab-clash.service
3) Check autossh log: tail -n 50 ${INSTALL_ROOT}/logs/autossh.log
4) Re-login to load zsh changes, then run: echo \$SHELL && echo \$http_proxy

EOT
