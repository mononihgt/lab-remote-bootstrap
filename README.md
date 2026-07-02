# Lab Remote Bootstrap

> **🚀 新版本 v2.0 已完成！**  
> 全新模块化架构，提供强大的 CLI 工具 `lab-remote-ctl` 和现代化 Web 管理界面。
> 
> **核心功能**：
> - ✅ 统一配置管理（YAML 格式 + JSON Schema 验证）
> - ✅ Clash 订阅管理（支持 Base64 编码订阅和 YAML 订阅）
> - ✅ Web 管理界面（Flask + Catppuccin Mocha 主题）
> - ✅ 个性化 Zsh 配置同步（fzf, eza, bat, tldr, fastfetch）
> - ✅ 健康检查系统（服务/端口/连通性）
> - ✅ 配置迁移工具（从旧版本 .env 迁移）
> 
> 查看 [设计文档](docs/superpowers/specs/2026-07-01-modular-refactor-design.md) 了解详情。
>
> ---

用于在实验室服务器上部署以下组件，并提供统一的初始化脚本：

- Clash
- 反向 SSH 隧道
- 增强的 Zsh 终端环境

支持两种部署方式：

1. **Docker 模式**：在宿主机中运行 Ubuntu 22.04 容器，适合较旧或不便直接改动的宿主机
2. **Host 模式**：直接在宿主机安装和配置服务，适合较新的 Linux 服务器

---

## 快速开始（新架构 v2.0）

### 前置条件

在开始部署之前，请确保满足以下条件：

#### 1. 本地环境（运行 lab-remote-ctl 的机器）

- Python 3.7+ 已安装
- 可以通过 SSH 连接到云服务器和实验室服务器
- 远程部署时，`target.ssh_identity_file` 是**本地机器上**用于连接实验室服务器的私钥；如果留空，则使用 `~/.ssh/config` 或 ssh-agent

#### 2. 云服务器（用于反向 SSH 隧道）

云服务器需要提前配置好：

```bash
# 在云服务器上执行
bash cloud/prepare_cloud_reverse_ssh.sh 2223
```

该脚本会：
- 启用 `AllowTcpForwarding yes`
- 启用 `GatewayPorts clientspecified`
- 重启 SSH 服务
- 放行端口（如果启用了防火墙）

验证云服务器可访问：
```bash
ssh <cloud_user>@<cloud_host>
```

#### 3. 实验室服务器（部署目标）

实验室服务器需要：
- Linux 系统（支持 Ubuntu、Debian、CentOS、Arch 等）
- sudo 权限
- 可以通过 SSH 从本地连接
- **具备到云服务器的 SSH 密钥认证**（用于 AutoSSH 反向隧道）

生成并配置 SSH 密钥：
```bash
# 在实验室服务器上生成密钥
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_autossh -N ""

# 将公钥添加到云服务器
ssh-copy-id -i ~/.ssh/id_ed25519_autossh.pub <cloud_user>@<cloud_host>

# 测试连接
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host>
```

**重要**：这里有两个不同的 SSH 身份，不要混用：

- `target.*`：本地机器 → 实验室服务器，用于 `lab-remote-ctl` 远程部署。`target.ssh_identity_file` 可留空以使用 `~/.ssh/config` 或 ssh-agent。
- `cloud.*`：实验室服务器 → 云服务器，用于 AutoSSH 反向隧道。`cloud.user` 是云服务器上的用户名，不是实验室服务器用户名。
- `autossh.identity_file`：实验室服务器 → 云服务器，用于 AutoSSH 反向隧道。这里填写实验室服务器上的私钥路径，如 `~/.ssh/id_ed25519_autossh`。

#### 4. 网络连通性

确保以下连接畅通：
- 本地 → 云服务器（SSH）
- 本地 → 实验室服务器（SSH）
- 实验室服务器 → 云服务器（SSH，用于 AutoSSH）

### 安装依赖

```bash
# 在本地机器上安装 Python 依赖
pip3 install -r requirements.txt
```

### 方式 1：全新部署（首次部署 - 在实验室服务器上操作）

如果本地无法直接 SSH 到实验室服务器（服务器在内网），需要先在实验室服务器上进行首次部署：

#### 1. 将项目拷贝到实验室服务器

```bash
# 方式 A: 使用 U 盘或其他物理介质
# 方式 B: 如果服务器可以访问 GitHub
git clone https://github.com/mononihgt/lab-remote-bootstrap.git
cd lab-remote-bootstrap
pip3 install -r requirements.txt
```

#### 2. 在服务器上初始化配置

```bash
# 在实验室服务器上执行
./cli/lab-remote-ctl init --interactive
```

**关键配置**：
- `deployment.target` 设置为 `local`（本地部署模式）
- 云服务器信息要正确填写（用于 AutoSSH 反向隧道）
- 不需要填写 `target.*`（本地部署不需要控制 SSH 私钥）
- `autossh.identity_file` 填写服务器上的 SSH 私钥路径

#### 3. 在服务器上执行部署

```bash
# 在实验室服务器上执行
./cli/lab-remote-ctl deploy
```

首次部署完成后，AutoSSH 会建立到云服务器的反向隧道，之后就可以从任何地方通过云服务器访问实验室服务器了：

```bash
# 从任何地方连接
ssh -p 2223 <lab_user>@<cloud_host>
```

**后续管理**：首次部署完成后，可以在本地使用 `lab-remote-ctl` 远程管理（将 `deployment.target` 改为 `remote`）。

---

### 方式 2：远程部署（本地可 SSH 到服务器）

#### 1. 初始化配置

```bash
# 交互式配置向导（推荐）
./cli/lab-remote-ctl init --interactive

# 或使用模板然后手动编辑
./cli/lab-remote-ctl init
vim config/config.yaml
```

#### 2. 准备 Clash 资源（可选）

将以下文件放入 `assets/clash/`：
- Clash 内核二进制（mihomo、clash 等）- 如果没有，部署时会自动下载
- `geoip.dat` 和 `geosite.dat` - 如果没有，部署时会自动下载

#### 3. 部署到远程服务器

**注意**：`lab-remote-ctl` 在本地运行，通过 SSH 控制远程服务器。
远程部署开始前会自动清理 `target.host` / `target.ssh_port` 对应的本地 `known_hosts` 记录，避免反向隧道或重装系统后残留的 SSH 指纹导致隐藏失败。

远程部署时的 SSH 配置示例：

```yaml
deployment:
  target: remote

target:
  # lab-remote-ctl 连接实验室服务器的方式
  host: <target_ssh_host_or_cloud_tunnel_host>
  user: <lab_user>
  ssh_port: 2222
  ssh_identity_file: ~/.ssh/<local_target_key>

cloud:
  # 实验室服务器上的 AutoSSH 连接云服务器的方式
  host: <cloud_public_host>
  user: <cloud_user>
  reverse_port: 2222
  # 反向 SSH 在云服务器上的监听地址；需要公网直连时用 0.0.0.0
  reverse_bind_address: 0.0.0.0

autossh:
  # 实验室服务器上的私钥路径，用于 AutoSSH 连接云服务器
  identity_file: ~/.ssh/<server_autossh_key>
```

```bash
# 完整部署（Clash + AutoSSH + Zsh + Web）
./cli/lab-remote-ctl deploy

# 选择性部署
./cli/lab-remote-ctl deploy --skip-web  # 跳过 Web 界面
./cli/lab-remote-ctl deploy --dry-run   # 预览部署计划
```

部署完成后，AutoSSH 会建立反向隧道，你可以通过云服务器连接到实验室服务器：
```bash
# 从任何地方通过云服务器连接实验室服务器
ssh -p 2223 <lab_user>@<cloud_host>
```

重新部署 AutoSSH 时，`lab-remote-ctl deploy` 会先通过实验室服务器登录云服务器，清理同一 `cloud.reverse_port` 上的旧监听进程，再重启 `lab-autossh.service`。这可以恢复旧反向隧道半死时出现的 `Connection timed out during banner exchange`。

`deploy` 结束时会根据本次实际结果输出对应的 Next steps：成功部署的模块会显示后续操作，跳过的模块不会显示对应步骤，Zsh/Web 等非关键模块失败时会优先提示修复并重新部署。

#### 4. 管理订阅

```bash
# 添加订阅
./cli/lab-remote-ctl subscription add "主力节点" https://example.com/subscription

# 更新订阅（下载并生成配置）
./cli/lab-remote-ctl subscription update "主力节点"

# 查看所有订阅
./cli/lab-remote-ctl subscription list

# 激活订阅
./cli/lab-remote-ctl subscription activate "主力节点"
```

#### 5. 健康检查

```bash
# 检查系统健康状态
./cli/lab-remote-ctl health

# JSON 格式输出
./cli/lab-remote-ctl health --json
```

#### 6. Web 管理界面

```bash
# 启动 Web 服务
./cli/lab-remote-ctl web start

# 在浏览器中打开
./cli/lab-remote-ctl web open

# 停止 Web 服务
./cli/lab-remote-ctl web stop
```

远程部署时，Web 服务默认只监听实验室服务器本机的 `127.0.0.1:5000`，Clash 控制端口默认只监听实验室服务器本机的 `127.0.0.1:9090`。在本地 PC 访问前先建立 SSH 隧道：

```bash
ssh -N -L 5001:127.0.0.1:5000 -L 9090:127.0.0.1:9090 sr665-4
```

`lab-remote-ctl web start` 和 `lab-remote-ctl web open` 在远程部署模式下会自动启动该本地隧道，然后打开 `http://localhost:5001`。`lab-remote-ctl web stop` 会停止远端 Web 服务，并清理本地隧道。不要直接访问本地 `http://localhost:5000`；macOS 可能已由 AirPlay/Control Center 占用该端口。

### 方式 3：从旧版本迁移

```bash
# 迁移旧版本配置
./cli/lab-remote-ctl migrate host/host-stack.env

# 预览迁移（不写入文件）
./cli/lab-remote-ctl migrate host/host-stack.env --dry-run

# 然后正常部署
./cli/lab-remote-ctl deploy
```

### CLI 命令总览

```bash
lab-remote-ctl
├── init              # 初始化配置
├── deploy            # 部署到远程服务器
├── subscription      # 订阅管理
│   ├── add          # 添加订阅
│   ├── list         # 列出所有订阅
│   ├── activate     # 激活订阅
│   ├── update       # 更新订阅
│   └── remove       # 删除订阅
├── health            # 健康检查
├── web               # Web 服务管理
│   ├── start        # 启动服务
│   ├── stop         # 停止服务
│   └── open         # 打开界面
└── migrate           # 配置迁移
```

**重要说明**：
- `lab-remote-ctl` 在**本地 PC** 运行，通过 SSH 控制远程服务器
- 部署的服务（Clash、AutoSSH、Web）在**实验室服务器**上运行
- 通过云服务器的反向隧道，可从任何地方访问实验室服务器

### 订阅格式支持

新版本支持以下订阅格式：

1. **Base64 编码订阅**：包含 vmess://、ss://、trojan:// 等协议的 Base64 编码链接
2. **Clash YAML 订阅**：直接提供 Clash proxies 的 YAML 格式

订阅会自动转换为 Clash 配置，并根据选择的模板（minimal/balanced/full）生成规则。

### 完整使用流程总结

```
┌─────────────┐
│  本地 PC    │  1. 安装依赖: pip3 install -r requirements.txt
│             │  2. 初始化配置: ./cli/lab-remote-ctl init --interactive
└──────┬──────┘  3. 部署: ./cli/lab-remote-ctl deploy
       │         4. 管理订阅: init 时填写 URL 或 subscription add/update
       │ SSH     5. Web 管理: ./cli/lab-remote-ctl web open
       ↓
┌──────────────────┐
│  云服务器        │  前置准备: bash cloud/prepare_cloud_reverse_ssh.sh 2223
│  (反向隧道中转)  │  提供反向 SSH 端口 (默认 2223)
└──────────────────┘
       ↑
       │ AutoSSH 反向隧道
       │
┌──────────────────────────┐
│  实验室服务器 (部署目标)  │  运行服务:
│                          │  - Clash (代理)
│                          │  - AutoSSH (反向隧道)
│                          │  - Zsh (终端环境)
│                          │  - Web (管理界面)
└──────────────────────────┘
```

**访问方式**：
- SSH 连接实验室服务器：`ssh -p 2223 <user>@<cloud_host>`
- Web 管理界面：远程部署时先建立 SSH 隧道，再访问 `http://localhost:5001`
- Clash 代理：HTTP `7890`，SOCKS `7891`

---

## 旧版本使用方式（稳定）

以下是当前稳定版本的使用方式，新架构完成前仍可使用。

---

## 仓库结构

```text
lab-remote-bootstrap/
├── README.md
├── assets/
│   └── clash/
│       └── README.md
├── cloud/
│   └── prepare_cloud_reverse_ssh.sh
├── docker/
│   ├── docker-stack.env.example
│   ├── setup_docker_mirror_cn.sh
│   └── setup_docker_stack.sh
├── host/
│   ├── host-stack.env.example
│   └── setup_host_stack.sh
├── local/
│   ├── dashboard.env.example
│   └── open_clash_dashboard.sh
└── docs/
    ├── Docker容器内连vpn.md
    └── Docker 远程开发环境搭建与维护手册.md
```

---

## 脚本职责

- **本地电脑**：`local/open_clash_dashboard.sh`
- **实验室服务器**：`host/setup_host_stack.sh`、`docker/setup_docker_stack.sh`
- **云服务器**：`cloud/prepare_cloud_reverse_ssh.sh`
- **Docker 镜像源与代理优化**：`docker/setup_docker_mirror_cn.sh`

---

## 前置条件

### 1. 云服务器可正常 SSH 登录

例如：

```bash
ssh <cloud_user>@<cloud_host>
```

### 2. 实验室服务器具备到云服务器的 SSH 密钥

例如：

```bash
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host>
```

### 3. 准备 Clash 文件

将以下文件放入 `assets/clash/`：

- Clash 内核二进制  
  脚本会自动识别 `CrashCore`、`mihomo*`、`clash*`
- `config.yaml`
- `geoip.dat`
- `geosite.dat`

如不希望将 `config.yaml` 保存在本地，可在环境变量中设置：

- `CLASH_CONFIG_URL=...`

其优先级高于 `CLASH_CONFIG_FILE`。

---

## 推荐部署顺序

1. 在云服务器执行 `cloud/prepare_cloud_reverse_ssh.sh`
2. 在实验室服务器选择 Docker 模式或 Host 模式执行部署
3. 在本地使用 `local/open_clash_dashboard.sh` 打开 Clash Dashboard

---

## 云服务器准备

在云服务器执行：

```bash
bash cloud/prepare_cloud_reverse_ssh.sh 2223
```

该脚本会：

- 启用 `AllowTcpForwarding yes`
- 启用 `GatewayPorts clientspecified`
- 重启 SSH 服务
- 在启用 `ufw` 时放行对应端口

---

## Docker 模式

### 1. 复制配置

```bash
cp docker/docker-stack.env.example docker/docker-stack.env
```

至少需要修改：

- 云服务器账号
- 云服务器地址
- 容器 root 密码

默认情况下，`CLASH_SOURCE_DIR` 使用仓库内的 `./assets/clash`。

### 2. 执行部署

```bash
bash docker/setup_docker_stack.sh docker/docker-stack.env
```

部署结果包括：

- Docker 镜像构建与容器启动（`--restart always`）
- 容器内 SSH 服务
- AutoSSH 反向隧道
- Clash 启动与端口注入
- Zsh 环境增强（补全、历史搜索、autosuggestions、syntax-highlighting、powerlevel10k、fastfetch、fzf、zoxide、eza）

---

## Host 模式

### 1. 复制配置

```bash
cp host/host-stack.env.example host/host-stack.env
```

至少需要修改：

- 云服务器账号
- 云服务器地址

默认情况下，`CLASH_SOURCE_DIR` 使用仓库内的 `./assets/clash`。

### 2. 执行部署

```bash
bash host/setup_host_stack.sh host/host-stack.env
```

部署结果包括：

- 自动安装依赖（支持 `apt`、`dnf`、`yum`、`pacman`、`zypper`、`apk`）
- Clash 安装到 `INSTALL_ROOT`（默认 `/opt/lab-remote-stack`）
- systemd 服务创建与启用：
  - `lab-clash.service`
  - `lab-autossh.service`
- `.zshrc` 注入代理环境变量
- Zsh 环境增强（补全、历史搜索、autosuggestions、syntax-highlighting、powerlevel10k、fastfetch、fzf、zoxide、eza）

---

## Docker 镜像源优化

仅在 Docker 模式下使用：

```bash
# 仅配置国内 Docker registry mirror
bash docker/setup_docker_mirror_cn.sh

# 同时为 Docker daemon 配置 Clash 代理
bash docker/setup_docker_mirror_cn.sh --enable-proxy
```

---

## Clash Dashboard

### 1. 复制本地配置

```bash
cp local/dashboard.env.example local/dashboard.env
```

如服务器仅允许公钥登录，可在 `local/dashboard.env` 中指定私钥：

```bash
DASHBOARD_SSH_IDENTITY_FILE=~/.ssh/id_ed25519
```

### 2. 建立隧道并打开面板

```bash
bash local/open_clash_dashboard.sh local/dashboard.env
```

脚本会：

- 建立本地到远端 Clash API 的 SSH 隧道
- 打开 Dashboard 页面
- 输出停止隧道所需的 `ssh -O exit` 命令

默认本地转发端口为 `9090`。

---

## 常用检查

### 检查云端端口监听

```bash
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host> "ss -tnl | grep 2223"
```

### 检查 Host 模式服务状态

```bash
sudo systemctl status lab-clash.service
sudo systemctl status lab-autossh.service
```

### 查看 Host 模式日志

```bash
sudo journalctl -u lab-clash.service -f
sudo journalctl -u lab-autossh.service -f
```

### SSH 输入异常

若 SSH 登录后出现乱码或重复输入，可先执行：

```bash
stty sane
reset
```

若问题仍然存在，可临时禁用 `~/.zshrc` 中的相关插件后重新登录，例如：

- `zsh-autosuggestions`
- `zsh-syntax-highlighting`

---

## 连接方式

- Docker 模式默认连接方式：`ssh -p 2223 <当前 Linux 用户>@<云服务器IP>`
- Host 模式默认连接方式：`ssh -p 2223 <当前 Linux 用户>@<云服务器IP>`

---

## 待完善功能

- [ ] 当使用云服务器对局域网服务器进行remote deploy时，会因为使用同一个端口而导致链接断开，无法进行后续deploy
- [ ] web管理界面添加订阅后，无法正常下载订阅文件，也无法update
