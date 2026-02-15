# Lab Remote Bootstrap

把实验室服务器「Clash + 反向 SSH + 开发终端增强」做成脚本化部署，支持两种模式：

1. **Docker 模式**：在宿主机跑 Ubuntu 22.04 容器（适配旧版宿主机）
2. **Host 模式（无 Docker）**：直接在宿主机配置服务（适配新服务器）

---

## 目录结构

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
│   └── setup_docker_stack.sh
├── host/
│   ├── host-stack.env.example
│   └── setup_host_stack.sh
└── docs/
    ├── Docker容器内连vpn.md
    └── Docker 远程开发环境搭建与维护手册.md
```

---

## 你需要提前准备

### 1) SSH 密钥（实验室机可免密登录云服务器）

例如（你已有）：

```bash
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host>
```

### 2) Clash 文件（放到 `assets/clash/`）

- 内核二进制（文件名不限，脚本会自动识别 `CrashCore` / `mihomo*` / `clash*`）
- `config.yaml`（隐私配置，建议每个用户自行准备，不放仓库）
- `geoip.dat`
- `geosite.dat`

---

## 第一步（云服务器）

先在云服务器执行：

```bash
bash cloud/prepare_cloud_reverse_ssh.sh 2223
```

作用：

- 打开 `AllowTcpForwarding yes`
- 打开 `GatewayPorts clientspecified`
- 重启 ssh 服务
-（若 ufw 开启）放行对应端口

---

## 方案 A：Docker 模式

### 1. 准备配置

```bash
cp docker/docker-stack.env.example docker/docker-stack.env
```

编辑 `docker/docker-stack.env`（至少改云服务器账号/IP 和 root 密码）。
`CLASH_SOURCE_DIR` 默认自动使用仓库内 `./assets/clash`，一般不需要改。

### 2. 一键部署

```bash
bash docker/setup_docker_stack.sh docker/docker-stack.env
```

部署内容：

- Docker 镜像构建 + 容器启动（`--restart always`）
- 容器内 SSH 服务
- AutoSSH 反向隧道
- Clash 启动与端口注入
- zsh + 插件 + powerlevel10k + fastfetch

---

## 方案 B：Host 模式（无 Docker）

### 1. 准备配置

```bash
cp host/host-stack.env.example host/host-stack.env
```

编辑 `host/host-stack.env`（至少改云服务器账号/IP）。
`CLASH_SOURCE_DIR` 默认自动使用仓库内 `./assets/clash`，一般不需要改。

### 2. 一键部署

```bash
bash host/setup_host_stack.sh host/host-stack.env
```

部署内容：

- 自动安装依赖（支持 `apt/dnf/yum/pacman/zypper/apk`）
- 安装 Clash 到 `INSTALL_ROOT`（默认 `/opt/lab-remote-stack`）
- 生成并启用 systemd 服务：
  - `lab-clash.service`
  - `lab-autossh.service`
- zsh 增强（completion/history/autosuggestions/syntax-highlighting/powerlevel10k/fastfetch）
- 在 `.zshrc` 注入 Clash 代理变量（带端口可配置）

---

## 常用检查

### 检查云端端口监听

```bash
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host> "ss -tnl | grep 2223"
```

### Host 模式服务状态

```bash
sudo systemctl status lab-clash.service
sudo systemctl status lab-autossh.service
```

### Host 模式日志

```bash
sudo journalctl -u lab-clash.service -f
sudo journalctl -u lab-autossh.service -f
```

---

## 连接方式

- Docker 模式（默认）：`ssh -p 2223 root@<云服务器IP>`
- Host 模式（默认）：`ssh -p 2223 <TARGET_USER>@<云服务器IP>`

---

## 备注

- 本目录只是脚本仓库骨架，**没有做 git init**，你可以自行初始化和推送。
- 已包含 `.gitignore`，默认忽略 `docker/docker-stack.env`、`host/host-stack.env` 和 `assets/clash/*`。
- 后续更新脚本时，建议保留 `*.env` 的本地私有配置，不要提交明文密码/密钥路径。
