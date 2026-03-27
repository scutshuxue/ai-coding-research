# Mutagen 文件同步工具使用指南

## 目录

- [简介](#简介)
- [工作原理](#工作原理)
- [安装](#安装)
- [基础使用](#基础使用)
- [项目模式](#项目模式)
- [配置详解](#配置详解)
- [常用命令速查](#常用命令速查)
- [实用技巧](#实用技巧)
- [常见问题](#常见问题)

---

## 简介

Mutagen 是一款专为开发者设计的高性能跨平台文件同步工具，支持 Windows、Linux、macOS 之间的双向实时同步。相比 rsync、SSHFS 等传统方案，Mutagen 在代码开发场景下有更好的性能和体验。

**核心特点：**

- 跨平台：Windows / Linux / macOS 任意组合
- 双向实时同步，增量传输
- 自动处理 Windows/Linux 换行符差异
- 远程端无需安装 Mutagen（自动推送 agent）
- 支持 SSH、Docker 容器等多种传输方式

---

## 工作原理

```
┌──────────────┐         SSH          ┌──────────────┐
│  Windows 本地 │ ◄──────────────────► │  Linux 远程   │
│              │                      │              │
│  Mutagen     │    加密传输通道        │  Mutagen     │
│  Daemon      │ ◄──────────────────► │  Agent       │
│  (常驻后台)   │                      │  (自动部署)   │
│              │                      │              │
│  Alpha 端    │    增量差异同步        │  Beta 端     │
│  (本地文件)   │ ◄──────────────────► │  (远程文件)   │
└──────────────┘                      └──────────────┘
```

### 核心概念

| 概念 | 说明 |
|------|------|
| **Alpha** | 同步会话的第一端（通常是本地） |
| **Beta** | 同步会话的第二端（通常是远程） |
| **Daemon** | 本地常驻后台进程，管理所有同步会话 |
| **Agent** | 远程端的轻量代理进程，由 Mutagen 自动部署，无需手动安装 |
| **Session** | 一个同步会话，定义了 Alpha 和 Beta 之间的同步关系 |
| **Staging** | 暂存区，Mutagen 先把变更存入暂存区，再应用到目标端 |

### 同步流程

1. 本地 Daemon 通过 SSH 连接远程服务器
2. 首次连接时自动将 Agent 二进制文件推送到远程
3. 两端分别扫描文件系统，生成快照
4. 对比快照差异，计算增量变更
5. 仅传输变更部分，应用到对端
6. 持续监听文件变化，实时增量同步

### 同步模式

| 模式 | 说明 |
|------|------|
| `two-way-safe` | 默认模式，双向同步，遇到冲突时不自动解决，需手动处理 |
| `two-way-resolved` | 双向同步，冲突时 Alpha 端优先 |
| `one-way-safe` | 单向同步（Alpha → Beta），Beta 端的变更会被标记为冲突 |
| `one-way-replica` | 单向镜像（Alpha → Beta），Beta 端的变更会被覆盖 |

---

## 安装

### Windows

**方法一：Scoop（推荐）**

```powershell
scoop install mutagen
```

**方法二：手动下载**

1. 前往 [GitHub Releases](https://github.com/mutagen-io/mutagen/releases) 下载 `mutagen_windows_amd64_v*.zip`
2. 解压，将 `mutagen.exe` 放到 PATH 目录下（如 `C:\Users\你的用户名\bin\`）
3. 验证：

```powershell
mutagen version
```

### Linux

```bash
# 下载最新版
curl -fsSL https://github.com/mutagen-io/mutagen/releases/latest/download/mutagen_linux_amd64_v*.tar.gz -o mutagen.tar.gz

# 或指定版本（推荐，避免通配符问题）
# 前往 https://github.com/mutagen-io/mutagen/releases 查看最新版本号
curl -fsSL https://github.com/mutagen-io/mutagen/releases/download/v0.18.1/mutagen_linux_amd64_v0.18.1.tar.gz -o mutagen.tar.gz

# 解压并安装
tar xzf mutagen.tar.gz
sudo mv mutagen /usr/local/bin/
rm mutagen.tar.gz

# 验证
mutagen version
```

### macOS

```bash
brew install mutagen-io/mutagen/mutagen
```

> **注意：** 远程端（Linux 服务器）不需要手动安装 Mutagen，首次连接时会自动推送 Agent。只需确保远程服务器有 SSH 访问权限即可。

---

## 基础使用

### 使用 `mutagen sync create` 创建会话

```powershell
# 基本用法
mutagen sync create <本地路径> <远程路径>

# 示例：Windows 同步到 Linux
mutagen sync create C:\code\myproject user@192.168.1.100:/home/user/myproject

# 附加选项
mutagen sync create \
  --name=my-sync \
  --ignore-vcs \
  --sync-mode=two-way-resolved \
  C:\code\myproject user@192.168.1.100:/home/user/myproject
```

### 管理会话

```powershell
# 查看所有同步会话
mutagen sync list

# 查看详细信息
mutagen sync list -l

# 暂停会话
mutagen sync pause <session-name-or-id>

# 恢复会话
mutagen sync resume <session-name-or-id>

# 强制重新同步
mutagen sync reset <session-name-or-id>

# 删除会话
mutagen sync terminate <session-name-or-id>
```

### 查看实时状态

```powershell
# 持续监控同步状态
mutagen sync monitor
```

---

## 项目模式

`mutagen project` 通过项目根目录的 `mutagen.yml`（注意：**没有前导点号**）配置文件管理同步，更适合团队协作和多目录场景。

> **重要区别：** `mutagen sync create` 不会读取 `mutagen.yml`，只有 `mutagen project start` 才会。

### 配置文件

在项目根目录创建 `mutagen.yml`：

```yaml
sync:
  code:                                # 会话名称，自定义
    alpha: "."                         # 本地目录（. = 当前项目目录）
    beta: "user@192.168.1.100:/home/user/myproject"  # 远程目录
    mode: "two-way-resolved"           # 同步模式
    ignore:
      vcs: true                        # 忽略 .git/ 目录
      paths:                           # 自定义忽略规则
        - "node_modules/"
        - "target/"
        - "dist/"
        - "build/"
        - "__pycache__/"
        - "*.pyc"
        - ".env"
        - ".env.*"
        - "*.log"
```

### 项目命令

```powershell
# 进入项目目录
cd C:\code\myproject

# 启动同步（读取 mutagen.yml）
mutagen project start

# 查看状态
mutagen project list

# 暂停
mutagen project pause

# 恢复
mutagen project resume

# 停止并删除会话
mutagen project terminate
```

### 多目录同步配置

```yaml
sync:
  frontend:
    alpha: "./frontend"
    beta: "user@server:/home/user/project/frontend"
    mode: "two-way-resolved"
    ignore:
      vcs: true
      paths:
        - "node_modules/"
        - "dist/"

  backend:
    alpha: "./backend"
    beta: "user@server:/home/user/project/backend"
    mode: "two-way-resolved"
    ignore:
      vcs: true
      paths:
        - "target/"
        - "__pycache__/"
        - "*.pyc"
```

---

## 配置详解

### 全局配置文件

位置：`~/.mutagen.yml`

- Windows: `C:\Users\你的用户名\.mutagen.yml`
- Linux/macOS: `~/.mutagen.yml`

全局配置对所有会话生效，需要手动创建：

```powershell
# Windows PowerShell
notepad $env:USERPROFILE\.mutagen.yml
```

```yaml
sync:
  defaults:
    ignore:
      vcs: true
      paths:
        - "node_modules/"
        - "__pycache__/"
        - ".env"
    mode: "two-way-resolved"
```

### 完整配置参考

```yaml
sync:
  session-name:
    alpha: "."                           # 本地路径
    beta: "user@host:/remote/path"       # 远程路径
    mode: "two-way-resolved"             # 同步模式

    ignore:
      vcs: true                          # 忽略 .git/ .svn/ 等 VCS 目录
      paths:                             # 忽略的路径/模式列表
        - "node_modules/"
        - "*.log"
        - ".DS_Store"
        - "Thumbs.db"

    permissions:
      defaultFileMode: 0644              # 新文件默认权限
      defaultDirectoryMode: 0755         # 新目录默认权限

    symlink:
      mode: "ignore"                     # 符号链接处理：ignore / portable

    watch:
      pollingInterval: 10                # 轮询间隔（秒），默认依赖系统事件
```

### 关于忽略规则的重要说明

**`--ignore-vcs` / `vcs: true` 只忽略 `.git/` 目录本身，不会读取 `.gitignore` 规则。**

如果需要忽略 `.gitignore` 中的文件，必须手动将规则添加到 Mutagen 的 `ignore.paths` 中。

可以用脚本从 `.gitignore` 转换：

```bash
# Linux/macOS：从 .gitignore 生成 mutagen ignore 列表
cat .gitignore | grep -v '^#' | grep -v '^$' | sed 's/^/        - "/' | sed 's/$/"/'
```

```powershell
# Windows PowerShell：
Get-Content .gitignore | Where-Object { $_ -notmatch '^\s*#' -and $_ -ne '' } | ForEach-Object { "        - `"$_`"" }
```

将输出粘贴到 `mutagen.yml`（项目级）或 `~/.mutagen.yml`（全局）的 `paths:` 下。

---

## 常用命令速查

### Daemon 管理

```powershell
mutagen daemon start       # 启动后台守护进程
mutagen daemon stop        # 停止守护进程
mutagen daemon run         # 前台运行（调试用）
```

### Sync 会话管理

```powershell
mutagen sync create <alpha> <beta>   # 创建同步会话
mutagen sync list                    # 列出所有会话
mutagen sync list -l                 # 列出详细信息
mutagen sync monitor                 # 实时监控状态
mutagen sync pause <id|name>         # 暂停
mutagen sync resume <id|name>        # 恢复
mutagen sync reset <id|name>         # 重置（重新全量扫描）
mutagen sync flush <id|name>         # 等待当前同步周期完成
mutagen sync terminate <id|name>     # 删除会话
```

### Project 项目管理

```powershell
mutagen project start       # 启动（读取 mutagen.yml）
mutagen project list        # 查看状态
mutagen project pause       # 暂停
mutagen project resume      # 恢复
mutagen project reset       # 重置
mutagen project flush       # 等待同步完成
mutagen project terminate   # 停止并删除
```

### 通用

```powershell
mutagen version             # 查看版本
mutagen legal               # 查看许可证信息
```

---

## 实用技巧

### 1. SSH 密钥认证

避免每次同步都输入密码，配置 SSH 免密登录：

```powershell
# 生成密钥（如果还没有）
ssh-keygen -t ed25519

# 将公钥复制到远程服务器
ssh-copy-id user@192.168.1.100
```

Windows 下如果没有 `ssh-copy-id`，手动操作：

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@192.168.1.100 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### 2. 使用 SSH Config 简化地址

在 `~/.ssh/config`（Windows: `C:\Users\你的用户名\.ssh\config`）中配置：

```
Host dev-server
    HostName 192.168.1.100
    User polarischen
    IdentityFile ~/.ssh/id_ed25519
```

然后 Mutagen 中可以直接用别名：

```yaml
beta: "dev-server:/home/polarischen/myproject"
```

### 3. 排查同步问题

```powershell
# 查看详细状态，包括冲突信息
mutagen sync list -l

# 如果同步卡住，重置会话
mutagen sync reset <name>

# 查看 Daemon 日志（调试）
mutagen daemon run
```

### 4. 与 Docker 容器同步

Mutagen 也支持直接同步到 Docker 容器：

```powershell
mutagen sync create C:\code\myproject docker://container-name/app
```

### 5. 批量忽略常见开发文件

推荐的通用忽略列表：

```yaml
ignore:
  vcs: true
  paths:
    # 依赖目录
    - "node_modules/"
    - "vendor/"
    - ".venv/"
    - "venv/"

    # 构建产物
    - "target/"
    - "dist/"
    - "build/"
    - "out/"
    - ".next/"

    # 缓存
    - "__pycache__/"
    - ".cache/"
    - ".pytest_cache/"
    - ".mypy_cache/"

    # IDE
    - ".idea/"
    - ".vscode/"
    - "*.swp"
    - "*.swo"

    # 系统文件
    - ".DS_Store"
    - "Thumbs.db"

    # 环境/密钥
    - ".env"
    - ".env.*"
    - "*.pem"
    - "*.key"

    # 日志
    - "*.log"
    - "logs/"
```

---

## 常见问题

### Q: 远程服务器需要安装 Mutagen 吗？

**不需要。** Mutagen 会通过 SSH 自动将 Agent 推送到远程服务器并启动。远程只需要有 SSH 访问权限。

### Q: `--ignore-vcs` 为什么没有忽略 .gitignore 中的文件？

`--ignore-vcs`（或 `vcs: true`）**只忽略 VCS 元数据目录**（如 `.git/`、`.svn/`），不会读取 `.gitignore` 规则。需要手动在 `ignore.paths` 中配置忽略列表。

### Q: `mutagen sync create` 和 `mutagen project start` 有什么区别？

| | `sync create` | `project start` |
|---|---|---|
| 配置方式 | 命令行参数 | 读取 `mutagen.yml` 文件 |
| 适合场景 | 临时/简单同步 | 项目级、团队协作 |
| 多目录 | 需要多次执行 | 一个配置文件搞定 |
| 配置可版本管理 | 否 | 是（`mutagen.yml` 可提交到 Git） |

### Q: 同步冲突怎么处理？

- `two-way-safe` 模式：冲突时暂停同步，通过 `mutagen sync list -l` 查看冲突详情，手动解决后 `mutagen sync reset` 重置
- `two-way-resolved` 模式：冲突时 Alpha 端（本地）优先，自动覆盖远程端的冲突文件

### Q: 首次同步很慢怎么办？

首次同步需要传输全部文件，之后都是增量同步。可以：
1. 先用 `rsync` 做一次初始全量传输
2. 再用 Mutagen 接管后续的实时同步
3. 确保 `ignore.paths` 配置正确，排除不需要同步的大目录

### Q: Windows 和 Linux 换行符问题？

Mutagen 默认不做换行符转换。建议在项目中配置 `.gitattributes`：

```
* text=auto eol=lf
```

确保 Git 在所有平台使用统一的 LF 换行符。
