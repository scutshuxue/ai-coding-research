# SSH 反向隧道远程开发方案设计

## 场景

两台可上网但不在同一局域网的机器，通过阿里云 VPS 中转，实现 VSCode SSH Remote 连接。

## 角色

| 机器 | 网络 | 角色 | 系统 |
|------|------|------|------|
| macOS 本机 | 无公网IP（家宽NAT） | SSH 服务端 + 隧道发起方 | macOS |
| 阿里云 VPS | 公网IP，2C2G/3Mbps | 中转跳板 | Linux |
| 机器B | 另一个网络，可上网 | VSCode SSH Remote 客户端 | — |

## 架构

```
机器B (VSCode) --SSH--> VPS:2222 --反向隧道--> macOS:22
                                  <--autossh--- macOS (保活)
```

1. macOS 通过 autossh 向 VPS 建立反向隧道，将 VPS:2222 映射到 macOS:22
2. 机器B 通过 VSCode SSH Remote 连接 VPS:2222
3. VPS 将流量转发到 macOS sshd

## 选型理由

- SSH 反向隧道 + autossh：零额外软件（机器B无需安装任何东西），配置简单，全程加密
- 对比 FRP：功能过重，只需暴露一个 SSH 端口
- 对比 Tailscale/ZeroTier：机器B无法安装客户端

## VPS 端配置要点

- sshd 开启 `GatewayPorts clientspecified`
- `ClientAliveInterval 30` + `ClientAliveCountMax 3` 清理僵尸连接
- 防火墙 + 阿里云安全组放行 TCP 2222

## macOS 端配置要点

- 开启远程登录（sshd）
- brew install autossh
- SSH 密钥免密登录 VPS
- autossh 命令：`autossh -M 0 -f -N -T -R 0.0.0.0:2222:localhost:22 user@VPS`
- launchd plist 实现开机自启 + 断线重启

## 机器B 配置要点

- `~/.ssh/config` 配置跳板连接
- VSCode SSH Remote 连接即可

## 安全措施

- 阿里云安全组限源 IP（如机器B出口IP固定）
- 禁用密码登录，仅密钥认证
- 使用非标准端口 2222
- 可选：VPS 装 fail2ban
