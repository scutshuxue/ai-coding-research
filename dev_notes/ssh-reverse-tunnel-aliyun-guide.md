# SSH 反向隧道配置指南（阿里云 VPS 中转）

> macOS（无公网IP）通过阿里云 VPS 中转，让另一台机器用 VSCode SSH Remote 连过来

## 前置信息

以下用占位符表示，操作时替换为实际值：

| 占位符 | 含义 | 示例 |
|--------|------|------|
| `VPS_IP` | 阿里云 ECS 公网IP | 47.xxx.xxx.xxx |
| `VPS_USER` | VPS 登录用户名 | root |
| `VPS_PORT` | VPS SSH 端口 | 22 |
| `TUNNEL_PORT` | 隧道映射端口 | 2222 |
| `MAC_USER` | macOS 用户名 | polarischen |

---

## 第一步：阿里云安全组放行端口

1. 登录 [阿里云 ECS 控制台](https://ecs.console.aliyun.com/)
2. 找到你的实例 → 点击实例ID进入详情
3. 左侧菜单「安全组」→ 点击安全组ID → 「入方向」→「手动添加」
4. 添加规则：

| 字段 | 值 |
|------|-----|
| 授权策略 | 允许 |
| 优先级 | 1 |
| 协议类型 | 自定义 TCP |
| 端口范围 | 2222/2222 |
| 授权对象 | 0.0.0.0/0（或填机器B的出口IP以限制来源） |
| 描述 | SSH反向隧道 |

> **安全建议：** 如果机器B的出口IP固定，授权对象填具体IP（如 `123.45.67.89/32`），不要用 `0.0.0.0/0`

---

## 第二步：配置 VPS 的 sshd

SSH 登录 VPS：

```bash
ssh VPS_USER@VPS_IP
```

编辑 sshd 配置：

```bash
sudo vi /etc/ssh/sshd_config
```

找到并修改（或末尾追加）以下三行：

```
GatewayPorts clientspecified
ClientAliveInterval 30
ClientAliveCountMax 3
```

重启 sshd：

```bash
# CentOS / Alibaba Cloud Linux
sudo systemctl restart sshd

# Ubuntu / Debian
sudo systemctl restart ssh
```

验证配置生效：

```bash
sudo sshd -T | grep -i gatewayports
# 应输出：gatewayports clientspecified
```

---

## 第三步：配置 VPS 防火墙（如有）

阿里云 ECS 默认可能还有 OS 层面的防火墙：

```bash
# 检查 firewalld 是否运行
sudo systemctl status firewalld

# 如果运行中，放行 2222
sudo firewall-cmd --permanent --add-port=2222/tcp
sudo firewall-cmd --reload

# 如果用的是 iptables
sudo iptables -A INPUT -p tcp --dport 2222 -j ACCEPT
```

如果 VPS 防火墙是关闭状态，跳过此步。

---

## 第四步：macOS 开启 SSH 服务

系统设置 → 通用 → 共享 → 打开「远程登录」

或命令行：

```bash
sudo systemsetup -setremotelogin on
```

验证：

```bash
ssh localhost
# 能登录就说明 sshd 正常
```

---

## 第五步：macOS 配置免密登录 VPS

```bash
# 如果还没有密钥对，先生成
ssh-keygen -t ed25519 -C "mac-to-vps"

# 把公钥推送到 VPS
ssh-copy-id -i ~/.ssh/id_ed25519.pub VPS_USER@VPS_IP
```

验证免密登录：

```bash
ssh VPS_USER@VPS_IP
# 不需要输密码即成功
```

---

## 第六步：安装 autossh 并测试隧道

```bash
brew install autossh
```

手动测试（前台运行，方便观察）：

```bash
autossh -M 0 -N -T \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -R 0.0.0.0:2222:localhost:22 \
  VPS_USER@VPS_IP
```

**验证隧道是否通了：** 在 VPS 上执行：

```bash
ssh -p 2222 MAC_USER@localhost
```

如果能登录到 macOS 的 shell，说明隧道建立成功。按 `Ctrl+C` 停掉前台的 autossh。

---

## 第七步：配置 autossh 开机自启（launchd）

创建 plist 文件：

```bash
cat > ~/Library/LaunchAgents/com.autossh.reverse-tunnel.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.autossh.reverse-tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/autossh</string>
        <string>-M</string>
        <string>0</string>
        <string>-N</string>
        <string>-T</string>
        <string>-o</string>
        <string>ServerAliveInterval=30</string>
        <string>-o</string>
        <string>ServerAliveCountMax=3</string>
        <string>-o</string>
        <string>ExitOnForwardFailure=yes</string>
        <string>-R</string>
        <string>0.0.0.0:2222:localhost:22</string>
        <string>VPS_USER@VPS_IP</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/autossh-tunnel.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/autossh-tunnel.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AUTOSSH_GATETIME</key>
        <string>0</string>
    </dict>
</dict>
</plist>
EOF
```

> **注意：** 把文件中的 `VPS_USER@VPS_IP` 替换为实际值。如果 autossh 路径不是 `/opt/homebrew/bin/autossh`，用 `which autossh` 查一下实际路径。

加载服务：

```bash
launchctl load ~/Library/LaunchAgents/com.autossh.reverse-tunnel.plist
```

常用管理命令：

```bash
# 查看状态
launchctl list | grep autossh

# 停止
launchctl unload ~/Library/LaunchAgents/com.autossh.reverse-tunnel.plist

# 重新加载（修改plist后）
launchctl unload ~/Library/LaunchAgents/com.autossh.reverse-tunnel.plist
launchctl load ~/Library/LaunchAgents/com.autossh.reverse-tunnel.plist

# 查看日志
tail -f /tmp/autossh-tunnel.log
tail -f /tmp/autossh-tunnel.err
```

---

## 第八步：机器B 配置 VSCode SSH Remote

在机器B上编辑 `~/.ssh/config`：

```
Host mac-dev
    HostName VPS_IP
    Port 2222
    User MAC_USER
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

然后：

1. VSCode → 左侧「远程资源管理器」→ SSH Targets
2. 选择 `mac-dev` → 连接
3. 首次连接会提示确认指纹 → 输入 macOS 的密码或使用密钥

> **可选：** 机器B也配置密钥免密登录，把机器B的公钥加到 macOS 的 `~/.ssh/authorized_keys` 中

---

## 安全加固

### VPS 端

编辑 `/etc/ssh/sshd_config`：

```bash
# 1. 禁用密码登录，只允许密钥
PasswordAuthentication no
PubkeyAuthentication yes

# 2. 禁止 root 直接登录（用普通用户+sudo）
PermitRootLogin no

# 3. 限制只允许特定用户登录
AllowUsers your_vps_username

# 4. 改掉默认 SSH 端口（减少扫描）
Port 50022
```

改完重启 sshd：`sudo systemctl restart sshd`

> **注意：** 如果改了 VPS SSH 端口为 50022，macOS 的 autossh 命令和 launchd plist 也要加 `-p 50022`，阿里云安全组也要同步放行 50022。

安装 fail2ban 防暴力破解：

```bash
# Ubuntu/Debian
sudo apt install fail2ban -y

# CentOS/Alibaba Cloud Linux
sudo yum install fail2ban -y

sudo systemctl enable fail2ban --now
```

默认配置即可——SSH 登录连续失败 5 次，封禁 IP 10 分钟。

### macOS 端

编辑 `/etc/ssh/sshd_config`（需要 sudo）：

```bash
# 1. 禁用密码登录
PasswordAuthentication no

# 2. 限制只允许你自己的用户
AllowUsers polarischen

# 3. 禁止 root 登录
PermitRootLogin no

# 4. 只监听 localhost（隧道流量走 127.0.0.1 进来，不需要监听所有网卡）
ListenAddress 127.0.0.1
ListenAddress ::1
```

重启 macOS sshd：

```bash
sudo launchctl stop com.openssh.sshd
sudo launchctl start com.openssh.sshd
```

> `ListenAddress 127.0.0.1` 是关键——即使有人扫到你的局域网 IP，也连不上 sshd，只有通过反向隧道（走 localhost）才能进来。

### 加固后的完整安全链路

```
机器B → 阿里云安全组(限源IP) → VPS:2222(密钥认证) → 隧道 → macOS:22(仅localhost, 密钥认证)
```

四层防护：安全组限IP、非标准端口、禁密码仅密钥、macOS 只听 localhost。

---

## 故障排查

### 隧道连不上

```bash
# 1. 在 macOS 上检查 autossh 是否在运行
ps aux | grep autossh

# 2. 在 VPS 上检查端口是否在监听
ss -tlnp | grep 2222

# 3. 在 VPS 上测试本地回环
ssh -p 2222 MAC_USER@localhost

# 4. 从机器B测试端口连通性
nc -zv VPS_IP 2222
```

### VPS 上 2222 没有监听

- 检查 `GatewayPorts` 配置是否生效
- 检查 macOS 上 autossh 日志：`cat /tmp/autossh-tunnel.err`
- 手动前台运行 autossh 看报错

### 连接经常断

- 检查 macOS 的网络是否稳定
- 查看 `/tmp/autossh-tunnel.log` 中的重连记录
- 3Mbps 带宽下正常编码不会有问题，但大文件传输（git clone 大仓库等）可能慢

### macOS 休眠后隧道断开

macOS 休眠会断网，autossh 唤醒后会自动重连（launchd 的 `KeepAlive` 确保进程存活）。通常 10-30 秒内恢复。
