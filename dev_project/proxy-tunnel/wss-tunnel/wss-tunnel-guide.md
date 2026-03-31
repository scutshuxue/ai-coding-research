# WSS 隧道代理 — 部署使用指南

## 概述

通过 WSS（WebSocket over TLS）隧道，让网络隔离的 Linux 借用 Windows 网络出网。替代 SSH 反向隧道方案，端口扫描和流量分析均无法识别隧道特征。

```mermaid
graph LR
    subgraph Linux["Linux 服务端（网络隔离）"]
        APP["应用层<br/>curl / Chrome / Java"]
        LP["Local Proxy<br/>127.0.0.1:18080"]
        TS["WSS Server<br/>0.0.0.0:9443<br/>(TLS 加密)"]
    end

    subgraph Windows["Windows（有网络）"]
        TC["WSS Client<br/>主动连接 Linux:9443"]
    end

    subgraph Internet["目标网络"]
        HTTP["HTTP / HTTPS / API"]
    end

    APP -->|"http_proxy"| LP
    LP -->|"内部转发"| TS
    TS <-.->|"WSS 加密隧道"| TC
    TC --> Internet

    style APP fill:#4a90d9,color:#fff
    style LP fill:#4a90d9,color:#fff
    style TS fill:#e6a23c,color:#fff
    style TC fill:#e6a23c,color:#fff
    style HTTP fill:#67c23a,color:#fff
```

**扫描器视角：** 看到的是一个普通 HTTPS 网站（TLS 握手 + "Internal Dashboard" 页面），无代理/隧道特征。

---

## 文件清单

```
wss-tunnel/
├── tunnel_common.py    # 共享模块（两端都需要）
├── tunnel_server.py    # Linux 端运行
├── tunnel_client.py    # Windows 端运行
└── setup_linux.sh      # Linux 代理环境变量配置
```

**两端都需要的文件：** `tunnel_common.py` + 对应的 `tunnel_server.py` 或 `tunnel_client.py`

---

## 第一步：安装依赖

两端都需要 Python 3.8+ 和 `websockets` 库。

```bash
# Linux 端
pip install websockets

# Windows 端
pip install websockets
```

Linux 端还需要 `openssl` 命令（通常已预装）：

```bash
openssl version   # 确认可用
```

---

## 第二步：Linux 初始化证书和 Token

```bash
python tunnel_server.py --init
```

输出示例：

```
[init] Config saved to: /home/user/.wss-tunnel/server.json
[init] Certificate:     /home/user/.wss-tunnel/cert.pem
[init] Key:             /home/user/.wss-tunnel/key.pem
[init] Fingerprint:     SHA256:467728207e6775dfc90a37d032d3a308d16b2c906a065dade30e8455124be9c9
[init] Token:           5db6ef080e6ea61ff23cf4851803999d3d36a84173f91cda5e6217f6c50ee21c

Copy the token and fingerprint to the client config.
```

**记录 Token 和 Fingerprint**，Windows 端连接时需要。

文件存储在 `~/.wss-tunnel/` 目录，权限 600（仅 owner 可读）：

```
~/.wss-tunnel/
├── cert.pem        # TLS 证书
├── key.pem         # TLS 私钥
└── server.json     # 配置（含 Token）
```

自定义存储目录：

```bash
python tunnel_server.py --init --cert-dir /path/to/custom/dir
```

---

## 第三步：Linux 启动服务

```bash
python tunnel_server.py
```

输出：

```
WSS server listening on 0.0.0.0:9443
Local proxy listening on 127.0.0.1:18080
Server ready. WSS=0.0.0.0:9443  Proxy=127.0.0.1:18080
```

自定义端口：

```bash
python tunnel_server.py --wss-port 9443 --proxy-port 18080
```

后台运行：

```bash
nohup python tunnel_server.py > /tmp/tunnel-server.log 2>&1 &

# 查看日志
tail -f /tmp/tunnel-server.log
```

**tunnel_server.py 完整参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--init` | — | 首次初始化：生成证书和 Token |
| `--wss-port` | 9443 | WSS Server 监听端口 |
| `--wss-bind` | 0.0.0.0 | WSS Server 绑定地址 |
| `--proxy-port` | 18080 | Local Proxy 监听端口 |
| `--proxy-bind` | 127.0.0.1 | Local Proxy 绑定地址（仅本机） |
| `--cert-dir` | ~/.wss-tunnel | 证书和配置目录 |
| `-v` | — | 开启 debug 日志 |

---

## 第四步：Windows 连接隧道

将 `tunnel_common.py` 和 `tunnel_client.py` 复制到 Windows，然后：

```powershell
python tunnel_client.py ^
    --host <linux-ip> ^
    --token <第二步输出的 Token> ^
    --fingerprint <第二步输出的 Fingerprint>
```

输出：

```
============================================================
  WSS Tunnel Client
============================================================
  Server:      192.168.1.100:9443
  Reconnect:   ON
  Fingerprint: SHA256:467728207e67...
============================================================

Connecting to wss://192.168.1.100:9443/ws
Certificate fingerprint verified OK
Connected to server
```

**tunnel_client.py 完整参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | （必填） | Linux 服务器地址 |
| `--port` | 9443 | WSS Server 端口 |
| `--token` | （必填） | 鉴权 Token |
| `--fingerprint` | （必填） | 证书指纹 SHA256:xxx |
| `--no-reconnect` | — | 禁用自动重连 |
| `--max-retry` | 0（无限） | 最大重连次数 |
| `-v` | — | 开启 debug 日志 |

断线自动重连（默认开启），指数退避：1s → 2s → 4s → ... → 最长 60s。

---

## 第五步：Linux 验证与配置代理

### 验证隧道

```bash
# 检查代理端口
nc -z 127.0.0.1 18080 -w 3 && echo "OK" || echo "FAIL"

# 测试 HTTP
curl -x http://127.0.0.1:18080 http://httpbin.org/ip

# 测试 HTTPS
curl -x http://127.0.0.1:18080 https://httpbin.org/ip

# 验证伪装页面（外部扫描器看到的效果）
curl -k https://127.0.0.1:9443/
```

### 一键配置环境变量

```bash
source setup_linux.sh
```

或手动设置：

```bash
export http_proxy=http://127.0.0.1:18080
export https_proxy=http://127.0.0.1:18080
export no_proxy=localhost,127.0.0.1,::1
```

取消代理：

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
```

---

## 各应用接入方式

### 1. 环境变量（curl / wget / pip / npm / 大多数 CLI）

```bash
source setup_linux.sh
# 或
export http_proxy=http://127.0.0.1:18080
export https_proxy=http://127.0.0.1:18080
```

> 与 SSH 方案不同，WSS 方案的 Local Proxy **不需要认证**（仅绑定 127.0.0.1），URL 中无需 `user:pass@`。

### 2. Playwright MCP（Claude Code 调用的 Chrome）

```bash
claude mcp remove playwright

claude mcp add playwright --scope user \
  -e DISPLAY="" \
  -e PLAYWRIGHT_BROWSERS_PATH=/home/user/.cache/ms-playwright \
  -- npx @playwright/mcp@0.0.55 --headless --no-sandbox --caps devtools \
  --ignore-https-errors \
  --proxy-server http://127.0.0.1:18080 \
  --executable-path /home/user/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome
```

### 3. Chrome / Chromium（手动启动）

```bash
chromium --proxy-server=http://127.0.0.1:18080 --ignore-certificate-errors
```

### 4. Java 应用

```bash
# 方式 A：JVM 启动参数
java -Dhttp.proxyHost=127.0.0.1 \
     -Dhttp.proxyPort=18080 \
     -Dhttps.proxyHost=127.0.0.1 \
     -Dhttps.proxyPort=18080 \
     -Dhttp.nonProxyHosts="localhost|127.0.0.1" \
     -jar your-app.jar

# 方式 B：环境变量（对所有 JVM 生效）
export JAVA_TOOL_OPTIONS="-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=18080 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=18080"
```

### 5. pip

```bash
# 环境变量已设置则自动生效，或显式指定
pip install --proxy http://127.0.0.1:18080 package-name
```

### 6. npm / yarn

```bash
npm config set proxy http://127.0.0.1:18080
npm config set https-proxy http://127.0.0.1:18080

# 取消
npm config delete proxy
npm config delete https-proxy
```

### 7. Git（HTTPS 协议）

```bash
git config --global http.proxy http://127.0.0.1:18080
git config --global https.proxy http://127.0.0.1:18080

# 取消
git config --global --unset http.proxy
git config --global --unset https.proxy
```

---

## 安全特性

```mermaid
graph TD
    subgraph L1["第一层：网络加密"]
        TLS["TLS 1.2+ 加密<br/>扫描器只看到 TLS 握手"]
    end
    subgraph L2["第二层：协议伪装"]
        DISGUISE["HTTPS 伪装<br/>普通访问返回网页<br/>Server: nginx/1.24.0"]
    end
    subgraph L3["第三层：Token 鉴权"]
        TOKEN["Sec-WebSocket-Protocol<br/>无 Token → 403"]
    end
    subgraph L4["第四层：证书校验"]
        CERT["SHA256 指纹 Pinning<br/>防中间人攻击"]
    end
    subgraph L5["第五层：本地隔离"]
        LOCAL["Local Proxy 仅 127.0.0.1<br/>外部无法直连代理"]
    end

    L1 --> L2 --> L3 --> L4 --> L5

    style L1 fill:#4a90d9,color:#fff
    style L2 fill:#4a90d9,color:#fff
    style L3 fill:#e6a23c,color:#fff
    style L4 fill:#e6a23c,color:#fff
    style L5 fill:#67c23a,color:#fff
```

| 威胁 | 缓解措施 |
|------|----------|
| 端口扫描发现代理 | TLS 加密 + 伪装 HTML + `Server: nginx/1.24.0` |
| 流量深度分析 | TLS 加密，内部协议不可见 |
| SSH 隧道特征检测 | 完全不使用 SSH 隧道 |
| 中间人攻击 | 证书指纹 pinning |
| 未授权使用隧道 | Token 鉴权 |
| 本地代理被滥用 | 绑定 127.0.0.1，仅本机可达 |
| 杀软误报 | 纯 Python 脚本，不打包 exe，合法 PyPI 库 |

---

## 故障排查

```mermaid
flowchart TD
    START["应用无法通过代理出网"] --> CHECK1{"curl -x http://127.0.0.1:18080<br/>http://httpbin.org/ip"}

    CHECK1 -->|"Connection refused"| FIX1["tunnel_server.py 未运行<br/>→ 启动 tunnel_server.py"]
    CHECK1 -->|"502 Bad Gateway"| CHECK2{"Windows tunnel_client 状态?"}
    CHECK1 -->|"504 Gateway Timeout"| FIX5["Windows 无法连接目标<br/>→ 检查 Windows 网络"]
    CHECK1 -->|"正常响应"| OK["代理正常"]

    CHECK2 -->|"未运行"| FIX2["启动 tunnel_client.py"]
    CHECK2 -->|"Reconnecting..."| CHECK3{"Linux :9443 可达?"}

    CHECK3 -->|"不可达"| FIX3["检查防火墙 / 端口"]
    CHECK3 -->|"可达"| FIX4["检查 Token / 指纹"]

    style OK fill:#67c23a,color:#fff
    style FIX1 fill:#f56c6c,color:#fff
    style FIX2 fill:#f56c6c,color:#fff
    style FIX3 fill:#f56c6c,color:#fff
    style FIX4 fill:#f56c6c,color:#fff
    style FIX5 fill:#f56c6c,color:#fff
```

### 诊断命令

```bash
# Linux —— 检查服务
ps aux | grep tunnel_server
nc -z 127.0.0.1 9443 -w 3 && echo "WSS OK" || echo "WSS FAIL"
nc -z 127.0.0.1 18080 -w 3 && echo "Proxy OK" || echo "Proxy FAIL"

# Linux —— 伪装页面测试
curl -k https://127.0.0.1:9443/

# Linux —— 代理测试
curl -x http://127.0.0.1:18080 http://httpbin.org/ip
curl -x http://127.0.0.1:18080 https://httpbin.org/ip

# Linux —— debug 日志
python tunnel_server.py -v

# Windows —— 连通性测试
Test-NetConnection -ComputerName <linux-ip> -Port 9443

# Windows —— debug 日志
python tunnel_client.py --host <linux-ip> --token <token> --fingerprint <fp> -v
```

### 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `Connection refused` on :18080 | Server 未启动 | 启动 `tunnel_server.py` |
| `502 Bad Gateway` | Client 未连接 | 启动 `tunnel_client.py` 或检查网络 |
| `504 Gateway Timeout` | Windows 无法访问目标 | 检查 Windows 网络 |
| Client 显示 `fingerprint mismatch` | 证书重新生成过 | 用 `--init` 后的新指纹 |
| Client 显示 `403` | Token 错误 | 确认 `--token` 参数正确 |
| Client 不断 `Reconnecting` | Linux:9443 不可达 | 检查防火墙规则 |

---

## 与 SSH 方案对比

| | SSH -R + proxy_server.py | WSS 隧道方案 |
|---|---|---|
| 启动方式 | 需要 `ssh -R` 命令建立隧道 | 直接 `python` 启动，无需 SSH |
| 端口扫描 | 暴露 HTTP 代理特征 | TLS + 伪装网页，不可识别 |
| 流量分析 | 明文代理流量 | TLS 加密，不可分析 |
| 认证 | 用户名密码 / IP 白名单 | Token + 证书指纹 |
| 代理 URL | `http://proxy:proxy123@127.0.0.1:18080` | `http://127.0.0.1:18080`（无需认证） |
| 连接保持 | 需要 `ServerAliveInterval` | 内置心跳 + 自动重连 |
| 依赖 | Python stdlib | Python + `websockets` 库 |

---

## 快速参考

```bash
# ===== 首次部署（一次性） =====

# Linux: 安装依赖 + 初始化
pip install websockets
python tunnel_server.py --init
# → 记录 Token 和 Fingerprint

# Windows: 安装依赖
pip install websockets
# → 复制 tunnel_common.py + tunnel_client.py 到 Windows

# ===== 日常使用 =====

# Linux: 启动服务
python tunnel_server.py

# Windows: 连接隧道
python tunnel_client.py --host <linux-ip> --token <token> --fingerprint <fp>

# Linux: 配置代理
source setup_linux.sh

# Linux: 验证
curl -x http://127.0.0.1:18080 http://httpbin.org/ip
curl -x http://127.0.0.1:18080 https://httpbin.org/ip
```
