# SSH 反向隧道 + 正向代理方案

## 问题背景

```
Windows (有网络) ──SSH──→ Linux (网络隔离)
```

- Windows 通过 VSCode Remote SSH 连接 Linux
- Linux 无法直接访问外部网络，Windows → Linux 是**单向 SSH 通道**
- Linux 上的应用（curl、Chrome、Java 等）需要借助 Windows 网络访问外部服务

传统 SSH `-R` 反向隧道只能做**端口级**一对一映射（如把 `10.0.1.50:8080` 映射到 Linux 的 `localhost:8080`），无法满足「所有 HTTP/HTTPS 请求统一走代理」的需求。

## 方案架构

在 Windows 上运行一个 **HTTP/HTTPS 正向代理**，通过 SSH 反向隧道暴露到 Linux，Linux 端所有应用配置该代理即可。

```mermaid
graph LR
    subgraph Linux["Linux 服务端（网络隔离）"]
        APP["应用层<br/>curl / Chrome / Java"]
        LP["127.0.0.1:18080<br/>（SSH 隧道入口）"]
    end

    subgraph SSH["SSH 连接"]
        T["反向隧道<br/>-R 18080:127.0.0.1:18080"]
    end

    subgraph Windows["Windows（有网络）"]
        PROXY["proxy_server.py<br/>正向代理 :18080"]
    end

    subgraph Internet["目标网络"]
        HTTP["HTTP 站点"]
        HTTPS["HTTPS 站点"]
        API["内部 API"]
    end

    APP -->|"http_proxy / --proxy-server"| LP
    LP -.->|"SSH 加密隧道"| T
    T -.-> PROXY
    PROXY -->|"HTTP 转发"| HTTP
    PROXY -->|"CONNECT 隧道"| HTTPS
    PROXY -->|"直连"| API

    style APP fill:#4a90d9,color:#fff
    style LP fill:#4a90d9,color:#fff
    style T fill:#e6a23c,color:#fff
    style PROXY fill:#e6a23c,color:#fff
    style HTTP fill:#67c23a,color:#fff
    style HTTPS fill:#67c23a,color:#fff
    style API fill:#67c23a,color:#fff
```

### 对比传统方案

| | 传统 SSH -R（端口映射） | 本方案（代理 + SSH -R） |
|---|---|---|
| 映射方式 | 一个端口对一个目标 | 一个代理端口覆盖所有 HTTP/HTTPS |
| 新增目标 | 需要加 `-R` 参数并重建隧道 | 无需改动，代理自动转发 |
| HTTPS | 需要逐个映射 443 端口 | CONNECT 隧道原生支持 |
| 应用配置 | 改 hosts / iptables 逐个对接 | 统一环境变量或启动参数 |
| 代码改动 | 可能需要改目标地址 | **零代码改动** |

---

## 文件说明

```
dev_project/proxy-tunnel/
├── proxy-tunnel-guide.md   # 本文档
├── proxy_server.py         # Windows 端正向代理（Python 3，无第三方依赖）
├── linux-setup.sh          # Linux 端代理环境变量配置脚本
├── wss-tunnel-design.md    # WSS 隧道方案详细设计（隐蔽性升级，替代 SSH -R）
└── wss-tunnel-plan.md      # WSS 隧道方案实施计划
```

---

## 操作步骤

### 第一步：Windows 启动代理

```powershell
# 默认：端口 18080，账号 proxy / proxy123
python proxy_server.py

# 自定义
python proxy_server.py --port 8888 --user admin --pass myp@ss

# 仅测试用，关闭认证
python proxy_server.py --no-auth
```

命令行参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--port` | 18080 | 代理监听端口 |
| `--bind` | 127.0.0.1 | 绑定地址（仅本机可访问） |
| `--user` | proxy | 认证用户名 |
| `--pass` | proxy123 | 认证密码 |
| `--no-auth` | false | 关闭认证 |

### 第二步：Windows 建立 SSH 反向隧道

```powershell
ssh -R 18080:127.0.0.1:18080 -o ServerAliveInterval=60 user@linux-server
```

> SSH 会话保持打开即可。加 `-o ServerAliveInterval=60` 防止空闲断开。

### 第三步：Linux 验证隧道

```bash
# 检查端口
nc -z 127.0.0.1 18080 -w 3 && echo "OK" || echo "FAIL"

# 通过代理访问
curl -x http://proxy:proxy123@127.0.0.1:18080 http://httpbin.org/ip
```

### 第四步：Linux 配置应用代理

以下各种方式选其一，按需使用。

---

## 各应用接入方式

### 1. 环境变量（curl / wget / pip / npm / 大多数 CLI 工具）

```bash
# 一键配置（推荐用脚本）
source linux-setup.sh

# 或手动设置
export http_proxy=http://proxy:proxy123@127.0.0.1:18080
export https_proxy=http://proxy:proxy123@127.0.0.1:18080
export no_proxy=localhost,127.0.0.1,::1

# 取消代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
```

### 2. Playwright MCP（Claude Code 调用的 Chrome）

Chromium 不读取 `http_proxy` 环境变量，必须通过 `--proxy-server` 参数。

```bash
claude mcp remove playwright

claude mcp add playwright --scope user \
  -e DISPLAY="" \
  -e PLAYWRIGHT_BROWSERS_PATH=/home/polarischen/.cache/ms-playwright \
  -- npx @playwright/mcp@0.0.55 --headless --no-sandbox --caps devtools \
  --ignore-https-errors \
  --proxy-server http://127.0.0.1:18080 \
  --executable-path /home/polarischen/.cache/ms-playwright/chromium-1205/chrome-linux64/chrome
```

> **认证说明**：Chromium 的 `--proxy-server` 不支持 URL 内嵌账号密码。本代理对来自 `127.0.0.1`（SSH 隧道）的请求自动免认证，无需额外处理。

### 3. Chrome / Chromium（手动启动）

```bash
chromium --proxy-server=http://127.0.0.1:18080 --ignore-certificate-errors
```

### 4. Java 应用

#### 方式 A：JVM 启动参数（推荐，不改代码）

```bash
java -Dhttp.proxyHost=127.0.0.1 \
     -Dhttp.proxyPort=18080 \
     -Dhttps.proxyHost=127.0.0.1 \
     -Dhttps.proxyPort=18080 \
     -Dhttp.nonProxyHosts="localhost|127.0.0.1" \
     -jar your-app.jar
```

#### 方式 B：环境变量（部分框架支持）

```bash
export JAVA_TOOL_OPTIONS="-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=18080 -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=18080"
java -jar your-app.jar
```

> `JAVA_TOOL_OPTIONS` 对所有 JVM 进程生效，无需逐个改启动脚本。

#### 认证处理

Java 的 `Authenticator` 机制会自动处理 407 响应。如果代理要求认证：

```bash
java -Dhttp.proxyUser=proxy \
     -Dhttp.proxyPassword=proxy123 \
     -Dhttps.proxyUser=proxy \
     -Dhttps.proxyPassword=proxy123 \
     ...
```

> 但本方案中 Java 通过 SSH 隧道（127.0.0.1）连代理，已自动免认证。

### 5. pip

```bash
# 已设置环境变量则自动生效，或显式指定
pip install --proxy http://proxy:proxy123@127.0.0.1:18080 package-name
```

### 6. npm / yarn

```bash
npm config set proxy http://proxy:proxy123@127.0.0.1:18080
npm config set https-proxy http://proxy:proxy123@127.0.0.1:18080

# 取消
npm config delete proxy
npm config delete https-proxy
```

### 7. Git（clone / fetch / push via HTTPS）

```bash
git config --global http.proxy http://proxy:proxy123@127.0.0.1:18080
git config --global https.proxy http://proxy:proxy123@127.0.0.1:18080

# 取消
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 8. Claude Code（MCP SSE/HTTP 连接）

Claude Code 调用 MCP Server 时（SSE 或 HTTP transport），通过标准 HTTP 代理环境变量路由请求。

> **注意**：Claude Code 不支持 SOCKS 代理，仅支持 HTTP/HTTPS 代理。

#### 方式 A：settings.json（推荐，持久化）

在 `~/.claude/settings.json` 中添加 `env` 字段：

```json
{
  "env": {
    "HTTP_PROXY": "http://127.0.0.1:18080",
    "HTTPS_PROXY": "http://127.0.0.1:18080",
    "NO_PROXY": "localhost,127.0.0.1"
  }
}
```

#### 方式 B：Shell 环境变量

启动 Claude Code 前设置（或 `source linux-setup.sh`）：

```bash
export HTTP_PROXY=http://127.0.0.1:18080
export HTTPS_PROXY=http://127.0.0.1:18080
export NO_PROXY=localhost,127.0.0.1
```

#### 说明

- 代理对 **所有** MCP 连接全局生效，`.mcp.json` 中没有单独的 proxy 字段
- 通过 SSH 隧道连接（来源 `127.0.0.1`），自动免认证，无需在 URL 中带账号密码
- 如果代理使用自签证书，需额外设置：`NODE_EXTRA_CA_CERTS=/path/to/ca.pem`
- SSE transport 已被标记为 deprecated，新版推荐使用 `--transport http`

---

## 代理工作原理

### HTTP 请求流程

```mermaid
sequenceDiagram
    participant App as Linux 应用
    participant Tunnel as SSH 隧道<br/>127.0.0.1:18080
    participant Proxy as Windows 代理
    participant Server as 目标服务器

    App->>Tunnel: GET http://example.com/api HTTP/1.1
    Tunnel->>Proxy: 隧道转发
    Proxy->>Server: GET /api HTTP/1.1<br/>Host: example.com
    Server-->>Proxy: HTTP 200 OK
    Proxy-->>Tunnel: 响应回传
    Tunnel-->>App: 收到响应
```

### HTTPS 请求流程（CONNECT 隧道）

```mermaid
sequenceDiagram
    participant App as Linux 应用
    participant Tunnel as SSH 隧道<br/>127.0.0.1:18080
    participant Proxy as Windows 代理
    participant Server as 目标服务器

    App->>Tunnel: CONNECT example.com:443 HTTP/1.1
    Tunnel->>Proxy: 隧道转发
    Proxy->>Server: TCP 连接 example.com:443
    Server-->>Proxy: 连接建立
    Proxy-->>App: HTTP 200 Connection Established
    Note over App,Server: 后续 TLS 握手 + 加密数据<br/>代理仅做透明转发（看不到明文）
    App->>Server: TLS ClientHello → 加密通信
```

### 认证策略

```mermaid
flowchart TD
    REQ["收到代理请求"] --> CHECK_IP{"来源 IP?"}
    CHECK_IP -->|"127.0.0.1 / ::1"| PASS["✓ 免认证放行"]
    CHECK_IP -->|"其他 IP"| CHECK_AUTH{"Proxy-Authorization?"}
    CHECK_AUTH -->|"有且正确"| PASS
    CHECK_AUTH -->|"无 / 错误"| DENY["✗ 返回 407"]

    style PASS fill:#67c23a,color:#fff
    style DENY fill:#f56c6c,color:#fff
```

- **代理只绑定 `127.0.0.1`**，外部网络无法直连
- **SSH 隧道来源都是 `127.0.0.1`**，自动免认证
- Chromium（不支持代理内嵌认证）和 Java（认证配置繁琐）因此都能无缝使用
- curl/wget 等通过 URL 带认证信息，也正常工作

---

## 安全考量

| 风险点 | 缓解措施 |
|--------|----------|
| 代理被未授权访问 | 绑定 `127.0.0.1`，仅本机和 SSH 隧道可达 |
| 认证信息泄露 | 环境变量仅在 shell 会话内生效；代理对本地连接免认证 |
| HTTPS 中间人 | 代理用 CONNECT 隧道做透明转发，不解密 TLS 流量 |
| SSH 隧道断开 | 加 `ServerAliveInterval=60`；可用 `autossh` 自动重连 |

---

## 故障排查

### 隧道不通

```bash
# Linux 端检查端口
nc -z 127.0.0.1 18080 -w 3

# 如果不通，检查：
# 1. Windows 端代理是否在运行
# 2. SSH 连接是否断开（Windows 终端看）
# 3. sshd_config 是否允许转发
grep AllowTcpForwarding /etc/ssh/sshd_config
# 应为 yes
```

### 代理返回 502

```
curl: (56) Received HTTP code 502 from proxy after CONNECT
```

Windows 代理无法连接目标。检查 Windows 端网络是否能访问目标地址。

### 代理返回 407

```
curl: (56) Received HTTP code 407 from proxy after CONNECT
```

认证失败。检查用户名密码是否正确，或确认连接来源是 `127.0.0.1`。

### Chrome 证书错误

Playwright MCP 已加 `--ignore-https-errors`，一般不会遇到。手动启动 Chrome 加 `--ignore-certificate-errors`。

### Java 连接超时

```bash
# 确认 JAVA_TOOL_OPTIONS 生效
java -XshowSettings:all 2>&1 | grep proxy

# 或在应用启动日志中搜索
grep -i proxy app.log
```

---

## 快速参考

```bash
# ===== Windows 端 =====
python proxy_server.py                                              # 启动代理
ssh -R 18080:127.0.0.1:18080 -o ServerAliveInterval=60 user@linux  # 建立隧道

# ===== Linux 端 =====
source linux-setup.sh                                               # 配置环境变量
curl -x http://127.0.0.1:18080 http://httpbin.org/ip                # 验证 HTTP
curl -x http://127.0.0.1:18080 https://httpbin.org/ip               # 验证 HTTPS
```
