# Lab Remote Bootstrap

用于在实验室服务器上部署以下组件，并提供统一的初始化脚本：

- Clash
- 反向 SSH 隧道
- 增强的 Zsh 终端环境

支持两种部署方式：

1. **Docker 模式**：在宿主机中运行 Ubuntu 22.04 容器，适合较旧或不便直接改动的宿主机
2. **Host 模式**：直接在宿主机安装和配置服务，适合较新的 Linux 服务器

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
- Host 模式默认连接方式：`ssh -p 2223 <TARGET_USER>@<云服务器IP>`
