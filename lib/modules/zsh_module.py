#!/usr/bin/env python3
"""Zsh configuration module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import BaseModule
from utils import print_error, print_info, print_success, run_ssh_command


class ZshModule(BaseModule):
    """Zsh terminal configuration module."""

    def validate(self) -> bool:
        """Validate Zsh module prerequisites."""
        # Check if remote server is accessible
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')

        if not host or not user:
            print_error("Cloud host and user must be configured")
            return False

        return True

    def deploy(self) -> bool:
        """Deploy Zsh configuration."""
        print_info("Deploying Zsh configuration...")

        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('autossh.identity_file')
        reverse_port = self.config.get('cloud.reverse_port', 2223)

        # Install tools
        if not self._install_tools(host, user, identity_file, reverse_port):
            print_error("Failed to install tools")
            return False

        # Install plugins
        if not self._install_plugins(host, user, identity_file, reverse_port):
            print_error("Failed to install plugins")
            return False

        # Generate and write config
        config_block = self._generate_config_block()
        if not self._write_config(host, user, identity_file, reverse_port, config_block):
            print_error("Failed to write config")
            return False

        print_success("Zsh configuration deployed")
        return True

    def rollback(self) -> bool:
        """Rollback Zsh configuration."""
        print_info("Zsh rollback not implemented")
        return True

    def _install_tools(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Install command-line tools."""
        print_info("Installing command-line tools...")

        # Detect package manager
        detect_cmd = """
if command -v apt-get >/dev/null 2>&1; then echo apt
elif command -v dnf >/dev/null 2>&1; then echo dnf
elif command -v yum >/dev/null 2>&1; then echo yum
elif command -v pacman >/dev/null 2>&1; then echo pacman
elif command -v zypper >/dev/null 2>&1; then echo zypper
elif command -v apk >/dev/null 2>&1; then echo apk
else echo unknown
fi
"""
        returncode, stdout, _ = run_ssh_command(host, user, detect_cmd, identity_file, port)
        if returncode != 0:
            return False

        pkg_manager = stdout.strip()
        self.log(f"Detected package manager: {pkg_manager}")

        # Define tools to install (best-effort)
        tools = []
        if pkg_manager == 'apt':
            tools = ['fzf', 'fd-find', 'eza', 'bat', 'tldr', 'fastfetch']
        elif pkg_manager in ['dnf', 'yum']:
            tools = ['fzf', 'fd-find', 'eza', 'bat', 'tldr', 'fastfetch']
        elif pkg_manager == 'pacman':
            tools = ['fzf', 'fd', 'eza', 'bat', 'tldr', 'fastfetch']
        elif pkg_manager == 'apk':
            tools = ['fzf', 'fd', 'eza', 'bat', 'tldr-pages', 'fastfetch']
        else:
            print_info("Unknown package manager, skipping tool installation")
            return True

        # Install each tool (best-effort)
        install_cmds = {
            'apt': 'sudo apt-get install -y',
            'dnf': 'sudo dnf install -y',
            'yum': 'sudo yum install -y',
            'pacman': 'sudo pacman -S --noconfirm',
            'zypper': 'sudo zypper install -y',
            'apk': 'sudo apk add',
        }

        install_cmd = install_cmds.get(pkg_manager)
        if not install_cmd:
            return True

        for tool in tools:
            cmd = f"{install_cmd} {tool} 2>/dev/null || true"
            self.log(f"Installing {tool}")
            run_ssh_command(host, user, cmd, identity_file, port)

        print_success("Tools installation completed (best-effort)")
        return True

    def _install_plugins(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Install Zsh plugins."""
        print_info("Installing Zsh plugins...")

        plugins_dir = "$HOME/.zsh/plugins"
        themes_dir = "$HOME/.zsh/themes"

        # Create directories
        cmd = f"mkdir -p {plugins_dir} {themes_dir}"
        run_ssh_command(host, user, cmd, identity_file, port)

        # Install zsh-autosuggestions
        cmd = f"""
if [ ! -d {plugins_dir}/zsh-autosuggestions ]; then
    git clone https://github.com/zsh-users/zsh-autosuggestions {plugins_dir}/zsh-autosuggestions
fi
"""
        run_ssh_command(host, user, cmd, identity_file, port)

        # Install zsh-syntax-highlighting
        cmd = f"""
if [ ! -d {plugins_dir}/zsh-syntax-highlighting ]; then
    git clone https://github.com/zsh-users/zsh-syntax-highlighting {plugins_dir}/zsh-syntax-highlighting
fi
"""
        run_ssh_command(host, user, cmd, identity_file, port)

        # Install zsh-completions
        cmd = f"""
if [ ! -d {plugins_dir}/zsh-completions ]; then
    git clone https://github.com/zsh-users/zsh-completions {plugins_dir}/zsh-completions
fi
"""
        run_ssh_command(host, user, cmd, identity_file, port)

        # Install powerlevel10k
        cmd = f"""
if [ ! -d {themes_dir}/powerlevel10k ]; then
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git {themes_dir}/powerlevel10k
fi
"""
        run_ssh_command(host, user, cmd, identity_file, port)

        print_success("Zsh plugins installed")
        return True

    def _generate_config_block(self) -> str:
        """Generate Zsh configuration block."""
        clash_http_port = self.config.get('clash.http_port', 7890)
        clash_socks_port = self.config.get('clash.socks_port', 7891)
        clash_api_port = self.config.get('clash.api_port', 9090)

        zsh_config = self.config.get('zsh.custom_config', {})
        autosuggestions_style = zsh_config.get('autosuggestions_style', 'fg=240')
        fzf_theme = zsh_config.get('fzf_theme', {})
        bat_theme = zsh_config.get('bat_theme', 'tokyonight_night')

        # Extract fzf colors
        fg = fzf_theme.get('fg', '#CBE0F0')
        bg = fzf_theme.get('bg', '#011628')
        bg_highlight = fzf_theme.get('bg_highlight', '#143652')
        purple = fzf_theme.get('purple', '#B388FF')
        blue = fzf_theme.get('blue', '#06BCE4')
        cyan = fzf_theme.get('cyan', '#2CF9ED')

        config = f"""# >>> lab-remote-bootstrap >>>

# Proxy environment variables
export CLASH_HTTP_PORT={clash_http_port}
export CLASH_SOCKS_PORT={clash_socks_port}
export CLASH_API_PORT={clash_api_port}

export http_proxy="http://127.0.0.1:{clash_http_port}"
export https_proxy="http://127.0.0.1:{clash_http_port}"
export HTTP_PROXY="http://127.0.0.1:{clash_http_port}"
export HTTPS_PROXY="http://127.0.0.1:{clash_http_port}"
export ftp_proxy="http://127.0.0.1:{clash_http_port}"
export FTP_PROXY="http://127.0.0.1:{clash_http_port}"
export all_proxy="socks5://127.0.0.1:{clash_socks_port}"
export ALL_PROXY="socks5://127.0.0.1:{clash_socks_port}"

# Zsh configuration
if [[ -d $HOME/.zsh/plugins/zsh-completions/src ]]; then
  fpath=($HOME/.zsh/plugins/zsh-completions/src $fpath)
fi
autoload -Uz compinit
compinit
zstyle ':completion:*' menu select

HISTFILE=$HOME/.zhistory
SAVEHIST=5000
HISTSIZE=5000
setopt share_history
setopt hist_expire_dups_first
setopt hist_ignore_dups
setopt hist_verify

bindkey '^[[A' history-search-backward
bindkey '^[[B' history-search-forward

# zsh-autosuggestions
if [[ -r $HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source $HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
  ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='{autosuggestions_style}'
fi

# zsh-syntax-highlighting
if [[ -r $HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source $HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# zsh-completions
if [[ -r $HOME/.zsh/plugins/zsh-completions/zsh-completions.plugin.zsh ]]; then
  source $HOME/.zsh/plugins/zsh-completions/zsh-completions.plugin.zsh
fi

# fzf
if command -v fzf >/dev/null 2>&1; then
  if fzf --help 2>/dev/null | grep -q -- '--zsh'; then
    eval "$(fzf --zsh)" 2>/dev/null || true
  else
    [[ -r $HOME/.fzf.zsh ]] && source $HOME/.fzf.zsh
    [[ -r /usr/share/doc/fzf/examples/key-bindings.zsh ]] && source /usr/share/doc/fzf/examples/key-bindings.zsh
    [[ -r /usr/share/doc/fzf/examples/completion.zsh ]] && source /usr/share/doc/fzf/examples/completion.zsh
    [[ -r /usr/share/fzf/key-bindings.zsh ]] && source /usr/share/fzf/key-bindings.zsh
    [[ -r /usr/share/fzf/completion.zsh ]] && source /usr/share/fzf/completion.zsh
  fi

  # fd integration
  if command -v fd >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND='fd --hidden --strip-cwd-prefix --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fd --type=d --hidden --strip-cwd-prefix --exclude .git'
  elif command -v fdfind >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND='fdfind --hidden --strip-cwd-prefix --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fdfind --type=d --hidden --strip-cwd-prefix --exclude .git'
  fi

  # compgen functions
  _fzf_compgen_path() {{
    if command -v fd >/dev/null 2>&1; then
      fd --hidden --exclude .git . "$1"
    elif command -v fdfind >/dev/null 2>&1; then
      fdfind --hidden --exclude .git . "$1"
    fi
  }}

  _fzf_compgen_dir() {{
    if command -v fd >/dev/null 2>&1; then
      fd --type=d --hidden --exclude .git . "$1"
    elif command -v fdfind >/dev/null 2>&1; then
      fdfind --type=d --hidden --exclude .git . "$1"
    fi
  }}

  # Custom theme
  fg="{fg}"
  bg="{bg}"
  bg_highlight="{bg_highlight}"
  purple="{purple}"
  blue="{blue}"
  cyan="{cyan}"
  export FZF_DEFAULT_OPTS="--color=fg:${{fg}},bg:${{bg}},hl:${{purple}},fg+:${{fg}},bg+:${{bg_highlight}},hl+:${{purple}},info:${{blue}},prompt:${{cyan}},pointer:${{cyan}},marker:${{cyan}},spinner:${{cyan}},header:${{cyan}}"
fi

# eza aliases
if command -v eza >/dev/null 2>&1; then
    alias ls='eza --icons=always --group-directories-first --git --no-filesize --no-time --no-user --no-permissions'
    alias l='eza -F --icons=always --group-directories-first'
    alias ll='eza -lh --icons=always --git --group-directories-first'
    alias la='eza -aF --icons=always --group-directories-first'
    alias lla='eza -lah --icons=always --git --group-directories-first'
elif command -v exa >/dev/null 2>&1; then
    alias ls='exa --icons --group-directories-first'
    alias ll='exa -lh --icons --git --group-directories-first'
    alias la='exa -aF --icons --group-directories-first'
    alias l='exa -F --icons --group-directories-first'
else
    alias ll='ls -alF'
    alias la='ls -A'
    alias l='ls -CF'
fi

# bat
if command -v bat >/dev/null 2>&1; then
    export BAT_THEME="{bat_theme}"
fi

# tldr
if command -v tldr >/dev/null 2>&1; then
    alias help='tldr'
fi

# powerlevel10k
if [[ -r $HOME/.zsh/themes/powerlevel10k/powerlevel10k.zsh-theme ]]; then
  export POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true
  source $HOME/.zsh/themes/powerlevel10k/powerlevel10k.zsh-theme
  [[ -f $HOME/.p10k.zsh ]] && source $HOME/.p10k.zsh
fi

# fastfetch
if [[ -o interactive ]] && command -v fastfetch >/dev/null 2>&1; then
    if [[ $COLUMNS -ge 110 ]]; then
        fastfetch --disable-linewrap false
    else
        fastfetch --logo-position top --disable-linewrap false
    fi
fi

# Local customizations
[[ -f $HOME/.zshrc.local ]] && source $HOME/.zshrc.local

# <<< lab-remote-bootstrap <<<
"""
        return config

    def _write_config(self, host: str, user: str, identity_file: str, port: int, config_block: str) -> bool:
        """Write config block to .zshrc."""
        print_info("Writing Zsh configuration...")

        # Escape single quotes and backslashes for shell
        escaped_config = config_block.replace("\\", "\\\\").replace("'", "'\\''")

        # Write config using Python heredoc-style script
        write_cmd = f"""
python3 << 'PYTHON_EOF'
import re

zshrc_path = '{{}}/{{.}}zshrc'.format(__import__('os').path.expanduser('~'))
start_marker = '# >>> lab-remote-bootstrap >>>'
end_marker = '# <<< lab-remote-bootstrap <<<'

try:
    with open(zshrc_path, 'r') as f:
        content = f.read()
except FileNotFoundError:
    content = ''

# Remove old managed block
pattern = re.compile(
    re.escape(start_marker) + r'.*?' + re.escape(end_marker),
    re.DOTALL
)
content = pattern.sub('', content).strip()

# Append new block
new_block = '''
{escaped_config}
'''

with open(zshrc_path, 'w') as f:
    f.write(content + new_block)

print('Configuration written to', zshrc_path)
PYTHON_EOF
"""

        returncode, stdout, stderr = run_ssh_command(host, user, write_cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to write config: {stderr}")
            return False

        print_success("Zsh configuration written to ~/.zshrc")
        return True
