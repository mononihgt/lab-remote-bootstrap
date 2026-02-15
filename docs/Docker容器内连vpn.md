这份文档基于我们在 Docker/无桌面环境下的排错总结，完全摒弃了不稳定的自动化脚本，采用**全手动模式**，这是最稳定、最适合你环境的方案。

---

# Ubuntu (Docker) Clash/Mihomo 手动部署指南
### 1. 本地准备 (在你的 Mac/PC 上)
请先下载好以下 4 个文件，并将核心文件解压、重命名：

1. **Clash 核心 (Mihomo)**: [下载地址 (GitHub)](https://github.com/MetaCubeX/mihomo/releases)
    - 下载 `mihomo-linux-amd64-vX.X.X.gz`。
    - 解压后，**重命名为 **`CrashCore` (注意大小写)。
2. **配置文件**: [在线转换工具](https://ovpnspider.com/subconvert)
    - 将你的订阅链接转换并下载，**重命名为 **`config.yaml`。
3. **GeoIP 数据库**: [下载地址](https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat)
    - 下载 `geoip.dat`。
4. **GeoSite 数据库**: [下载地址](https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat)
    - 下载 `geosite.dat`。

---

### 2. 上传文件到服务器
在你的 Mac 终端执行 SCP 命令（假设服务器 IP 为 `1.2.3.4`，端口 `22`）：

```bash
# 如果端口不是22，请修改 -P 后的数字
scp -P 22 CrashCore config.yaml geoip.dat geosite.dat root@1.2.3.4:/etc/ShellCrash/
```

_注：如果服务器上没有 _`/etc/ShellCrash`_ 目录，请先去服务器上 _`mkdir -p /etc/ShellCrash`_。_

---

### 3. 服务器端启动配置 (一次性)
登录服务器终端，执行以下命令：

```bash
cd /etc/ShellCrash

# 1. 赋予执行权限
chmod +x CrashCore

# 2. 清理旧进程（防止冲突）
pkill -f CrashCore
```

---

### 4. 设置开机/登录自启 (Docker 专用)
由于容器没有 Systemd，我们将启动逻辑写入用户登录脚本。复制以下代码在服务器执行：

```bash
cat << 'EOF' >> ~/.bashrc

# --- Clash 自动保活与环境变量 ---
if ! pgrep -f "/etc/ShellCrash/CrashCore" > /dev/null; then
    echo "Clash 未运行，正在后台启动..."
    cd /etc/ShellCrash
    nohup ./CrashCore -d . -f config.yaml > /dev/null 2>&1 &
    sleep 1
fi

# 设置终端代理
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
# -----------------------------
EOF
```

_生效方式：退出终端重新登录，或执行 _`source ~/.bashrc`_。_

---

### 5. 常用管理命令
#### 验证是否成功
```bash
curl -I https://www.google.com
# 返回 HTTP/2 200 即为成功
```

#### 切换模式 (无需重启)
+ **切换为全局模式 (Global)**：

```bash
curl -X PATCH "http://127.0.0.1:9090/configs" -d '{"mode": "global"}'
```

+ **切换为规则模式 (Rule)**：

```bash
curl -X PATCH "http://127.0.0.1:9090/configs" -d '{"mode": "rule"}'
```

#### 手动重启/停止
```bash
# 停止
pkill -f CrashCore

# 启动 (如果不想重新登录)
cd /etc/ShellCrash && nohup ./CrashCore -d . -f config.yaml > /dev/null 2>&1 &
```

#### 查看实时日志
```bash
# 如果你需要看报错，先把nohup改成输出到文件，然后：
tail -f /etc/ShellCrash/clash.log
```

---

### 6. 进阶：如何选节点 (Web 面板)
在纯命令行选节点很麻烦，建议通过 **SSH 隧道** 映射端口，在本地浏览器管理。

1. **在 Mac 终端执行**：

```bash
ssh -p 2223 -L 9090:127.0.0.1:9090 root@云服务器IP -N
```

2. **在 Mac 浏览器打开**：[http://yacd.haishan.me/](http://yacd.haishan.me/)
3. **填入 API**：`http://127.0.0.1:9090`，即可图形化切换节点。

