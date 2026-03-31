# WSS 隧道代理方案 — 详细设计文档

## 1. 问题背景

```
Windows (有网络) ──SSH──→ Linux (网络隔离)
```

- Windows 通过 VSCode Remote SSH 连接 Linux
- Linux 无法直接访问外部网络
- Linux 上的应用（curl、Chrome、Java 等）需要借助 Windows 网络访问外部服务

### 现有方案的问题

现有方案使用 SSH 反向隧道（`ssh -R`）+ Python 正向代理，功能完整但存在安全扫描风险：

| 风险点 | 说明 |
|--------|------|
| SSH 隧道特征 | `AllowTcpForwarding` 痕迹、`ss -tlnp` 可见隧道端口 |
| 端口扫描暴露 | 监听端口返回 HTTP 代理响应，特征明显 |
| 流量可分析 | 明文 HTTP 代理流量，深度包检测可识别 |

### 设计目标

| 目标 | 要求 |
|------|------|
| 功能等价 | 所有 HTTP/HTTPS 请求统一走代理出网，零代码改动 |
| 端口扫描隐蔽 | 扫描器看到的是普通 HTTPS 服务（TLS 握手 + 网页响应） |
| 流量不可分析 | TLS 加密，深度包检测无法识别隧道流量 |
| 无 SSH 依赖 | 不使用 `ssh -R`，无 SSH 隧道特征 |
| 部署简单 | 纯 Python，仅依赖 `websockets` 库 |

---

## 2. 方案架构

### 2.1 整体拓扑

```mermaid
graph LR
    subgraph Linux["Linux 服务端（网络隔离）"]
        APP["应用层<br/>curl / Chrome / Java"]
        LP["Local Proxy<br/>127.0.0.1:18080"]
        TS["WSS Server<br/>0.0.0.0:9443<br/>(TLS 加密)"]
    end

    subgraph Windows["Windows（有网络）"]
        TC["WSS Client<br/>主动连接 Linux:9443"]
        OUT["出网请求"]
    end

    subgraph Internet["目标网络"]
        HTTP["HTTP 站点"]
        HTTPS["HTTPS 站点"]
        API["内部 API"]
    end

    APP -->|"http_proxy / --proxy-server"| LP
    LP -->|"内部转发"| TS
    TS <-.->|"WSS 加密隧道<br/>单连接多路复用"| TC
    TC --> OUT
    OUT --> HTTP
    OUT --> HTTPS
    OUT --> API

    style APP fill:#4a90d9,color:#fff
    style LP fill:#4a90d9,color:#fff
    style TS fill:#e6a23c,color:#fff
    style TC fill:#e6a23c,color:#fff
    style HTTP fill:#67c23a,color:#fff
    style HTTPS fill:#67c23a,color:#fff
    style API fill:#67c23a,color:#fff
```

### 2.2 核心角色

| 组件 | 运行位置 | 监听地址 | 职责 |
|------|----------|----------|------|
| **WSS Server** | Linux | `0.0.0.0:9443` | TLS 加密端点；接受 Windows 客户端连接；对普通访问返回伪装网页 |
| **Local Proxy** | Linux | `127.0.0.1:18080` | HTTP/HTTPS 代理入口；应用层统一配置此地址 |
| **WSS Client** | Windows | — (主动连接) | 连接 Linux WSS Server；接收代理请求并执行出网 |

### 2.3 与现有方案对比

| | SSH -R + proxy_server.py | WSS 隧道方案 |
|---|---|---|
| 依赖 SSH 隧道 | 是（`ssh -R`） | **否** |
| 端口扫描特征 | HTTP 代理响应 | **TLS/HTTPS 网页** |
| 流量可分析 | 明文代理流量 | **TLS 加密，不可分析** |
| 连接方向 | Windows → Linux (SSH) | **Windows → Linux (WSS)** |
| 新增端口 | 18080（明文代理） | 9443（TLS）+ 18080（仅 127.0.0.1） |
| 杀软/EDR 风险 | 低 | **低（纯 Python 脚本，合法库）** |

---

## 3. 通信协议

### 3.1 消息格式

WSS 隧道内部使用 JSON 文本消息。每条消息包含 `type` 和 `id` 字段：

```json
{
    "type": "connect",
    "id": "a1b2c3",
    "host": "example.com",
    "port": 443
}
```

### 3.2 消息类型

| type | 方向 | 用途 | 字段 |
|------|------|------|------|
| `connect` | Linux → Windows | 请求建立到目标的 TCP 连接 | `id`, `host`, `port` |
| `connect_ok` | Windows → Linux | 连接目标成功 | `id` |
| `connect_fail` | Windows → Linux | 连接目标失败 | `id`, `error` |
| `data` | 双向 | 传输数据（base64 编码） | `id`, `payload` |
| `close` | 双向 | 关闭某个连接 | `id` |
| `ping` / `pong` | 双向 | 心跳保活 | — |

### 3.3 多路复用

单条 WSS 连接上通过 `id` 字段区分多个并发代理请求：

```mermaid
graph TD
    subgraph WSS["单条 WSS 加密连接"]
        MUX["多路复用器"]
    end

    subgraph Streams["并发流"]
        S1["id:a1 → example.com:80"]
        S2["id:b2 → google.com:443"]
        S3["id:c3 → api.github.com:443"]
    end

    MUX --> S1
    MUX --> S2
    MUX --> S3

    style WSS fill:#e6a23c,color:#fff
    style S1 fill:#67c23a,color:#fff
    style S2 fill:#67c23a,color:#fff
    style S3 fill:#67c23a,color:#fff
```

### 3.4 HTTP 请求流程

```mermaid
sequenceDiagram
    participant App as Linux 应用
    participant LP as Local Proxy<br/>127.0.0.1:18080
    participant TS as WSS Server
    participant TC as WSS Client<br/>(Windows)
    participant Target as 目标服务器

    App->>LP: GET http://example.com/api
    LP->>LP: 解析目标 host:port
    LP->>TS: connect {id:"a1", host:"example.com", port:80}
    TS->>TC: WSS 转发 connect 消息
    TC->>Target: TCP connect example.com:80
    TC->>TS: connect_ok {id:"a1"}
    TS->>LP: 连接就绪

    LP->>TS: data {id:"a1", payload:"GET /api HTTP/1.1\r\n..."}
    TS->>TC: WSS 转发 data
    TC->>Target: 发送 HTTP 请求

    Target-->>TC: HTTP/1.1 200 OK...
    TC->>TS: data {id:"a1", payload:"HTTP/1.1 200..."}
    TS->>LP: 回传响应数据
    LP-->>App: HTTP 200 OK

    LP->>TS: close {id:"a1"}
    TS->>TC: WSS 转发 close
    TC->>TC: 关闭到 Target 的 TCP 连接
```

### 3.5 HTTPS CONNECT 隧道流程

```mermaid
sequenceDiagram
    participant App as Linux 应用
    participant LP as Local Proxy
    participant TS as WSS Server
    participant TC as WSS Client
    participant Target as 目标 :443

    App->>LP: CONNECT example.com:443 HTTP/1.1
    LP->>TS: connect {id:"b2", host:"example.com", port:443}
    TS->>TC: WSS 转发
    TC->>Target: TCP connect example.com:443
    TC->>TS: connect_ok {id:"b2"}
    TS->>LP: 连接就绪
    LP-->>App: HTTP/1.1 200 Connection Established

    Note over App,Target: 后续 TLS 握手 + 加密数据<br/>全部封装为 data 消息透传<br/>代理看不到明文

    App->>LP: [TLS ClientHello...]
    LP->>TS: data {id:"b2", payload:"base64..."}
    TS->>TC: WSS 转发
    TC->>Target: 转发原始字节

    Target-->>TC: [TLS ServerHello...]
    TC->>TS: data {id:"b2", payload:"base64..."}
    TS->>LP: 回传
    LP-->>App: [TLS 握手继续...]

    Note over App,Target: TLS 握手完成后<br/>应用与目标直接加密通信<br/>隧道仅做字节透传
```

---

## 4. 安全设计

### 4.1 认证与鉴权

```mermaid
flowchart TD
    REQ["请求到达 :9443"] --> TLS["TLS 握手完成"]
    TLS --> PATH{"请求路径?"}
    PATH -->|"/ 或其他普通路径"| FAKE["返回伪装 HTML 页面<br/>(模拟内部 Dashboard)"]
    PATH -->|"/ws"| UPGRADE{"WebSocket 升级请求?"}
    UPGRADE -->|"否"| FAKE
    UPGRADE -->|"是"| TOKEN{"Sec-WebSocket-Protocol<br/>包含有效 Token?"}
    TOKEN -->|"否"| DENY["返回 403 Forbidden"]
    TOKEN -->|"是"| ACCEPT["建立 WSS 隧道连接"]

    style FAKE fill:#67c23a,color:#fff
    style DENY fill:#f56c6c,color:#fff
    style ACCEPT fill:#4a90d9,color:#fff
```

**Token 机制说明：**

- Token 在首次初始化时随机生成（32 字节 hex），存储在配置文件中
- 客户端连接时通过 `Sec-WebSocket-Protocol` 头传递（WS 标准字段，不会引起注意）
- Token 错误直接返回 403，与普通 HTTPS 网站行为一致

### 4.2 TLS 证书管理

```mermaid
flowchart LR
    INIT["首次 --init"] --> GEN["生成自签名证书<br/>cert.pem + key.pem<br/>(Python ssl stdlib)"]
    GEN --> STORE["存储到 ~/.wss-tunnel/<br/>权限 600"]
    GEN --> FP["计算证书指纹<br/>SHA256:xxxx..."]
    FP --> PRINT["打印指纹 + Token<br/>给管理员"]
    PRINT --> CLIENT["Windows 客户端配置<br/>--fingerprint SHA256:xxxx"]
    CLIENT --> VERIFY{"连接时校验<br/>证书指纹匹配?"}
    VERIFY -->|"匹配"| OK["连接建立"]
    VERIFY -->|"不匹配"| REJECT["拒绝连接<br/>防止中间人攻击"]

    style GEN fill:#e6a23c,color:#fff
    style OK fill:#67c23a,color:#fff
    style REJECT fill:#f56c6c,color:#fff
```

- **不依赖 CA 体系**，通过证书指纹 pinning 验证身份
- 自签证书有效期默认 365 天，可通过 `--init` 重新生成
- 证书文件权限 `600`，仅 owner 可读

### 4.3 伪装策略

当扫描器或浏览器直接访问 `:9443` 时，返回一个静态 HTML 页面：

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Server: nginx/1.24.0

<!DOCTYPE html>
<html>
<head><title>Internal Dashboard</title></head>
<body>
    <h1>System Status</h1>
    <p>All services operational.</p>
    <p>Last updated: 2024-01-15 10:30:00 UTC</p>
</body>
</html>
```

伪装要点：

| 细节 | 实现 |
|------|------|
| Server 头 | 返回 `nginx/1.24.0`，不暴露 Python |
| 响应结构 | 标准 HTML，看起来像内部监控页面 |
| 404 处理 | 未知路径返回标准 404 页面 |
| WS 升级无 Token | 返回 403，和普通网站行为一致 |

### 4.4 安全层级总览

```mermaid
graph TD
    subgraph L1["第一层：网络层"]
        TLS_ENC["TLS 1.2+ 加密<br/>扫描器只看到 TLS 握手"]
    end

    subgraph L2["第二层：协议层"]
        DISGUISE["HTTPS 伪装<br/>普通访问返回网页<br/>Server: nginx/1.24.0"]
    end

    subgraph L3["第三层：认证层"]
        TOKEN_AUTH["Token 鉴权<br/>Sec-WebSocket-Protocol<br/>无 Token → 403"]
    end

    subgraph L4["第四层：传输层"]
        CERT_PIN["证书指纹 Pinning<br/>防中间人攻击"]
    end

    subgraph L5["第五层：主机层"]
        LOCAL_ONLY["Local Proxy 仅绑定 127.0.0.1<br/>外部无法直连代理"]
    end

    L1 --> L2 --> L3 --> L4 --> L5

    style L1 fill:#4a90d9,color:#fff
    style L2 fill:#4a90d9,color:#fff
    style L3 fill:#e6a23c,color:#fff
    style L4 fill:#e6a23c,color:#fff
    style L5 fill:#67c23a,color:#fff
```

---

## 5. 组件详细设计

### 5.1 文件结构

```
dev_project/proxy-tunnel/
├── proxy-tunnel-guide.md          # 现有文档（SSH 方案）
├── proxy_server.py                # 现有 SSH 方案代理
├── linux-setup.sh                 # 现有 Linux 配置脚本
├── wss-tunnel-design.md           # 本设计文档
│
└── wss-tunnel/                    # WSS 隧道方案
    ├── tunnel_server.py           # Linux 端：WSS Server + Local Proxy
    ├── tunnel_client.py           # Windows 端：WSS Client + 出网执行
    ├── tunnel_common.py           # 共享：消息协议、证书生成、Token 工具
    └── setup_linux.sh             # Linux 端启动辅助脚本
```

### 5.2 tunnel_common.py — 共享模块

**职责**：消息协议、证书工具、Token 管理

```mermaid
classDiagram
    class MessageProtocol {
        +make_connect(id, host, port) str
        +make_connect_ok(id) str
        +make_connect_fail(id, error) str
        +make_data(id, payload_bytes) str
        +make_close(id) str
        +parse(raw_str) dict
    }

    class CertManager {
        +generate_self_signed(cert_dir, days=365)
        +get_fingerprint(cert_path) str
        +load_or_generate(cert_dir) tuple
    }

    class TokenManager {
        +generate_token() str
        +save_token(token, config_path)
        +load_token(config_path) str
    }
```

**消息协议详细定义：**

```python
# connect: 请求建立到目标的 TCP 连接
{"type": "connect", "id": "a1b2c3", "host": "example.com", "port": 443}

# connect_ok: 目标连接成功
{"type": "connect_ok", "id": "a1b2c3"}

# connect_fail: 目标连接失败
{"type": "connect_fail", "id": "a1b2c3", "error": "Connection refused"}

# data: 传输数据（base64 编码的原始字节）
{"type": "data", "id": "a1b2c3", "payload": "R0VUIi8gSFRUUC8xLjE..."}

# close: 关闭连接
{"type": "close", "id": "a1b2c3"}
```

**证书生成**（使用 Python ssl stdlib）：

```python
# 基于 ssl 模块生成自签名证书
# 有效期：365 天
# 密钥：RSA 2048
# 存储路径：~/.wss-tunnel/cert.pem, ~/.wss-tunnel/key.pem
# 文件权限：600
```

### 5.3 tunnel_server.py — Linux 端

**职责**：WSS Server（接受 Windows 连接）+ Local Proxy（接受应用代理请求）

```mermaid
graph TD
    subgraph Server["tunnel_server.py (单个 asyncio 进程)"]
        subgraph WSS["WSS Server (:9443)"]
            HTTPS_HANDLER["HTTPS 请求处理<br/>伪装页面响应"]
            WS_HANDLER["WebSocket 处理<br/>Token 鉴权<br/>消息收发"]
        end

        subgraph Proxy["Local Proxy (127.0.0.1:18080)"]
            HTTP_PROXY["HTTP 代理<br/>GET/POST/PUT/DELETE..."]
            CONNECT_PROXY["CONNECT 代理<br/>HTTPS 隧道"]
        end

        subgraph Core["核心"]
            TUNNEL_MGR["TunnelManager<br/>管理 WSS 连接<br/>消息路由"]
            STREAM_MAP["StreamMap<br/>id → asyncio.Queue<br/>多路复用映射"]
        end
    end

    HTTP_PROXY --> TUNNEL_MGR
    CONNECT_PROXY --> TUNNEL_MGR
    TUNNEL_MGR --> WS_HANDLER
    WS_HANDLER --> STREAM_MAP

    style WSS fill:#e6a23c,color:#fff
    style Proxy fill:#4a90d9,color:#fff
    style Core fill:#67c23a,color:#fff
```

**核心类设计：**

```mermaid
classDiagram
    class TunnelManager {
        -ws_connection: WebSocket
        -streams: dict[str, asyncio.Queue]
        -connected: asyncio.Event
        +register_client(ws)
        +unregister_client()
        +send_connect(id, host, port)
        +send_data(id, payload)
        +send_close(id)
        +wait_response(id) dict
        +dispatch_incoming(msg)
    }

    class LocalProxy {
        -tunnel: TunnelManager
        -server: asyncio.Server
        +start(bind, port)
        +handle_client(reader, writer)
        -_handle_connect(method, target)
        -_handle_http(method, url, headers, body)
        -_relay_data(stream_id, reader, writer)
    }

    class WSSServer {
        -tunnel: TunnelManager
        -ssl_context: ssl.SSLContext
        -token: str
        +start(bind, port)
        +handle_connection(websocket)
        -_serve_disguise_page(path) bytes
        -_verify_token(ws) bool
    }

    TunnelManager --> WSSServer : 被 WSS 连接驱动
    TunnelManager --> LocalProxy : 被代理请求驱动
```

**Local Proxy 处理逻辑：**

```mermaid
flowchart TD
    CLIENT["应用连接 127.0.0.1:18080"] --> PARSE["解析请求行"]
    PARSE --> METHOD{"请求方法?"}

    METHOD -->|"CONNECT"| CONNECT_FLOW["HTTPS 隧道流程"]
    METHOD -->|"GET/POST/..."| HTTP_FLOW["HTTP 代理流程"]

    CONNECT_FLOW --> CHECK_TUNNEL{"WSS 隧道<br/>已连接?"}
    HTTP_FLOW --> CHECK_TUNNEL

    CHECK_TUNNEL -->|"否"| ERR502["返回 502<br/>隧道未就绪"]
    CHECK_TUNNEL -->|"是"| SEND_CONNECT["发送 connect 消息<br/>到 Windows"]

    SEND_CONNECT --> WAIT{"等待响应"}
    WAIT -->|"connect_ok"| RELAY["双向 data 转发"]
    WAIT -->|"connect_fail"| ERR502_2["返回 502<br/>目标不可达"]
    WAIT -->|"超时 10s"| ERR504["返回 504<br/>Gateway Timeout"]

    RELAY --> DONE["连接关闭<br/>发送 close 消息"]

    style ERR502 fill:#f56c6c,color:#fff
    style ERR502_2 fill:#f56c6c,color:#fff
    style ERR504 fill:#f56c6c,color:#fff
    style RELAY fill:#67c23a,color:#fff
```

### 5.4 tunnel_client.py — Windows 端

**职责**：WSS Client（连接 Linux）+ 出网执行

```mermaid
graph TD
    subgraph Client["tunnel_client.py (单个 asyncio 进程)"]
        WS_CLIENT["WSS Client<br/>连接 Linux:9443"]
        DISPATCHER["消息分发器<br/>按 id 路由"]
        CONN_POOL["连接池<br/>id → TCP Socket"]
        RECONNECT["断线重连<br/>指数退避"]
    end

    WS_CLIENT --> DISPATCHER
    DISPATCHER --> CONN_POOL
    CONN_POOL --> INTERNET["目标服务器"]
    WS_CLIENT -.-> RECONNECT

    style Client fill:#e6a23c,color:#fff
    style INTERNET fill:#67c23a,color:#fff
```

**消息处理逻辑：**

```mermaid
flowchart TD
    MSG["收到 WSS 消息"] --> TYPE{"消息类型?"}

    TYPE -->|"connect"| TCP_CONNECT["TCP 连接目标<br/>host:port"]
    TCP_CONNECT --> RESULT{"连接结果?"}
    RESULT -->|"成功"| REPLY_OK["发送 connect_ok<br/>启动读取协程"]
    RESULT -->|"失败"| REPLY_FAIL["发送 connect_fail"]

    TYPE -->|"data"| FIND_CONN["查找 id 对应的<br/>TCP 连接"]
    FIND_CONN --> FORWARD["转发 payload<br/>到目标服务器"]

    TYPE -->|"close"| CLOSE_CONN["关闭 id 对应的<br/>TCP 连接"]

    REPLY_OK --> READ_LOOP["异步读取目标响应<br/>封装为 data 消息回传"]

    style REPLY_OK fill:#67c23a,color:#fff
    style REPLY_FAIL fill:#f56c6c,color:#fff
    style READ_LOOP fill:#4a90d9,color:#fff
```

**断线重连策略：**

```mermaid
flowchart LR
    DISCONNECT["WSS 连接断开"] --> WAIT1["等待 1s"]
    WAIT1 --> RETRY1["重连尝试 1"]
    RETRY1 -->|"失败"| WAIT2["等待 2s"]
    WAIT2 --> RETRY2["重连尝试 2"]
    RETRY2 -->|"失败"| WAIT4["等待 4s"]
    WAIT4 --> RETRY3["重连尝试 3"]
    RETRY3 -->|"失败"| WAITN["等待 min(2^n, 60)s"]
    WAITN --> RETRYN["重连尝试 n"]
    RETRY1 -->|"成功"| OK["隧道恢复"]
    RETRY2 -->|"成功"| OK
    RETRY3 -->|"成功"| OK
    RETRYN -->|"成功"| OK

    style OK fill:#67c23a,color:#fff
    style DISCONNECT fill:#f56c6c,color:#fff
```

---

## 6. 启动与部署

### 6.1 首次初始化

```mermaid
sequenceDiagram
    participant Admin as 操作人员
    participant Linux as Linux 服务器
    participant Windows as Windows 开发机

    Note over Admin,Linux: 第一步：Linux 初始化
    Admin->>Linux: python tunnel_server.py --init
    Linux->>Linux: 生成 ~/.wss-tunnel/cert.pem
    Linux->>Linux: 生成 ~/.wss-tunnel/key.pem
    Linux->>Linux: 生成 ~/.wss-tunnel/config.json (含 Token)
    Linux-->>Admin: 打印 Token 和证书指纹

    Note over Admin: 记录 Token 和指纹

    Note over Admin,Windows: 第二步：安装依赖
    Admin->>Linux: pip install websockets
    Admin->>Windows: pip install websockets

    Note over Admin: 部署文件
    Admin->>Linux: 上传 tunnel_server.py + tunnel_common.py
    Admin->>Windows: 上传 tunnel_client.py + tunnel_common.py
```

### 6.2 日常使用

```bash
# ===== Linux 端 =====
python tunnel_server.py
# 输出:
# WSS Server listening on 0.0.0.0:9443 (TLS)
# Local Proxy listening on 127.0.0.1:18080
# Waiting for tunnel client...

# ===== Windows 端 =====
python tunnel_client.py --host <linux-ip> --port 9443 \
    --token <token> --fingerprint <SHA256:xxxx>
# 输出:
# Connected to wss://linux-ip:9443/ws
# Tunnel established, ready to relay.

# ===== Linux 端验证 =====
curl -x http://127.0.0.1:18080 http://httpbin.org/ip
curl -x http://127.0.0.1:18080 https://httpbin.org/ip
```

### 6.3 命令行参数

**tunnel_server.py (Linux):**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--init` | — | 首次初始化：生成证书和 Token |
| `--wss-port` | 9443 | WSS Server 监听端口 |
| `--wss-bind` | 0.0.0.0 | WSS Server 绑定地址 |
| `--proxy-port` | 18080 | Local Proxy 监听端口 |
| `--proxy-bind` | 127.0.0.1 | Local Proxy 绑定地址（仅本机） |
| `--cert-dir` | ~/.wss-tunnel | 证书和配置存储目录 |

**tunnel_client.py (Windows):**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | （必填） | Linux 服务器地址 |
| `--port` | 9443 | WSS Server 端口 |
| `--token` | （必填） | 鉴权 Token |
| `--fingerprint` | （必填） | 证书指纹（SHA256） |
| `--reconnect` | true | 断线自动重连 |
| `--max-retry` | 0 (无限) | 最大重连次数 |

### 6.4 应用配置

应用层配置与现有 SSH 方案**完全一致**，无需改动：

```bash
# 环境变量（curl / wget / pip / npm）
export http_proxy=http://127.0.0.1:18080
export https_proxy=http://127.0.0.1:18080
export no_proxy=localhost,127.0.0.1,::1

# Playwright MCP（Chromium）
--proxy-server http://127.0.0.1:18080

# Java
-Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=18080

# Git
git config --global http.proxy http://127.0.0.1:18080
```

> **注意**：WSS 方案的 Local Proxy 不需要认证（仅绑定 127.0.0.1），所以代理 URL 中无需 `user:pass@`，比 SSH 方案更简洁。

---

## 7. 错误处理

### 7.1 错误场景与处理

```mermaid
flowchart TD
    subgraph Errors["错误场景"]
        E1["WSS 隧道未连接"]
        E2["目标服务器不可达"]
        E3["WSS 连接中断"]
        E4["目标连接超时"]
        E5["消息格式错误"]
    end

    subgraph Responses["处理方式"]
        R1["Local Proxy 返回 502<br/>Bad Gateway"]
        R2["发送 connect_fail<br/>Local Proxy 返回 502"]
        R3["Windows 自动重连<br/>队列中请求返回 502"]
        R4["发送 connect_fail<br/>Local Proxy 返回 504"]
        R5["记录日志，忽略消息"]
    end

    E1 --> R1
    E2 --> R2
    E3 --> R3
    E4 --> R4
    E5 --> R5

    style E1 fill:#f56c6c,color:#fff
    style E2 fill:#f56c6c,color:#fff
    style E3 fill:#f56c6c,color:#fff
    style E4 fill:#f56c6c,color:#fff
    style E5 fill:#f56c6c,color:#fff
```

### 7.2 资源清理

```mermaid
flowchart TD
    EVENT["连接关闭事件"] --> WHO{"哪端关闭?"}

    WHO -->|"应用端关闭"| APP_CLOSE["Local Proxy 检测到 EOF"]
    APP_CLOSE --> SEND_CLOSE["发送 close 消息到 Windows"]
    SEND_CLOSE --> WIN_CLOSE["Windows 关闭到目标的 TCP 连接"]
    WIN_CLOSE --> CLEANUP1["清理 StreamMap 条目"]

    WHO -->|"目标端关闭"| TARGET_CLOSE["Windows 检测到目标 EOF"]
    TARGET_CLOSE --> SEND_CLOSE2["发送 close 消息到 Linux"]
    SEND_CLOSE2 --> PROXY_CLOSE["Local Proxy 关闭到应用的连接"]
    PROXY_CLOSE --> CLEANUP2["清理 StreamMap 条目"]

    WHO -->|"WSS 隧道断开"| TUNNEL_DOWN["所有活跃流收到错误"]
    TUNNEL_DOWN --> CLOSE_ALL["关闭所有应用连接<br/>清理所有 StreamMap"]
    CLOSE_ALL --> RECONNECT["Windows 开始自动重连"]
```

---

## 8. 性能考量

### 8.1 开销分析

| 层 | 开销 | 说明 |
|----|------|------|
| TLS 加密 | ~5% CPU | 仅握手阶段较重，后续对称加密开销小 |
| JSON 消息解析 | ~1% | 消息头很小，payload 是 base64 |
| base64 编码 | ~33% 体积膨胀 | 文本 WebSocket 帧的代价 |
| asyncio 调度 | 极低 | 事件驱动，无线程切换开销 |

### 8.2 优化选项

| 优化 | 方式 | 效果 |
|------|------|------|
| 减少体积膨胀 | 使用 binary WebSocket 帧代替 text | payload 无需 base64，体积 -33% |
| 大文件传输 | 分片发送，避免单帧过大 | 降低内存峰值 |
| 并发连接 | asyncio 天然支持数千并发 | 无需线程池 |

> 对于日常开发使用场景（curl、浏览器、API 调用），性能开销可忽略不计。

---

## 9. 故障排查

### 9.1 排查流程图

```mermaid
flowchart TD
    START["应用无法通过代理出网"] --> CHECK1{"curl -x http://127.0.0.1:18080<br/>http://httpbin.org/ip"}

    CHECK1 -->|"Connection refused"| FIX1["tunnel_server.py 未运行<br/>→ 启动 tunnel_server.py"]

    CHECK1 -->|"502 Bad Gateway"| CHECK2{"Windows 端<br/>tunnel_client.py 状态?"}
    CHECK2 -->|"未运行"| FIX2["启动 tunnel_client.py"]
    CHECK2 -->|"运行中但显示 Reconnecting"| CHECK3{"Linux :9443 端口可达?"}
    CHECK3 -->|"不可达"| FIX3["检查防火墙<br/>或 tunnel_server 是否监听"]
    CHECK3 -->|"可达"| FIX4["检查 Token/指纹<br/>是否匹配"]

    CHECK1 -->|"504 Gateway Timeout"| FIX5["Windows 无法连接目标<br/>检查 Windows 网络"]

    CHECK1 -->|"正常响应"| OK["代理工作正常"]

    style OK fill:#67c23a,color:#fff
    style FIX1 fill:#f56c6c,color:#fff
    style FIX2 fill:#f56c6c,color:#fff
    style FIX3 fill:#f56c6c,color:#fff
    style FIX4 fill:#f56c6c,color:#fff
    style FIX5 fill:#f56c6c,color:#fff
```

### 9.2 常用诊断命令

```bash
# Linux 端 —— 检查服务是否在运行
ps aux | grep tunnel_server

# Linux 端 —— 检查 WSS 端口
nc -z 127.0.0.1 9443 -w 3 && echo "WSS OK" || echo "WSS FAIL"

# Linux 端 —— 检查代理端口
nc -z 127.0.0.1 18080 -w 3 && echo "Proxy OK" || echo "Proxy FAIL"

# Linux 端 —— 测试伪装页面（应该看到 HTML）
curl -k https://127.0.0.1:9443/

# Linux 端 —— 测试代理
curl -x http://127.0.0.1:18080 http://httpbin.org/ip
curl -x http://127.0.0.1:18080 https://httpbin.org/ip

# Windows 端 —— 检查到 Linux 的连通性
Test-NetConnection -ComputerName <linux-ip> -Port 9443
```

---

## 10. 安全总览

| 威胁 | 缓解措施 |
|------|----------|
| 端口扫描发现代理 | TLS 加密 + 伪装 HTML 页面 + `Server: nginx/1.24.0` |
| 流量深度分析 | TLS 加密，内部协议不可见 |
| SSH 隧道特征检测 | 完全不使用 SSH 隧道 |
| 中间人攻击 | 证书指纹 pinning |
| 未授权使用隧道 | Token 鉴权 + TLS 双向加密 |
| 本地代理被滥用 | 绑定 `127.0.0.1`，仅本机可达 |
| Token 泄露 | 存储在 `~/.wss-tunnel/config.json`，权限 600 |
| 杀软/EDR 误报 | 纯 Python 脚本运行，不打包 exe；合法 PyPI 库 |

---

## 11. 快速参考

```bash
# ===== 首次部署 =====

# Linux: 初始化证书和 Token
python tunnel_server.py --init
# → 记录输出的 Token 和 Fingerprint

# 安装依赖（两端）
pip install websockets

# ===== 日常使用 =====

# Linux: 启动服务
python tunnel_server.py

# Windows: 连接隧道
python tunnel_client.py --host <linux-ip> --token <token> --fingerprint <fingerprint>

# Linux: 配置代理
export http_proxy=http://127.0.0.1:18080
export https_proxy=http://127.0.0.1:18080
export no_proxy=localhost,127.0.0.1,::1

# Linux: 验证
curl -x http://127.0.0.1:18080 http://httpbin.org/ip
curl -x http://127.0.0.1:18080 https://httpbin.org/ip
```
