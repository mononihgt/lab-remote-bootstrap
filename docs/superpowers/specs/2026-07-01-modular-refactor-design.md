# Lab Remote Bootstrap 模块化重构设计

**日期**: 2026-07-01  
**状态**: 设计阶段  
**设计方案**: 方案 2 - 模块化重构

## 概述

对 lab-remote-bootstrap 项目进行架构重构，实现以下目标：

1. **Zsh 配置同步**：将本地的个性化 zsh 配置（eza、fzf、bat、tldr）同步到服务器
2. **Clash 订阅管理**：支持 Base64 订阅转换，提供多模板选择
3. **Web 管理界面**：统一管理 Clash Dashboard 和订阅，通过 Flask 实现
4. **健康检查系统**：提供基础服务检查和连接测试
5. **模块化架构**：统一配置格式（YAML），CLI 工具，可维护的代码结构

## 核心改进

### 改进 1：Zsh 配置同步

**目标**：复刻本地 `.zshrc` 的插件配置到服务器，保持个性化体验。

**同步内容**：
- zsh-autosuggestions 高亮样式：`ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=240'`
- 完整的 eza 别名配置（带 icons、git、分组）
- fzf 自定义主题（保持本地的蓝紫色调）
- fzf compgen 函数（集成 fd）
- bat 主题：`tokyonight_night`
- tldr 别名：`help='tldr'`
- fastfetch 根据终端宽度自适应启动

**新增工具**：
- bat（语法高亮的 cat 替代）
- tldr（简化的 man 页面）

**移除工具**：
- zoxide（用户本地未使用）

**降级策略**：
- eza → exa → ls（根据可用性自动降级）
- fd → fdfind（根据包名适配）

### 改进 2：Clash 订阅管理

**订阅类型支持**：
- **YAML 订阅**：直接下载使用
- **Base64 订阅**：解码后转换为 Clash 配置

**订阅转换流程**：
```
订阅 URL → 下载 → 检测类型 → 转换 → 生成 config.yaml → 部署
```

**支持的协议**：
- vmess://
- ss:// (Shadowsocks)
- trojan://

**配置模板系统**：

提供三个预设模板，位于 `assets/clash/templates/`：

1. **minimal.yaml**：基础规则，仅包含代理选择和国内直连
2. **balanced.yaml**（推荐）：包含自动选择、基础广告拦截
3. **full.yaml**：完整规则集，包含更多分流规则

**模板占位符**：
- `{{proxies}}`：节点列表
- `{{proxy_names}}`：节点名称列表
- `{{generated_time}}`：生成时间
- `{{subscription_name}}`：订阅名称

**订阅存储**：

使用 JSON 文件 `/opt/lab-remote-stack/clash/subscriptions.json`：

```json
{
  "version": "1.0",
  "active": "主力订阅",
  "subscriptions": [
    {
      "name": "主力订阅",
      "url": "https://example.com/sub",
      "type": "base64",
      "template": "balanced",
      "added_at": "2026-07-01T10:30:00Z",
      "last_update": "2026-07-01T14:20:00Z",
      "node_count": 25,
      "status": "active"
    }
  ]
}
```

### 改进 3：Web 管理界面

**技术栈**：
- 后端：Flask 2.x + Flask-CORS
- 前端：原生 JavaScript + Alpine.js
- 样式：Catppuccin Mocha 配色

**功能模块**：

1. **Clash Dashboard 区域**
   - 通过 iframe 嵌入 MetaCubeX Dashboard
   - 实时显示代理状态和流量统计

2. **订阅管理区域**
   - 订阅列表（查看、激活、更新、删除）
   - 添加订阅（名称、URL、模板选择）
   - 订阅详情（节点列表预览）

3. **系统状态区域**
   - 服务状态（Clash、AutoSSH）
   - 端口监听状态
   - 快速操作（重启、查看日志、健康检查）

**部署方式**：
- Flask 服务运行在远程服务器（systemd 管理）
- 监听 127.0.0.1:5000
- 通过本地脚本建立 SSH 隧道访问
- 无需额外认证（依赖 SSH 隧道保护）

### 改进 4：健康检查系统

**检查项目**（方案 B：基础 + 连接测试）：

1. **基础服务检查**
   - Clash 进程状态（PID、运行时间）
   - AutoSSH 隧道状态
   - 端口监听状态（HTTP/SOCKS/API）

2. **连接测试**
   - Clash API 可用性
   - HTTP 代理连通性（测试外网访问）
   - 反向隧道可达性（云服务器端口检查）

**输出格式**：
- 终端：彩色格式化输出（默认）
- JSON：用于脚本集成（`--json` 选项）

**集成点**：
- CLI：`lab-remote-ctl health`
- Web 界面：系统状态区域显示 + 手动触发按钮
- 部署后：自动运行验证

## 架构设计

### 项目目录结构

```
lab-remote-bootstrap/
├── README.md
├── assets/
│   └── clash/
│       ├── templates/          # 新增：订阅转换模板
│       │   ├── minimal.yaml
│       │   ├── balanced.yaml
│       │   └── full.yaml
│       ├── geoip.dat
│       └── geosite.dat
├── lib/                        # 新增：核心模块库
│   ├── config.py              # 统一配置管理
│   ├── deployer.py            # 主部署协调器
│   ├── modules/
│   │   ├── clash_module.py    # Clash 部署逻辑
│   │   ├── autossh_module.py  # AutoSSH 部署逻辑
│   │   ├── zsh_module.py      # Zsh 部署逻辑
│   │   └── web_module.py      # Web 部署逻辑
│   ├── subscription.py        # 订阅转换核心逻辑
│   ├── health.py              # 健康检查
│   └── utils.py               # 通用工具函数
├── cli/                        # 新增：CLI 工具
│   └── lab-remote-ctl         # 主命令行工具（Python）
├── web/                        # 新增：Web 界面
│   ├── app.py                 # Flask 应用
│   ├── templates/
│   │   └── index.html         # 单页面应用
│   └── static/
│       ├── style.css
│       └── app.js
├── scripts/                    # 重构：辅助脚本
│   ├── deploy.sh              # 简化的部署入口
│   ├── health_check.sh        # 健康检查脚本
│   └── migrate_config.py      # 配置迁移工具
├── config/                     # 新增：配置目录
│   ├── config.example.yaml    # 配置模板
│   └── config.schema.json     # 配置验证 schema
├── cloud/
│   └── prepare_cloud_reverse_ssh.sh
├── local/
│   └── open_dashboard.sh      # 重构：打开 Web 界面
└── docs/
    ├── migration-guide.md     # 新增：迁移指南
    └── superpowers/specs/
        └── 2026-07-01-modular-refactor-design.md
```

### 统一配置格式（config.yaml）

从多个 `.env` 文件迁移到单一的 YAML 配置：

```yaml
# 部署模式
deployment:
  mode: host  # host 或 docker

# 云服务器配置
cloud:
  host: cloud.example.com
  user: ubuntu
  reverse_port: 2223

# Clash 配置
clash:
  install_root: /opt/lab-remote-stack
  http_port: 7890
  socks_port: 7891
  api_port: 9090
  api_secret: ""
  
  # 订阅配置
  subscription:
    template: balanced  # minimal, balanced, full, 或自定义路径
    auto_update: false
    update_interval: 86400  # 秒

# AutoSSH 配置
autossh:
  identity_file: ~/.ssh/id_ed25519_autossh
  monitor_port: 20000

# Zsh 配置
zsh:
  enable_plugins: true
  custom_config:
    autosuggestions_style: "fg=240"
    fzf_theme:
      fg: "#CBE0F0"
      bg: "#011628"
      bg_highlight: "#143652"
      purple: "#B388FF"
      blue: "#06BCE4"
      cyan: "#2CF9ED"
    bat_theme: "tokyonight_night"
    eza_aliases: true
    tldr_alias: true
    fastfetch_on_startup: true

# Web 界面配置
web:
  enabled: true
  port: 5000
  bind: 127.0.0.1

# Docker 模式特有配置
docker:
  container_name: lab-remote-dev
  root_password: changeme
  host_ssh_port: 2222
```

**选择 YAML 的原因**：
- 支持注释，便于文档化配置
- 人类可读性更好
- 与 Clash 配置格式一致
- Python 有成熟的 YAML 库（PyYAML）

### CLI 工具设计（lab-remote-ctl）

**命令结构**：

```bash
lab-remote-ctl [全局选项] <命令> [命令选项]

全局选项：
  -c, --config PATH    指定配置文件路径（默认：./config/config.yaml）
  -v, --verbose        详细输出
  --help              显示帮助信息

命令：
  init                 初始化配置文件
  deploy              部署到远程服务器
  subscription        管理订阅（子命令）
  health              运行健康检查
  web                 管理 Web 服务（子命令）
  migrate             迁移旧配置到新格式
```

**核心命令详解**：

#### 1. init - 初始化配置

```bash
lab-remote-ctl init [--mode host|docker] [--interactive]
```

功能：交互式生成 config.yaml，验证必填项

#### 2. deploy - 部署服务

```bash
lab-remote-ctl deploy [--dry-run] [--skip-clash] [--skip-autossh] [--skip-zsh]
```

功能：根据 config.yaml 部署所有模块（Clash → AutoSSH → Zsh → Web）

#### 3. subscription - 订阅管理

```bash
lab-remote-ctl subscription <子命令>

子命令：
  add <name> <url>           添加订阅
  list                       列出所有订阅
  activate <name>            切换到指定订阅
  update <name>              更新指定订阅
  update-all                 更新所有订阅
  remove <name>              删除订阅
  show <name>                显示订阅详情
```

#### 4. health - 健康检查

```bash
lab-remote-ctl health [--json] [--check-connectivity]
```

功能：检查服务状态、端口监听、代理连通性

#### 5. web - Web 服务管理

```bash
lab-remote-ctl web <子命令>

子命令：
  start                启动 Web 服务
  stop                 停止 Web 服务
  restart              重启 Web 服务
  status               查看服务状态
  open                 打开 Web 界面（建立隧道 + 浏览器）
```

#### 6. migrate - 配置迁移

```bash
lab-remote-ctl migrate <旧配置文件.env>
```

功能：将旧的 .env 格式转换为新的 config.yaml

**技术实现**：
- 语言：Python 3.8+
- CLI 框架：Click（轻量、易用）
- 配置解析：PyYAML + jsonschema（验证）
- SSH 操作：Paramiko 或调用系统 ssh 命令
- 输出美化：Rich 库（彩色输出、进度条）

### 模块化架构

每个功能模块实现标准接口：

```python
class BaseModule:
    def validate(self) -> bool:
        """验证前置条件"""
        pass
    
    def deploy(self) -> bool:
        """执行部署"""
        pass
    
    def rollback(self) -> bool:
        """部署失败时回滚"""
        pass
```

**模块列表**：
- **clash_module.py**：Clash 安装、配置、服务管理
- **autossh_module.py**：AutoSSH 隧道设置
- **zsh_module.py**：Zsh 插件和工具安装、配置生成
- **web_module.py**：Flask 应用部署

### Web 应用架构

**后端（Flask）**：

API 端点设计：

```
GET    /api/subscriptions              # 获取订阅列表
POST   /api/subscriptions              # 添加订阅
GET    /api/subscriptions/<name>       # 获取订阅详情
PUT    /api/subscriptions/<name>       # 更新订阅
DELETE /api/subscriptions/<name>       # 删除订阅
POST   /api/subscriptions/<name>/activate   # 激活订阅
POST   /api/subscriptions/<name>/update     # 更新订阅

GET    /api/status                     # 获取系统状态
POST   /api/clash/restart              # 重启 Clash
GET    /api/clash/logs                 # 获取 Clash 日志

GET    /api/health                     # 健康检查
POST   /api/test-subscription          # 测试订阅链接

# Clash API 代理（避免跨域问题）
GET    /api/clash/proxies              # 代理 Clash API
GET    /api/clash/traffic              # 流量信息
```

**前端（单页面应用）**：

三个主要区域：
1. **Clash Dashboard**：iframe 嵌入 MetaCubeX Dashboard
2. **订阅管理**：列表、添加、详情、切换
3. **系统状态**：服务状态、快速操作

**UI 配色**：Catppuccin Mocha

```css
:root {
  --ctp-base: #1e1e2e;
  --ctp-surface0: #313244;
  --ctp-text: #cdd6f4;
  --ctp-mauve: #cba6f7;  /* 主要强调色 */
  --ctp-green: #a6e3a1;  /* 成功状态 */
  --ctp-yellow: #f9e2af; /* 警告 */
  --ctp-red: #f38ba8;    /* 危险 */
}
```

## 详细设计

### 订阅转换系统

**流程**：

```
1. 下载订阅 URL
2. 检测类型（YAML 或 Base64）
3. Base64 订阅：解码 → 解析节点 URI → 转换为 Clash proxies
4. 加载模板文件
5. 替换占位符（{{proxies}}, {{proxy_names}}）
6. 生成完整的 config.yaml
7. 备份旧配置
8. 部署新配置
9. 重启 Clash 服务
```

**类型检测逻辑**：

```python
def detect_subscription_type(content: str) -> str:
    # 1. 尝试解析为 YAML
    try:
        yaml.safe_load(content)
        return 'yaml'
    except:
        pass
    
    # 2. 检测 Base64 编码特征
    if re.match(r'^[A-Za-z0-9+/=\s]+$', content):
        try:
            decoded = base64.b64decode(content)
            if any(proto in decoded for proto in [b'vmess://', b'ss://', b'trojan://']):
                return 'base64'
        except:
            pass
    
    return 'unknown'
```

**支持的节点协议**：
- vmess:// (V2Ray)
- ss:// (Shadowsocks)
- trojan://

**模板示例（balanced.yaml）**：

```yaml
# Auto-generated at {{generated_time}}
# Subscription: {{subscription_name}}

port: 7890
socks-port: 7891
allow-lan: true
mode: rule
log-level: info
external-controller: 127.0.0.1:9090

proxies:
{{proxies}}

proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - "AUTO"
{{proxy_names}}
      - DIRECT

  - name: "AUTO"
    type: url-test
    proxies:
{{proxy_names}}
    url: 'http://www.gstatic.com/generate_204'
    interval: 300

rules:
  - DOMAIN-SUFFIX,cn,DIRECT
  - DOMAIN-KEYWORD,baidu,DIRECT
  - GEOIP,CN,DIRECT
  - DOMAIN-SUFFIX,ads.google.com,REJECT
  - DOMAIN-KEYWORD,analytics,REJECT
  - MATCH,PROXY
```

### Zsh 配置生成

**生成的配置块**（写入 `~/.zshrc` 的 managed block）：

```bash
# >>> lab-remote-bootstrap >>>

# 代理环境变量（动态注入）
export CLASH_HTTP_PORT=7890
export CLASH_SOCKS_PORT=7891
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export all_proxy="socks5://127.0.0.1:7891"

# zsh 基础配置
autoload -Uz compinit
compinit
HISTFILE=$HOME/.zhistory
SAVEHIST=5000
HISTSIZE=5000
setopt share_history hist_expire_dups_first hist_ignore_dups hist_verify

# zsh-autosuggestions
if [[ -r $HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source $HOME/.zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
  ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=240'
fi

# zsh-syntax-highlighting
if [[ -r $HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source $HOME/.zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# fzf
if command -v fzf >/dev/null 2>&1; then
  eval "$(fzf --zsh)" 2>/dev/null || true
  
  # fd 集成
  if command -v fd >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND='fd --hidden --strip-cwd-prefix --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fd --type=d --hidden --strip-cwd-prefix --exclude .git'
  elif command -v fdfind >/dev/null 2>&1; then
    export FZF_DEFAULT_COMMAND='fdfind --hidden --strip-cwd-prefix --exclude .git'
    export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
    export FZF_ALT_C_COMMAND='fdfind --type=d --hidden --strip-cwd-prefix --exclude .git'
  fi
  
  # compgen 函数
  _fzf_compgen_path() {
    if command -v fd >/dev/null 2>&1; then
      fd --hidden --exclude .git . "$1"
    elif command -v fdfind >/dev/null 2>&1; then
      fdfind --hidden --exclude .git . "$1"
    fi
  }
  
  _fzf_compgen_dir() {
    if command -v fd >/dev/null 2>&1; then
      fd --type=d --hidden --exclude .git . "$1"
    elif command -v fdfind >/dev/null 2>&1; then
      fdfind --type=d --hidden --exclude .git . "$1"
    fi
  }
  
  # 自定义主题（蓝紫色调）
  fg="#CBE0F0"
  bg="#011628"
  bg_highlight="#143652"
  purple="#B388FF"
  blue="#06BCE4"
  cyan="#2CF9ED"
  export FZF_DEFAULT_OPTS="--color=fg:${fg},bg:${bg},hl:${purple},fg+:${fg},bg+:${bg_highlight},hl+:${purple},info:${blue},prompt:${cyan},pointer:${cyan},marker:${cyan},spinner:${cyan},header:${cyan}"
fi

# eza 别名
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
    export BAT_THEME="tokyonight_night"
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

# 加载本地自定义配置
[[ -f $HOME/.zshrc.local ]] && source $HOME/.zshrc.local

# <<< lab-remote-bootstrap <<<
```

### 健康检查输出

**终端输出示例**：

```
╭─────────────────────────────────────────╮
│  🏥 Lab Remote Bootstrap 健康检查       │
╰─────────────────────────────────────────╯

📦 服务状态
  ✓ Clash 进程运行中 (PID: 12345, 运行时间: 2h 15m)
  ✓ AutoSSH 隧道已连接 (PID: 12346)

🌐 端口检查
  ✓ HTTP 代理端口 7890 监听中
  ✓ SOCKS 代理端口 7891 监听中
  ✓ API 端口 9090 监听中

🔗 连通性测试
  ✓ Clash API 可访问 (版本: 1.18.0)
  ✓ HTTP 代理连通性正常 (204 OK)
  ✓ 反向隧道可达 (云服务器: cloud.example.com:2223)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 所有检查通过 (7/7)
运行时间: 3.2s
```

### 配置迁移

**迁移映射表**：

```python
ENV_TO_YAML_MAPPING = {
    # 云服务器配置
    'CLOUD_HOST': 'cloud.host',
    'CLOUD_USER': 'cloud.user',
    'REVERSE_PORT': 'cloud.reverse_port',
    
    # Clash 配置
    'INSTALL_ROOT': 'clash.install_root',
    'CLASH_HTTP_PORT': 'clash.http_port',
    'CLASH_SOCKS_PORT': 'clash.socks_port',
    'CLASH_API_PORT': 'clash.api_port',
    'CLASH_CONFIG_URL': 'clash.subscription.url',
    
    # AutoSSH 配置
    'AUTOSSH_IDENTITY_FILE': 'autossh.identity_file',
    'AUTOSSH_MONITOR_PORT': 'autossh.monitor_port',
    
    # Docker 配置
    'CONTAINER_NAME': 'docker.container_name',
    'CONTAINER_ROOT_PASSWORD': 'docker.root_password',
    'HOST_SSH_PORT': 'docker.host_ssh_port',
}
```

**特殊处理**：
- `CLASH_CONFIG_URL`：自动转为名为 "Default" 的订阅
- 路径转换：相对路径转绝对路径，`~/` 展开
- 模式检测：根据文件路径或配置项推断部署模式

## 部署流程

### 完整部署流程（lab-remote-ctl deploy）

```
1. 预检查
   ├─ 验证 config.yaml 格式和必填项
   ├─ 检查 SSH 连接到云服务器
   ├─ 检查远程服务器是否已有旧版本部署
   └─ 提示是否需要先迁移配置

2. 准备阶段
   ├─ 确定部署模式（host/docker）
   ├─ 检测远程服务器的包管理器
   ├─ 创建安装目录
   └─ 备份现有配置（如果存在）

3. Clash 模块部署
   ├─ 上传 Clash 核心二进制
   ├─ 上传 geo 数据文件
   ├─ 上传订阅转换模板
   ├─ 如果有订阅 URL：下载并转换
   ├─ 否则：提示用户稍后通过 Web 界面添加
   ├─ 创建 systemd 服务
   └─ 启动服务

4. AutoSSH 模块部署
   ├─ 检查 SSH 密钥
   ├─ 上传 autossh 配置
   ├─ 创建 systemd 服务
   └─ 启动服务

5. Zsh 模块部署
   ├─ 安装工具包（fzf, fd, eza, bat, tldr, fastfetch）
   ├─ 安装 zsh 插件
   ├─ 生成配置块（根据 config.yaml）
   ├─ 写入 ~/.zshrc
   └─ 设置默认 shell（如果需要）

6. Web 模块部署
   ├─ 上传 Flask 应用文件
   ├─ 安装 Python 依赖（Flask, PyYAML, requests）
   ├─ 创建 systemd 服务
   └─ 启动服务

7. 后期验证
   ├─ 等待服务启动（5-10 秒）
   ├─ 运行健康检查
   ├─ 显示部署摘要
   └─ 提供下一步操作建议
```

### 部署输出示例

```
╭─────────────────────────────────────────╮
│  🚀 Lab Remote Bootstrap 部署            │
╰─────────────────────────────────────────╯

配置文件: config/config.yaml
部署模式: host
目标服务器: user@remote-server

[1/7] 预检查
  ✓ 配置文件验证通过
  ✓ SSH 连接正常
  ✓ 远程服务器环境检查完成

[2/7] 准备阶段
  ✓ 检测到包管理器: apt
  ✓ 创建安装目录: /opt/lab-remote-stack
  ⚠ 检测到旧版本部署，已备份到 .backup-20260701

[3/7] Clash 模块部署
  ✓ 上传 Clash 核心 (CrashCore)
  ✓ 上传 geo 数据文件
  ✓ 上传订阅模板 (3 个)
  ℹ 未配置订阅 URL，请稍后通过 Web 界面添加
  ✓ 创建 systemd 服务
  ✓ 启动 lab-clash.service

[4/7] AutoSSH 模块部署
  ✓ 验证 SSH 密钥
  ✓ 创建 systemd 服务
  ✓ 启动 lab-autossh.service

[5/7] Zsh 模块部署
  ✓ 安装工具包 (7/8 成功, tldr 跳过)
  ✓ 安装 zsh 插件
  ✓ 写入配置到 ~/.zshrc
  ✓ 默认 shell 已设置为 zsh

[6/7] Web 模块部署
  ✓ 上传 Flask 应用
  ✓ 安装 Python 依赖
  ✓ 创建 systemd 服务
  ✓ 启动 lab-web.service (端口: 5000)

[7/7] 部署验证
  ⏳ 等待服务启动...
  ✓ 运行健康检查 (7/7 通过)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 部署完成！

服务状态:
  • Clash: 运行中 (端口: 7890/7891/9090)
  • AutoSSH: 已连接 (cloud.example.com:2223)
  • Web 界面: 运行中 (127.0.0.1:5000)

下一步:
  1. 打开 Web 界面添加订阅:
     lab-remote-ctl web open
  
  2. 或通过 CLI 添加订阅:
     lab-remote-ctl subscription add "主力" https://...
  
  3. 通过反向隧道连接服务器:
     ssh -p 2223 user@cloud.example.com

部署耗时: 2m 34s
```

## 技术选型

### 依赖清单

**Python 依赖**：
- Flask >= 2.0（Web 框架）
- Flask-CORS（跨域支持）
- PyYAML（配置解析）
- jsonschema（配置验证）
- Click >= 8.0（CLI 框架）
- Rich（终端美化）
- requests（HTTP 请求）
- Paramiko（可选，SSH 操作）

**系统依赖**（服务器端）：
- Python 3.8+
- systemd（服务管理）
- zsh
- 包管理器（apt/dnf/yum/pacman/zypper/apk）

**命令行工具**（best-effort 安装）：
- fzf
- fd-find / fd / fdfind
- eza（降级：exa）
- bat / batcat
- tldr
- fastfetch
- autossh
- curl
- git

### 向后兼容策略

**保留简化的 Shell 脚本入口**：

```bash
# scripts/deploy.sh
#!/bin/bash
if command -v lab-remote-ctl >/dev/null 2>&1; then
    exec lab-remote-ctl deploy "$@"
else
    echo "请先安装 lab-remote-ctl"
    echo "或使用旧版本脚本: host/setup_host_stack.sh"
    exit 1
fi
```

**迁移支持**：
- 提供 `lab-remote-ctl migrate` 命令
- 自动检测旧配置文件
- 生成详细的迁移报告
- 保留旧文件作为备份

## 实现计划

### 阶段划分

**阶段 1：基础架构（优先级：高）**
- 创建目录结构
- 实现统一配置系统（config.py + config.yaml）
- 实现 CLI 框架（lab-remote-ctl 命令骨架）
- 实现配置迁移工具

**阶段 2：核心模块（优先级：高）**
- Clash 模块（clash_module.py + 订阅转换）
- AutoSSH 模块（autossh_module.py）
- Zsh 模块（zsh_module.py）
- 健康检查系统（health.py）

**阶段 3：Web 界面（优先级：中）**
- Flask 后端 API
- 前端单页面应用
- 订阅管理界面
- Clash Dashboard 集成

**阶段 4：部署和测试（优先级：中）**
- 主部署流程（deployer.py）
- systemd 服务管理
- 完整的集成测试
- 文档更新

**阶段 5：优化和文档（优先级：低）**
- 错误处理优化
- 日志系统完善
- 用户文档
- 迁移指南

### 测试策略

**单元测试**：
- 配置解析和验证
- 订阅转换逻辑
- 模板渲染

**集成测试**：
- 完整部署流程（使用测试服务器）
- 订阅更新流程
- 健康检查功能

**手动测试**：
- 不同 Linux 发行版的兼容性
- Web 界面功能完整性
- 配置迁移正确性

### 风险和缓解

**风险 1：现有用户迁移失败**
- 缓解：提供详细的迁移工具和文档
- 缓解：保留旧脚本作为降级选项

**风险 2：订阅转换兼容性问题**
- 缓解：支持多种协议格式
- 缓解：提供手动 YAML 上传选项

**风险 3：不同发行版的包名差异**
- 缓解：best-effort 安装策略
- 缓解：详细的安装日志和错误提示

**风险 4：SSH 连接和权限问题**
- 缓解：详细的预检查步骤
- 缓解：清晰的错误信息和修复建议

## 用户体验改进

### 新用户体验

```bash
# 1. 克隆仓库
git clone <repo> && cd lab-remote-bootstrap

# 2. 初始化配置（交互式）
./cli/lab-remote-ctl init --interactive

# 3. 编辑配置（可选）
vim config/config.yaml

# 4. 一键部署
./cli/lab-remote-ctl deploy

# 5. 打开 Web 界面添加订阅
./cli/lab-remote-ctl web open
```

### 旧用户迁移体验

```bash
# 1. 更新代码
git pull

# 2. 迁移配置
./cli/lab-remote-ctl migrate host/host-stack.env

# 3. 检查生成的配置
cat config/config.yaml

# 4. 重新部署
./cli/lab-remote-ctl deploy
```

### 日常使用体验

```bash
# 添加订阅
lab-remote-ctl subscription add "新订阅" https://...

# 更新订阅
lab-remote-ctl subscription update "新订阅"

# 切换订阅
lab-remote-ctl subscription activate "新订阅"

# 健康检查
lab-remote-ctl health

# 打开 Web 界面
lab-remote-ctl web open
```

## 成功标准

### 功能完整性
- ✅ 所有四个核心改进都已实现
- ✅ CLI 工具提供完整的管理功能
- ✅ Web 界面功能正常且易用
- ✅ 健康检查准确可靠

### 质量标准
- ✅ 旧配置迁移成功率 > 95%
- ✅ 订阅转换支持主流格式
- ✅ 部署成功率 > 90%（在支持的发行版上）
- ✅ 详细的错误信息和修复建议

### 可维护性
- ✅ 模块化架构，职责清晰
- ✅ 统一的配置格式
- ✅ 完整的文档和注释
- ✅ 易于添加新功能

## 附录

### 文件清单

**新增文件**：
```
lib/config.py
lib/deployer.py
lib/subscription.py
lib/health.py
lib/utils.py
lib/modules/clash_module.py
lib/modules/autossh_module.py
lib/modules/zsh_module.py
lib/modules/web_module.py
cli/lab-remote-ctl
web/app.py
web/templates/index.html
web/static/style.css
web/static/app.js
scripts/deploy.sh
scripts/health_check.sh
scripts/migrate_config.py
config/config.example.yaml
config/config.schema.json
assets/clash/templates/minimal.yaml
assets/clash/templates/balanced.yaml
assets/clash/templates/full.yaml
docs/migration-guide.md
```

**修改文件**：
```
README.md（更新文档）
local/open_dashboard.sh（重命名并简化）
```

**保留但标记为 deprecated 的文件**：
```
host/setup_host_stack.sh
docker/setup_docker_stack.sh
```

### 配置示例

完整的 `config.yaml` 示例已包含在"统一配置格式"章节。

### 命令速查表

```bash
# 初始化
lab-remote-ctl init --interactive

# 部署
lab-remote-ctl deploy
lab-remote-ctl deploy --dry-run
lab-remote-ctl deploy --skip-zsh

# 订阅管理
lab-remote-ctl subscription add <name> <url>
lab-remote-ctl subscription list
lab-remote-ctl subscription activate <name>
lab-remote-ctl subscription update <name>
lab-remote-ctl subscription remove <name>

# Web 界面
lab-remote-ctl web start
lab-remote-ctl web open
lab-remote-ctl web stop

# 健康检查
lab-remote-ctl health
lab-remote-ctl health --json

# 迁移
lab-remote-ctl migrate <old-config.env>
```

---

**设计完成日期**: 2026-07-01  
**下一步**: 进入实现计划阶段

