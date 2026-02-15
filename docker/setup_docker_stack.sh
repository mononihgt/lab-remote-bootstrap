#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ERROR] docker/setup_docker_stack.sh must run on the Linux host machine."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${1:-${SCRIPT_DIR}/docker-stack.env}"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/my-docker-lab}"
DOCKER_CONTEXT_DIR="${DOCKER_CONTEXT_DIR:-$PROJECT_ROOT/docker_context}"
CLASH_SOURCE_DIR="${CLASH_SOURCE_DIR:-}"
CLASH_CORE_FILE="${CLASH_CORE_FILE:-}"
CLASH_CONFIG_FILE="${CLASH_CONFIG_FILE:-config.yaml}"
CLASH_CONFIG_URL="${CLASH_CONFIG_URL:-}"
WORKSPACE_HOST_DIR="${WORKSPACE_HOST_DIR:-$HOME/my_project}"
SSH_KEY_SOURCE="${SSH_KEY_SOURCE:-$HOME/.ssh/id_ed25519_autossh}"
CLOUD_USER="${CLOUD_USER:-}"
CLOUD_HOST="${CLOUD_HOST:-}"
CLOUD_SSH_PORT="${CLOUD_SSH_PORT:-22}"
REVERSE_PORT="${REVERSE_PORT:-2223}"
IMAGE_NAME="${IMAGE_NAME:-my-lab-cpu}"
CONTAINER_NAME="${CONTAINER_NAME:-lab-cpu-container}"
ROOT_PASSWORD="${ROOT_PASSWORD:-rootpassword}"
CONTAINER_TIMEZONE="${CONTAINER_TIMEZONE:-Asia/Shanghai}"
CLASH_HTTP_PORT="${CLASH_HTTP_PORT:-7890}"
CLASH_SOCKS_PORT="${CLASH_SOCKS_PORT:-7891}"
CLASH_API_PORT="${CLASH_API_PORT:-9090}"
TMP_FILES=()

normalize_clash_source_dir() {
  local path="${1:-}"
  if [[ -z "$path" || "$path" == "/path/to/lab-remote-bootstrap/assets/clash" ]]; then
    path="$ROOT_DIR/assets/clash"
  elif [[ "$path" != /* ]]; then
    path="$ROOT_DIR/$path"
  fi
  printf '%s\n' "$path"
}

CLASH_SOURCE_DIR="$(normalize_clash_source_dir "$CLASH_SOURCE_DIR")"

if [[ -z "$CLOUD_USER" || -z "$CLOUD_HOST" ]]; then
  echo "[ERROR] CLOUD_USER and CLOUD_HOST must be set in $CONFIG_FILE."
  exit 1
fi

if [[ $EUID -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

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

cleanup_tmp_files() {
  local file_path
  for file_path in "${TMP_FILES[@]:-}"; do
    [[ -n "$file_path" ]] && rm -f "$file_path" >/dev/null 2>&1 || true
  done
}

download_to_file() {
  local url="$1"
  local output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO "$output" "$url"
    return 0
  fi
  echo "[ERROR] Neither curl nor wget is available to download clash config URL."
  exit 1
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
  if [[ -n "$CLASH_CONFIG_URL" ]]; then
    local tmp_cfg
    tmp_cfg="$(mktemp "${TMPDIR:-/tmp}/clash-config.XXXXXX.yaml")"
    download_to_file "$CLASH_CONFIG_URL" "$tmp_cfg"
    TMP_FILES+=("$tmp_cfg")
    printf '%s\n' "$tmp_cfg"
    return 0
  fi
  local config_path="${CLASH_CONFIG_FILE:-config.yaml}"
  [[ "$config_path" = /* ]] || config_path="$dir/$config_path"
  printf '%s\n' "$config_path"
}

trap cleanup_tmp_files EXIT

CLASH_CORE_SOURCE="$(resolve_clash_core "$CLASH_SOURCE_DIR" || true)"
CLASH_CONFIG_SOURCE="$(resolve_clash_config "$CLASH_SOURCE_DIR")"
if [[ -z "$CLASH_CORE_SOURCE" ]]; then
  echo "[ERROR] No clash core binary found in $CLASH_SOURCE_DIR"
  echo "        Provide CrashCore/mihomo*/clash* (non-.gz), or set CLASH_CORE_FILE in env."
  exit 1
fi

run_cloud_cmd() {
  ssh -i "$SSH_KEY_SOURCE" \
    -p "$CLOUD_SSH_PORT" \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=accept-new \
    "${CLOUD_USER}@${CLOUD_HOST}" "$@"
}

log "Checking required local files"
need_file "$SSH_KEY_SOURCE"
need_file "$CLASH_CORE_SOURCE"
need_file "$CLASH_CONFIG_SOURCE"
need_file "$CLASH_SOURCE_DIR/geoip.dat"
need_file "$CLASH_SOURCE_DIR/geosite.dat"

log "Checking access to cloud host"
if ! run_cloud_cmd "echo cloud-ok" >/dev/null; then
  echo "[ERROR] Cannot access ${CLOUD_USER}@${CLOUD_HOST}:${CLOUD_SSH_PORT} using key: $SSH_KEY_SOURCE"
  echo "        Verify key login first, then rerun this script."
  exit 1
fi

log "Installing Docker if needed"
if ! command -v docker >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y docker.io
fi

if command -v systemctl >/dev/null 2>&1; then
  "${SUDO[@]}" systemctl enable docker >/dev/null 2>&1 || true
  "${SUDO[@]}" systemctl start docker >/dev/null 2>&1 || true
fi

log "Preparing project directories"
mkdir -p "$PROJECT_ROOT/ssh_keys" "$PROJECT_ROOT/clash" "$DOCKER_CONTEXT_DIR" "$WORKSPACE_HOST_DIR"
cp "$SSH_KEY_SOURCE" "$PROJECT_ROOT/ssh_keys/cloud_key"
chmod 600 "$PROJECT_ROOT/ssh_keys/cloud_key"

cp "$CLASH_CORE_SOURCE" "$PROJECT_ROOT/clash/CrashCore"
cp "$CLASH_CONFIG_SOURCE" "$PROJECT_ROOT/clash/config.yaml"
cp "$CLASH_SOURCE_DIR/geoip.dat" "$PROJECT_ROOT/clash/geoip.dat"
cp "$CLASH_SOURCE_DIR/geosite.dat" "$PROJECT_ROOT/clash/geosite.dat"
chmod +x "$PROJECT_ROOT/clash/CrashCore"

log "Writing Dockerfile"
cat > "$DOCKER_CONTEXT_DIR/Dockerfile" <<'DOCKERFILE'
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y \
    autossh \
    ca-certificates \
    curl \
    fd-find \
    fzf \
    git \
    iputils-ping \
    openssh-server \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    ripgrep \
    sudo \
    tmux \
    tzdata \
    vim \
    wget \
    zsh \
    zsh-autosuggestions \
    zsh-syntax-highlighting \
    zsh-completions \
    && if apt-cache show fastfetch >/dev/null 2>&1; then apt-get install -y fastfetch; fi \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/run/sshd /root/.ssh /opt/clash /workspace
RUN git clone --depth=1 https://github.com/romkatv/powerlevel10k.git /root/.powerlevel10k || true
RUN chsh -s /usr/bin/zsh root || true

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
WORKDIR /workspace
EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
DOCKERFILE

log "Writing container entrypoint"
cat > "$DOCKER_CONTEXT_DIR/entrypoint.sh" <<'ENTRYPOINT'
#!/usr/bin/env bash
set -euo pipefail

: "${CLOUD_USER:?CLOUD_USER is required}"
: "${CLOUD_HOST:?CLOUD_HOST is required}"
: "${CLOUD_SSH_PORT:=22}"
: "${REVERSE_PORT:=2223}"
: "${ROOT_PASSWORD:=rootpassword}"
: "${CONTAINER_TIMEZONE:=Asia/Shanghai}"
: "${CLASH_HTTP_PORT:=7890}"
: "${CLASH_SOCKS_PORT:=7891}"
: "${CLASH_API_PORT:=9090}"

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

configure_clash_ports() {
  local cfg="/opt/clash/config.yaml"
  [[ -f "$cfg" ]] || return 0
  set_yaml_scalar "$cfg" "port" "${CLASH_HTTP_PORT}"
  set_yaml_scalar "$cfg" "socks-port" "${CLASH_SOCKS_PORT}"
  set_yaml_scalar "$cfg" "external-controller" "\"127.0.0.1:${CLASH_API_PORT}\""
}

write_zshrc() {
  cat > /root/.zshrc <<ZSHRC
# ---- Lab Docker managed zshrc ----
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

# history setup
HISTFILE=\$HOME/.zhistory
SAVEHIST=5000
HISTSIZE=5000
setopt share_history
setopt hist_expire_dups_first
setopt hist_ignore_dups
setopt hist_verify

# completion from history (arrow up/down)
bindkey '^[[A' history-search-backward
bindkey '^[[B' history-search-forward

if [[ -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
fi
if [[ -r /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

if [[ -r /root/.powerlevel10k/powerlevel10k.zsh-theme ]]; then
  export POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true
  source /root/.powerlevel10k/powerlevel10k.zsh-theme
  [[ -f ~/.p10k.zsh ]] && source ~/.p10k.zsh
else
  PROMPT='%F{cyan}%n@%m%f:%F{yellow}%~%f %# '
fi

[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local

if [[ -o interactive ]] && command -v fastfetch >/dev/null 2>&1; then
  fastfetch
fi
ZSHRC
  chmod 644 /root/.zshrc
}

ln -snf "/usr/share/zoneinfo/${CONTAINER_TIMEZONE}" /etc/localtime || true
echo "${CONTAINER_TIMEZONE}" > /etc/timezone || true

echo "root:${ROOT_PASSWORD}" | chpasswd

# Ensure SSH server settings are explicit.
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
grep -q '^PermitRootLogin' /etc/ssh/sshd_config || echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config
grep -q '^PasswordAuthentication' /etc/ssh/sshd_config || echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config

if [[ ! -f /root/.ssh/cloud_key ]]; then
  echo "[ERROR] /root/.ssh/cloud_key not found"
  exit 1
fi

cp /root/.ssh/cloud_key /root/id_key_internal
chmod 600 /root/id_key_internal

mkdir -p /var/log
touch /var/log/clash.log
configure_clash_ports
write_zshrc

if [[ -x /opt/clash/CrashCore && -f /opt/clash/config.yaml ]]; then
  pkill -f '/opt/clash/CrashCore' >/dev/null 2>&1 || true
  nohup /opt/clash/CrashCore -d /opt/clash -f /opt/clash/config.yaml >/var/log/clash.log 2>&1 &
else
  echo "[WARN] Clash assets missing, skip Clash startup"
fi

cat > /etc/profile.d/proxy.sh <<PROXY
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
chmod 644 /etc/profile.d/proxy.sh

service ssh start

echo "[INFO] Starting AutoSSH reverse tunnel to ${CLOUD_USER}@${CLOUD_HOST}:${CLOUD_SSH_PORT}"
exec autossh -M 0 \
  -o "ServerAliveInterval 30" \
  -o "ServerAliveCountMax 3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -N \
  -R "0.0.0.0:${REVERSE_PORT}:127.0.0.1:22" \
  -p "${CLOUD_SSH_PORT}" \
  -i /root/id_key_internal \
  "${CLOUD_USER}@${CLOUD_HOST}"
ENTRYPOINT
chmod +x "$DOCKER_CONTEXT_DIR/entrypoint.sh"

log "Building Docker image: $IMAGE_NAME"
"${SUDO[@]}" docker build -t "$IMAGE_NAME" "$DOCKER_CONTEXT_DIR"

if "${SUDO[@]}" docker ps -a --format "{{.Names}}" | grep -Fxq "$CONTAINER_NAME"; then
  log "Removing existing container: $CONTAINER_NAME"
  "${SUDO[@]}" docker rm -f "$CONTAINER_NAME" >/dev/null
fi

log "Starting container"
"${SUDO[@]}" docker run -d \
  --name "$CONTAINER_NAME" \
  --restart always \
  -e CLOUD_USER="$CLOUD_USER" \
  -e CLOUD_HOST="$CLOUD_HOST" \
  -e CLOUD_SSH_PORT="$CLOUD_SSH_PORT" \
  -e REVERSE_PORT="$REVERSE_PORT" \
  -e ROOT_PASSWORD="$ROOT_PASSWORD" \
  -e CONTAINER_TIMEZONE="$CONTAINER_TIMEZONE" \
  -e CLASH_HTTP_PORT="$CLASH_HTTP_PORT" \
  -e CLASH_SOCKS_PORT="$CLASH_SOCKS_PORT" \
  -e CLASH_API_PORT="$CLASH_API_PORT" \
  -v "$PROJECT_ROOT/ssh_keys/cloud_key:/root/.ssh/cloud_key:ro" \
  -v "$PROJECT_ROOT/clash:/opt/clash" \
  -v "$WORKSPACE_HOST_DIR:/workspace" \
  "$IMAGE_NAME" >/dev/null

log "Checking reverse tunnel on cloud host"
for _ in {1..10}; do
  if run_cloud_cmd "ss -tnl | grep -E ':${REVERSE_PORT}\\s'" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if run_cloud_cmd "ss -tnl | grep -E ':${REVERSE_PORT}\\s'" >/dev/null 2>&1; then
  log "Done. Connect from local machine: ssh -p ${REVERSE_PORT} root@${CLOUD_HOST}"
else
  echo "[WARN] Tunnel port ${REVERSE_PORT} not detected on cloud host."
  echo "       Check cloud sshd_config: AllowTcpForwarding yes, GatewayPorts clientspecified"
  echo "       Also ensure cloud firewall/security-group allows TCP ${REVERSE_PORT}."
fi

log "Container logs"
"${SUDO[@]}" docker logs --tail 30 "$CONTAINER_NAME" || true

cat <<EOT

Next checks:
1) ssh -p ${REVERSE_PORT} root@${CLOUD_HOST}
2) Inside container, run: curl -I https://www.google.com
3) View Clash log: ${SUDO[*]:-} docker exec -it ${CONTAINER_NAME} tail -n 50 /var/log/clash.log
4) Confirm shell/proxy: ${SUDO[*]:-} docker exec -it ${CONTAINER_NAME} zsh -lc 'echo $SHELL && echo $http_proxy'

EOT
