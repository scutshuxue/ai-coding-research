# gstack 深度解析：把 Claude Code 变成你的虚拟工程团队

> **一句话总结**：gstack 是 Y Combinator CEO Garry Tan 开源的 Claude Code 工作流系统，通过 28 个结构化 Skill 把 AI 编码助手从"随机对话"升级为**完整的软件工程团队模拟** —— Think → Plan → Build → Review → Test → Ship → Reflect。

---

## 1. 背景：为什么需要 gstack？

### 1.1 AI 编码的核心痛点

```mermaid
graph LR
    A[你] -->|"帮我做个功能"| B[AI 助手]
    B -->|输出质量随机| C{结果}
    C -->|好| D[能用]
    C -->|差| E[一坨💩]

    style C fill:#ff9,stroke:#333
    style E fill:#f66,stroke:#333
```

直接用 AI 写代码的问题：
- **输出不稳定**：同一个需求，不同 prompt 写法结果天差地别
- **缺乏审查**：AI 写完就完了，没有 Code Review、没有 QA、没有安全审计
- **上下文丢失**：每次对话都是从零开始，前面做的决策后面不知道
- **完整性不足**：AI 倾向于给你"最小可行"方案，而不是"生产级"方案

### 1.2 gstack 的核心洞察

> **真实的软件团队不是一个人在写代码，而是多个角色在协作。**

一个正经的功能从想法到上线，经历的角色：

| 角色 | 职责 | gstack 对应 Skill |
|------|------|------------------|
| 产品经理/CEO | 定方向、砍需求 | `/office-hours` `/plan-ceo-review` |
| 设计师 | UX 审查、设计系统 | `/plan-design-review` `/design-consultation` |
| 技术负责人 | 架构设计、技术选型 | `/plan-eng-review` |
| 开发工程师 | 写代码 | （你自己 + Claude Code） |
| Code Reviewer | 审查代码质量 | `/review` |
| QA 工程师 | 测试、找 bug | `/qa` `/qa-only` |
| 安全工程师 | 安全审计 | `/cso` |
| 发布工程师 | 打版本、发 PR | `/ship` |
| SRE | 部署后监控 | `/canary` `/land-and-deploy` |
| 技术文档 | 更新文档 | `/document-release` |

gstack 让 **一个人 + Claude Code** 扮演以上所有角色。

---

## 2. 架构全景

### 2.1 整体架构

```mermaid
graph TB
    subgraph "用户层"
        U[你在 Terminal 里]
    end

    subgraph "Claude Code"
        CC[Claude Code CLI]
        SK[Skill 系统<br/>28 个 SKILL.md]
    end

    subgraph "gstack 核心"
        PR[Preamble 引擎<br/>上下文注入]
        BIN[CLI 工具集<br/>17 个 bin 工具]
        TPL[模板系统<br/>SKILL.md.tmpl → SKILL.md]
    end

    subgraph "Browser Daemon"
        SRV[Bun HTTP Server<br/>localhost:随机端口]
        PW[Playwright<br/>Chromium 控制]
        SNAP[Snapshot 引擎<br/>可访问性树 + @ref]
    end

    subgraph "持久化"
        CFG["~/.gstack/config.toml"]
        STATE["~/.gstack/browse.json"]
        ANALYTICS["~/.gstack/analytics/"]
        SESSIONS["~/.gstack/sessions/"]
    end

    U -->|/skill-name| CC
    CC -->|加载| SK
    SK -->|执行| PR
    PR -->|调用| BIN
    SK -->|"$B 命令"| SRV
    SRV -->|CDP| PW
    PW -->|操控| SNAP
    BIN --> CFG
    SRV --> STATE
    BIN --> ANALYTICS
    PR --> SESSIONS

    style SK fill:#4af,stroke:#333,color:#000
    style SRV fill:#f94,stroke:#333,color:#000
    style SNAP fill:#9f4,stroke:#333,color:#000
```

### 2.2 Sprint 工作流

```mermaid
graph LR
    subgraph "Think 💭"
        OH["/office-hours<br/>YC 式问诊<br/>挑战假设，3 种方案"]
    end

    subgraph "Plan 📋"
        CEO["/plan-ceo-review<br/>CEO 视角<br/>扩张/缩减/维持/精选"]
        DES["/plan-design-review<br/>设计师审查<br/>UX 打分 0-10"]
        ENG["/plan-eng-review<br/>架构锁定<br/>图表+测试矩阵"]
    end

    subgraph "Build 🔨"
        CODE["Claude Code<br/>写代码"]
    end

    subgraph "Review 🔍"
        REV["/review<br/>Staff Engineer<br/>自动修复+标记"]
        CSO["/cso<br/>安全审计<br/>OWASP+STRIDE"]
    end

    subgraph "Test 🧪"
        QA["/qa<br/>真实浏览器测试<br/>Playwright"]
        BM["/benchmark<br/>性能对比"]
    end

    subgraph "Ship 🚀"
        SHIP["/ship<br/>版本号+CHANGELOG<br/>开 PR"]
        LAND["/land-and-deploy<br/>合并+部署+验证"]
        CAN["/canary<br/>部署后监控"]
    end

    subgraph "Reflect 🪞"
        RET["/retro<br/>周复盘<br/>指标趋势"]
        DOC["/document-release<br/>更新文档"]
    end

    OH --> CEO --> DES --> ENG --> CODE --> REV --> QA --> SHIP --> RET
    REV --> CSO
    QA --> BM
    SHIP --> LAND --> CAN
    SHIP --> DOC

    style OH fill:#e8d5f5,stroke:#333,color:#000
    style CEO fill:#d5e8f5,stroke:#333,color:#000
    style ENG fill:#d5e8f5,stroke:#333,color:#000
    style CODE fill:#f5e8d5,stroke:#333,color:#000
    style REV fill:#f5d5d5,stroke:#333,color:#000
    style QA fill:#d5f5e8,stroke:#333,color:#000
    style SHIP fill:#f5f5d5,stroke:#333,color:#000
    style RET fill:#e0e0e0,stroke:#333,color:#000
```

---

## 3. 核心机制深度解析

### 3.1 Skill 是什么？

每个 Skill 本质上是一个**精心设计的 Markdown 文件**（SKILL.md），定义了：

```yaml
# Skill 文件结构
name: review                    # Skill 名
preamble-tier: 4               # 执行频率 1=总是 4=很少
version: 1.0.0
description: "Pre-landing code review"
allowed-tools:                  # 限制 AI 可用工具
  - Bash
  - Read
  - Edit
  - AskUserQuestion
benefits-from:                  # 上游依赖
  - plan-eng-review
```

**核心理念**：不是给 AI 一个模糊的 prompt，而是给它一个**角色剧本** —— 包含流程、检查清单、输出格式、决策框架。

### 3.2 Preamble（序言引擎）

每个 Skill 执行前都会运行一段标准化的序言，注入关键上下文：

```mermaid
sequenceDiagram
    participant U as 你
    participant CC as Claude Code
    participant PR as Preamble
    participant SK as Skill 逻辑

    U->>CC: /review
    CC->>PR: 加载 SKILL.md

    Note over PR: 1. 检查 gstack 更新
    Note over PR: 2. 会话跟踪（写入 sessions/）
    Note over PR: 3. 检测当前分支
    Note over PR: 4. 检测仓库模式（solo/collaborative）
    Note over PR: 5. 检查遥测状态
    Note over PR: 6. 注入"Boil the Lake"哲学

    PR->>SK: 上下文就绪，执行 Skill
    SK->>U: 结构化输出 + AskUserQuestion
```

**仓库模式**自动检测特别聪明：
- **solo 模式**（你拥有 80%+ 提交）：AI 主动修复问题
- **collaborative 模式**（多人协作）：AI 只标记问题，问你再改

### 3.3 Browser Daemon（浏览器守护进程）

这是 gstack 最硬核的技术组件 —— 一个**持久化的无头 Chromium 浏览器**。

```mermaid
sequenceDiagram
    participant CC as Claude Code
    participant CLI as browse CLI<br/>(编译后的二进制)
    participant SRV as HTTP Server<br/>(Bun, localhost)
    participant CR as Chromium<br/>(Playwright)

    Note over CC,CR: 首次调用 (~3秒启动)
    CC->>CLI: $B goto https://app.com
    CLI->>SRV: POST /cmd {goto, url}
    SRV->>CR: 启动 Chromium + 导航
    CR-->>SRV: 页面加载完成
    SRV-->>CLI: 200 OK + 状态
    CLI-->>CC: 纯文本结果

    Note over CC,CR: 后续调用 (~100-200ms)
    CC->>CLI: $B snapshot -i
    CLI->>SRV: POST /cmd {snapshot, -i}
    SRV->>CR: 获取可访问性树
    CR-->>SRV: ARIA 树数据
    Note over SRV: 分配 @e1, @e2... 引用
    SRV-->>CLI: 带 @ref 的文本树
    CLI-->>CC: @e1 [button] "Submit"<br/>@e2 [textbox] "Email"

    CC->>CLI: $B click @e1
    CLI->>SRV: POST /cmd {click, @e1}
    SRV->>CR: 解析 @e1 → Locator.click()
    CR-->>SRV: 点击完成
    SRV-->>CLI: OK
    CLI-->>CC: 已点击 "Submit"

    Note over CR: 空闲 30 分钟后自动关闭
```

**为什么要持久化？**
- 登录态保持：不用每次重新登录
- Cookie/Tab/存储持久：测试流程连贯
- 亚秒级响应：不用每次启动浏览器

**@ref 系统**是精华：

```
传统方式：click("#app > div:nth-child(3) > button.submit")  ← 脆弱，一改就挂
gstack 方式：click @e5                                        ← 基于可访问性树，框架无关
```

### 3.4 Completeness 原则（"煮沸湖水"）

gstack 最具争议也最有价值的理念：

```mermaid
graph TD
    A{任务规模？} -->|Lake 湖| B["直接煮沸！<br/>完整实现<br/>100% 测试覆盖<br/>所有边界情况"]
    A -->|Ocean 海| C["标记为海洋<br/>分解为多个湖<br/>逐个煮沸"]
    A -->|Puddle 水坑| D["秒杀"]

    B --> E["AI 压缩比参考"]
    E --> F["样板代码 100x<br/>人类2天 → AI 15分钟"]
    E --> G["测试编写 50x<br/>人类1天 → AI 15分钟"]
    E --> H["功能实现 30x<br/>人类1周 → AI 30分钟"]
    E --> I["架构设计 5x<br/>人类2天 → AI 4小时"]

    style B fill:#4f4,stroke:#333,color:#000
    style C fill:#ff4,stroke:#333,color:#000
    style D fill:#4ff,stroke:#333,color:#000
```

**核心逻辑**：当 AI 让边际成本趋近于零时，"做完整"比"做最小"更合理。多写 70 行代码只多花几秒钟，但能省你以后几小时的修补时间。

---

## 4. 关键 Skill 详解

### 4.1 /office-hours — YC 式问诊

**模拟场景**：你去 YC 的 Office Hours，Partner 挑战你的每一个假设。

```
你: 我想做一个日报 App
AI:
  - 谁是目标用户？你自己还是团队？
  - 为什么不用现有方案（Notion、Slack recap）？
  - 核心价值假设是什么？

  3 种方案：
  A) 最小 MVP — 纯命令行日报生成（工作量：15min AI / 2h 人类）
  B) 中等方案 — Web App + AI 摘要（工作量：30min AI / 1周 人类）
  C) 完整方案 — 多源聚合 + 团队面板（工作量：2h AI / 1月 人类）

  RECOMMENDATION: 选 B，因为 [理由]
  Completeness: 7/10
```

### 4.2 /review — Staff Engineer 级代码审查

```mermaid
flowchart TD
    A[读取 git diff base..HEAD] --> B{扫描问题}
    B --> C[SQL 注入检查]
    B --> D[LLM 信任边界检查]
    B --> E[条件副作用检查]
    B --> F[完整性缺口检查]

    C --> G{可自动修复？}
    D --> G
    E --> G
    F --> G

    G -->|是| H["AUTO-FIXED ✅<br/>直接改代码+提交"]
    G -->|否| I["ASK ❓<br/>展示问题+建议<br/>等你确认"]
    G -->|严重| J["BLOCK 🚫<br/>不改这个不能 ship"]
```

### 4.3 /qa — 真实浏览器 QA

不是模拟测试，是**真的打开浏览器点点点**：

```bash
$B goto https://staging.myapp.com/login
$B snapshot -i                    # 看到 @e1 用户名, @e2 密码, @e3 登录按钮
$B fill @e1 "test@example.com"
$B fill @e2 "password123"
$B click @e3
$B snapshot -D                    # diff 模式：看登录后变了什么
$B screenshot /tmp/after-login.png
```

发现 bug → 修代码 → 原子提交 → 重跑测试 → 验证修复。循环直到全绿。

### 4.4 /cso — 首席安全官审计

按 OWASP Top 10 + STRIDE 威胁模型逐项审查：

- 注入攻击（SQL、XSS、命令注入）
- 认证/授权漏洞
- 敏感数据暴露
- 安全配置错误
- 已知漏洞依赖

### 4.5 安全守卫组合

```mermaid
graph LR
    CAR["/careful<br/>危险命令警告"] --> |"rm -rf, DROP TABLE<br/>force push"| WARN[⚠️ 警告并确认]
    FRZ["/freeze<br/>编辑范围锁定"] --> |"只允许改 src/feature/"| LOCK[🔒 锁定目录]
    GRD["/guard<br/>= careful + freeze"] --> WARN
    GRD --> LOCK
    UFZ["/unfreeze<br/>解除锁定"] --> |"解锁"| FREE[🔓 自由编辑]
```

---

## 5. 使用场景与最佳实践

### 5.1 适合的场景

| 场景 | 推荐流程 | 预期效果 |
|------|----------|----------|
| **独立开发者做 MVP** | `/office-hours` → `/plan-eng-review` → 写代码 → `/review` → `/ship` | 一天内从想法到 PR |
| **小团队没有专职 QA** | 写完代码 → `/review` → `/qa https://staging...` → `/ship` | 自动化 QA 流程 |
| **CEO 亲自写代码** | `/office-hours` → `/plan-ceo-review` → `/plan-eng-review` → 全流程 | 模拟完整团队 |
| **安全审计** | `/cso` 单独跑 | OWASP + STRIDE 审计报告 |
| **遗留代码排查** | `/investigate` | 系统化根因分析 |
| **周报/复盘** | `/retro` | 自动生成指标趋势 |

### 5.2 最佳实践

```mermaid
graph TB
    subgraph "✅ 推荐做法"
        A1["按顺序走流程<br/>Think → Plan → Build → Review → Ship"]
        A2["用 /freeze 限制编辑范围<br/>防止 AI 乱改"]
        A3["每个 Skill 结束后检查输出<br/>再进入下一步"]
        A4["用 /qa 做真实浏览器测试<br/>不要只跑单元测试"]
        A5["用 /careful 保护危险操作<br/>特别是生产环境"]
    end

    subgraph "❌ 避免做法"
        B1["跳过 Plan 直接写代码<br/>→ 方向错了全白做"]
        B2["跳过 /review 直接 ship<br/>→ 低质量代码上线"]
        B3["一次让 AI 做太大的功能<br/>→ 拆成多个湖分别煮"]
        B4["盲信 LOC 指标<br/>→ 代码量 ≠ 价值"]
        B5["不看 AI 修改直接确认<br/>→ 你才是最终 Reviewer"]
    end

    style A1 fill:#d5f5d5,stroke:#333
    style A2 fill:#d5f5d5,stroke:#333
    style A3 fill:#d5f5d5,stroke:#333
    style A4 fill:#d5f5d5,stroke:#333
    style A5 fill:#d5f5d5,stroke:#333
    style B1 fill:#f5d5d5,stroke:#333
    style B2 fill:#f5d5d5,stroke:#333
    style B3 fill:#f5d5d5,stroke:#333
    style B4 fill:#f5d5d5,stroke:#333
    style B5 fill:#f5d5d5,stroke:#333
```

### 5.3 快速上手路径

**30 秒安装**：
```bash
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup
```

**第一次使用（5 分钟上手）**：
```bash
# 1. 打开你的项目
cd your-project

# 2. 在 Claude Code 中试试
/office-hours    # 先用这个，把你的想法说出来，让 AI 挑战你
/review          # 写完代码后用这个审查
/ship            # 审查通过后用这个发 PR
```

**进阶使用**：
```bash
/autoplan        # 一键跑完 CEO → 设计 → 工程 全部 Plan 审查
/qa https://localhost:3000   # 真实浏览器测试
/cso             # 安全审计
/guard           # 开启安全护栏（careful + freeze）
```

---

## 6. 技术栈与依赖

```mermaid
graph TB
    subgraph "运行时"
        BUN[Bun<br/>TypeScript 运行时]
        PW[Playwright<br/>浏览器自动化]
        CR[Chromium<br/>无头浏览器]
    end

    subgraph "宿主"
        CC[Claude Code CLI<br/>Anthropic]
        CDX[Codex CLI<br/>OpenAI]
        GEM[Gemini CLI<br/>Google]
    end

    subgraph "数据"
        TOML["config.toml<br/>用户配置"]
        JSON["browse.json<br/>浏览器状态"]
        JSONL["*.jsonl<br/>分析数据"]
        SB["Supabase<br/>可选遥测"]
    end

    CC --> BUN
    CDX --> BUN
    GEM --> BUN
    BUN --> PW --> CR
    BUN --> TOML
    BUN --> JSON
    BUN --> JSONL
    BUN -.->|可选| SB
```

**关键依赖**：
- **Bun**（必须）— TypeScript 编译+运行时
- **Playwright + Chromium**（随 setup 安装）— 浏览器测试
- **Claude Code**（主要）/ Codex / Gemini CLI — AI 引擎

---

## 7. 社区评价与争议

### 7.1 正面

- **46,000+ Star**，48 小时内破万
- "将 SDLC 流程注入 AI 编码" 的概念被认为有创新意义
- 有 CTO 称之为 "God Mode"
- 浏览器自动化 + 真实 QA 的集成确实解决了实际问题

### 7.2 争议

- **LOC 指标争议**："60 天 60 万行" —— 批评者认为代码行数是负债不是资产
- **过度工程化质疑**：有人认为这就是 "一堆结构化的 prompts"
- **名人效应**：如果不是 YC CEO 发的，关注度会低很多
- **健康问题**：Garry Tan 自称每晚只睡 4 小时来写代码，社区表示担忧

### 7.3 客观评价

```
gstack 的真正价值不在于让你写更多代码，
而在于给 AI 编码加上了"工程纪律" ——
Code Review、QA、安全审计、发布流程，
这些东西即使在 AI 时代也不应该被跳过。
```

---

## 8. 与类似工具对比

| 特性 | gstack | 裸 Claude Code | Cursor | Copilot |
|------|--------|---------------|--------|---------|
| 结构化工作流 | ✅ 28 个 Skill | ❌ 自由对话 | ❌ | ❌ |
| 真实浏览器测试 | ✅ Playwright | ❌ | ❌ | ❌ |
| 自动 Code Review | ✅ /review | ❌ | ❌ | ❌ |
| 安全审计 | ✅ /cso | ❌ | ❌ | ❌ |
| 角色模拟 | ✅ CEO/设计/QA/SRE | ❌ | ❌ | ❌ |
| 上下文链式传递 | ✅ | ❌ | 部分 | ❌ |
| 开源免费 | ✅ MIT | — | ❌ 付费 | ❌ 付费 |

---

## 9. 谈资速查（帮你吹的要点）

1. **"这是 YC CEO 的工程工作流"** —— Garry Tan 亲自用这套系统，60 天产出 60 万行代码
2. **"不是 AI 写代码，是 AI 模拟整个工程团队"** —— Think/Plan/Build/Review/Test/Ship/Reflect 完整 SDLC
3. **"核心创新是给 AI 加工程纪律"** —— 不跳过 Code Review、不跳过 QA、不跳过安全审计
4. **"真的会打开浏览器测试"** —— 不是 mock，是 Playwright 控制真实 Chromium，亚秒级响应
5. **"Boil the Lake 哲学"** —— 当 AI 让边际成本趋近于零，做完整比做最小更合理
6. **"一个人就是一支团队"** —— Solo founder 的终极武器，适合早期创业快速迭代
7. **"跨 AI 平台"** —— 不绑定 Claude，也支持 Codex 和 Gemini CLI
8. **"争议很大"** —— LOC 指标被业界怼，但工作流结构化的理念被广泛认可

---

## 10. 项目文件结构速览

```
gstack/
├── office-hours/        # Think: YC 式问诊
├── plan-ceo-review/     # Plan: CEO 视角审查
├── plan-eng-review/     # Plan: 工程架构锁定
├── plan-design-review/  # Plan: 设计审查
├── design-consultation/ # Plan: 从零建设计系统
├── review/              # Review: Staff Engineer 代码审查
├── cso/                 # Review: 安全审计
├── qa/                  # Test: 浏览器 QA（修复模式）
├── qa-only/             # Test: 浏览器 QA（只报告）
├── benchmark/           # Test: 性能对比
├── investigate/         # Debug: 根因分析
├── ship/                # Ship: 发版+PR
├── land-and-deploy/     # Ship: 合并+部署+监控
├── canary/              # Ship: 部署后金丝雀监控
├── retro/               # Reflect: 周复盘
├── document-release/    # Reflect: 更新文档
├── autoplan/            # 自动化: 一键全流程 Plan
├── careful/             # 安全: 危险命令警告
├── freeze/              # 安全: 编辑范围锁定
├── guard/               # 安全: careful + freeze
├── unfreeze/            # 安全: 解除锁定
├── codex/               # 跨模型: Codex 二次确认
├── gstack-upgrade/      # 维护: 自动升级
├── browse/              # 核心: 浏览器守护进程
│   ├── src/             #   TypeScript 源码
│   └── dist/            #   编译后二进制 (~58MB)
├── bin/                 # CLI 工具集 (17 个)
├── scripts/             # 构建工具
├── test/                # 测试套件 (3 层)
├── setup                # 安装脚本
├── README.md            # 愿景文档 (17K 字)
├── ARCHITECTURE.md      # 架构文档 (21K 字)
├── SKILL.md             # 主 Skill 文档 (29K 字)
└── ETHOS.md             # 建造者哲学
```
