> Docker 远程开发环境搭建与维护手册
>

## 1. 架构说明
+ **宿主机**：实验室服务器 (Ubuntu 18.04)，仅作为 Docker 的载体，保留 2222 端口用于底层维护。
+ **容器**：Ubuntu 22.04 (CPU-Only)，运行 SSH 服务和开发环境，通过反向隧道暴露端口。
+ **跳板机**：公网云服务器，用于中转流量。
+ **客户端**：本地 VS Code，通过跳板机连接容器。

---

## 2. 环境准备（宿主机端）
### 2.1 安装 Docker
在实验室服务器上执行：

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
# 将当前用户加入 docker 组（避免每次输 sudo）
sudo usermod -aG docker $USER
# 注意：需注销重登录生效
```

### 2.2 生成并配置 SSH 密钥
为了让容器能自动连接云服务器（建立反向隧道），我们需要在宿主机上生成一对密钥，并将“公钥”上传给云服务器，实现**免密登录**。

1. **生成专用密钥**（在实验室宿主机执行）：

```bash
# -t ed25519: 使用更现代安全的加密算法
# -f ...: 指定文件名，避免覆盖默认密钥
# -N "": 密码为空（关键！AutoSSH 必须用无密码密钥）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_autossh -N ""
```

2. **上传公钥到云服务器**：  
这一步是让云服务器“认识”这把钥匙。

```bash
# 请替换为你的云服务器用户名和IP
ssh-copy-id -i ~/.ssh/id_ed25519_autossh.pub <cloud_user>@<cloud_host>
```

_输入一次云服务器密码后，提示 "Number of key(s) added: 1" 即成功。_

3. **测试免密连接**（必须测试）：

```bash
ssh -i ~/.ssh/id_ed25519_autossh <cloud_user>@<cloud_host>
```

_如果不需要输入密码直接进去了，说明密钥配置成功。输入 _`exit`_ 退出。_

4. **复制私钥到 Docker 目录**：  
现在把这把验证通过的“私钥”复制到我们准备挂载给容器的目录中。

```bash
mkdir -p ~/my-docker-lab/ssh_keys
cd ~/my-docker-lab

# 复制私钥
cp ~/.ssh/id_ed25519_autossh ./ssh_keys/cloud_key

# 赋予严格权限（否则 SSH 会拒绝使用）
chmod 600 ./ssh_keys/cloud_key
```

## 3. 配置文件编写
在 `~/my-docker-lab` 目录下创建以下两个文件。

### 3.1 Dockerfile
用于构建镜像，配置国内源以解决网络问题。

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# 1. 替换为阿里云源 (解决 apt 慢/失败问题)
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 2. 配置 pip 清华源
RUN mkdir -p /root/.pip && \
    echo "[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple" > /root/.pip/pip.conf

# 3. 安装基础工具
RUN apt-get update && apt-get install -y \
    openssh-server autossh git vim curl wget sudo \
    python3 python3-pip python3-venv build-essential iputils-ping tmux \
    && rm -rf /var/lib/apt/lists/*

# 4. 配置 SSH 服务
RUN mkdir /var/run/sshd
RUN echo 'root:rootpassword' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# 5. 准备工作目录
RUN mkdir -p /root/.ssh
WORKDIR /workspace

# 6. 启动入口
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
```

### 3.2 entrypoint.sh (启动脚本)
用于容器启动时自动建立反向隧道，并修复权限问题。

```bash
#!/bin/bash

# 1. 启动 SSH 服务
service ssh start

# 2. 修复密钥权限 (关键：解决 Docker 挂载导致的 Permission denied)
# 将挂载的 key 复制到容器内部，并重置所有者为 root
cp /root/.ssh/cloud_key /root/id_key_internal
chmod 600 /root/id_key_internal

# 3. 启动 AutoSSH 反向隧道
# 将云服务器的 2223 转发到容器的 22
echo "Starting AutoSSH tunnel..."
autossh -M 0 \
    -o "ServerAliveInterval 30" \
    -o "ServerAliveCountMax 3" \
    -o "StrictHostKeyChecking=no" \
    -o "ExitOnForwardFailure=yes" \
    -N \
    -R 2223:localhost:22 \
    -i /root/id_key_internal \
    <cloud_user>@<cloud_host> &  # <--- 修改为云服务器的真实用户名和IP

# 4. 保持容器运行
wait
```

---

## 4. 构建与启动
### 4.1 构建镜像
如果实验室网络无法拉取 Docker Hub 镜像，请先在本地电脑拉取 `ubuntu:22.04` 并 `save` 成 tar 包，上传到服务器 `load`。  
如果网络正常或配置了加速器：

```bash
sudo docker build -t my-lab-cpu .
```

### 4.2 启动容器
使用以下命令启动。**注意挂载路径**，确保代码保存在宿主机。

```bash
sudo docker run -d \
  --name lab-cpu-container \
  --restart always \
  -v "$(pwd)/ssh_keys/cloud_key":/root/.ssh/cloud_key \
  -v "$(pwd)/entrypoint.sh":/entrypoint.sh \
  -v ~/my_project:/workspace \
  my-lab-cpu
```

+ `-v ~/my_project:/workspace`：**核心数据挂载**。所有代码必须放在容器的 `/workspace` 下，这样才会在宿主机的 `~/my_project` 中持久化保存。

---

## 5. 容器内环境配置 (Miniconda)
1. **连接容器**：`ssh -p 2223 root@云服务器IP`
2. **下载安装**：

```bash
cd /tmp
wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
# 安装过程中一路 yes，最后 conda init 也要 yes
source ~/.bashrc
```

3. **配置 Conda 源**：

```bash
conda config --set show_channel_urls yes
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
# ... (添加其他需要的 channel)
```

4. **创建环境**：`conda create -n myenv python=3.9`

---

## 6. 客户端连接 (VS Code)
### 6.1 SSH Config 配置
```plain
Host lab-docker
    HostName <cloud_host>
    User root
    Port 2223
```

+ **User**: 必须是 `root` (容器内用户)。
+ **Port**: 必须是 `2223` (隧道端口)。

### 6.2 注意事项
+ **Settings Sync**: **绝对禁止**在旧版 VS Code (如果连接宿主机) 开启配置同步。连接此 Docker 容器（Ubuntu 22.04）时可以使用最新版 VS Code，同步风险较小，但建议谨慎。
+ **GitHub 登录**: 可以登录以使用 Copilot。

---

## 7. 常见问题与维护
### Q1: 宿主机（实验室电脑）重启了怎么办？
+ **操作**：**什么都不用做**。
+ **原理**：启动命令加了 `--restart always`。Docker 守护进程开机自启 -> 自动启动容器 -> `entrypoint.sh` 自动运行 -> `autossh` 自动重连。
+ **禁止**：不要重新运行启动脚本，否则会报“容器重名”错误。

### Q2: 连不上，提示 Permission denied (publickey)？
+ **原因**：云服务器不认密钥，或容器内密钥权限错误。
+ **解决**：
    1. 确保 `ssh_keys/cloud_key` 是正确的文件（不是文件夹），且宿主机权限为 600。
    2. 确保 `entrypoint.sh` 里连接云服务器的用户名（如 `coreknowledge`）是正确的，不要用 `root` 连云服务器。
    3. 使用 `sudo docker logs -f lab-cpu-container` 查看报错。

### Q3: 连不上，提示 Connection refused？
+ **原因**：云服务器防火墙拦截。
+ **解决**：去阿里云/腾讯云网页控制台，**安全组**添加入站规则，放行 TCP **2223** 端口。

### Q4: 跑代码中途断网/关机，程序会断吗？
+ **回答**：会断。
+ **解决**：**必须使用 **`tmux`。
    1. 进入容器输入 `tmux`。
    2. 运行代码。
    3. 按 `Ctrl+B` 然后按 `D` 离开（Detach）。
    4. 下次回来输入 `tmux attach` 恢复现场。

### Q5: 如何修改 root 密码？
+ **操作**：

```bash
sudo docker exec -it lab-cpu-container passwd
```

直接输入新密码即可，立即生效。

### Q6: 数据存在哪里？
+ **代码/数据**：存放在 `/workspace`。对应宿主机 `~/my_project`。**安全，不会丢**。
+ **环境/软件**：存放在 `/root` (如 miniconda)。对应容器内部存储。**删除容器后会丢失**。
    - _建议_：定期导出环境配置 `conda env export > /workspace/env.yml`。

