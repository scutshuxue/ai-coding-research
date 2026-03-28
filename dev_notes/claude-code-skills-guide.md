# Claude Code Skills 实践指南

> 基于 Thariq (Anthropic) 文章 *"Lessons from Building Claude Code: How We Use Skills"* (2026-03-17) 整理

## 目录

- [1. Skills 是什么](#1-skills-是什么)
- [2. 核心原理：Skills 的运行机制](#2-核心原理skills-的运行机制)
- [3. 九大 Skills 分类体系](#3-九大-skills-分类体系)
- [4. 各类型详解与示例](#4-各类型详解与示例)
- [5. Skills 最佳实践](#5-skills-最佳实践)
- [6. Skill 开发流程](#6-skill-开发流程)
- [7. 文件系统结构设计](#7-文件系统结构设计)

---

## 1. Skills 是什么

Skills 是 Claude Code 最核心的扩展机制之一。它**不是简单的 Markdown 提示文件**，而是一个可以包含脚本、资产文件、数据和配置的**文件夹**。Claude 能够发现、探索和操作这些资源，从而实现复杂的工程自动化。

**关键认知转变：**

| 初级理解 | 正确理解 |
|----------|----------|
| Skill = 一个 Markdown 文件 | Skill = 一个完整的工具包（文件夹） |
| 写好提示词就行 | 需要设计触发条件、脚本、数据结构 |
| 告诉 Claude 怎么做 | 给 Claude 信息和灵活性，让它自己决定怎么做 |
| 重复常识性知识 | 聚焦 Claude 不知道的"陷阱"和特殊逻辑 |

---

## 2. 核心原理：Skills 的运行机制

### 2.1 Skills 在 Claude Code 中的位置

```mermaid
graph TB
    subgraph "Claude Code 运行时"
        A[用户输入] --> B{Skill 触发判断}
        B -->|description 匹配| C[加载 Skill 内容]
        B -->|不匹配| D[常规响应]
        C --> E[读取 Skill 文件夹]
        E --> F[Markdown 指令]
        E --> G[脚本/工具]
        E --> H[配置/数据]
        E --> I[参考资料]
        F --> J[Claude 执行任务]
        G --> J
        H --> J
        I --> J
        J --> K[输出结果]
    end

    style B fill:#f9a825,stroke:#f57f17
    style C fill:#66bb6a,stroke:#388e3c
    style J fill:#42a5f5,stroke:#1976d2
```

### 2.2 Skill 触发流程

```mermaid
sequenceDiagram
    participant U as 用户
    participant CC as Claude Code
    participant S as Skill 系统
    participant T as 工具层

    U->>CC: 发送请求/指令
    CC->>S: 检查 description 字段匹配
    alt 存在匹配 Skill
        S->>CC: 返回 Skill 内容
        CC->>CC: 解析指令 + 上下文
        CC->>T: 调用工具（Bash/Read/Edit/MCP...）
        T->>CC: 返回执行结果
        CC->>U: 输出最终结果
    else 无匹配 Skill
        CC->>U: 使用默认能力响应
    end
```

### 2.3 核心设计原则

```mermaid
mindmap
  root((Skill 设计原则))
    信息而非指令
      提供 Claude 不知道的信息
      避免重述常识
      聚焦 Gotchas 和陷阱
    灵活而非死板
      给信息不给死板步骤
      让 Claude 自适应
      避免过度约束
    渐进式发现
      文件夹分层组织
      按需读取深层内容
      脚本和资产分离
    持久化记忆
      JSON/日志文件存储
      跨会话状态保持
      append-only 追加写入
```

---

## 3. 九大 Skills 分类体系

```mermaid
graph LR
    subgraph "开发阶段"
        A[5. 代码脚手架<br/>Code Scaffolding]
        B[1. 库/API 参考<br/>Library & API Ref]
        C[6. 代码质量<br/>Code Quality]
    end

    subgraph "测试与验证"
        D[2. 产品验证<br/>Product Verification]
    end

    subgraph "数据与分析"
        E[3. 数据获取<br/>Data Fetching]
    end

    subgraph "运维与部署"
        F[7. CI/CD 部署<br/>CI/CD & Deploy]
        G[8. 运维手册<br/>Runbooks]
        H[9. 基础设施<br/>Infra Operations]
    end

    subgraph "团队协作"
        I[4. 业务流程<br/>Business Process]
    end

    A --> D
    B --> C
    C --> D
    D --> F
    F --> G
    G --> H
    I --> E

    style A fill:#e3f2fd,stroke:#1565c0
    style B fill:#e3f2fd,stroke:#1565c0
    style C fill:#e3f2fd,stroke:#1565c0
    style D fill:#fff3e0,stroke:#e65100
    style E fill:#f3e5f5,stroke:#6a1b9a
    style F fill:#e8f5e9,stroke:#2e7d32
    style G fill:#e8f5e9,stroke:#2e7d32
    style H fill:#e8f5e9,stroke:#2e7d32
    style I fill:#fce4ec,stroke:#b71c1c
```

---

## 4. 各类型详解与示例

### 4.1 库/API 参考 (Library & API Reference)

**用途：** 说明库、CLI 或 SDK 的正确用法，包含参考代码片段和常见陷阱。

**典型场景：**
- 内部 billing-lib 的边界案例文档
- internal-platform-cli 子命令指导
- 前端设计系统改进指南

**原理：** Claude 对公开库有较好的知识，但对内部库、私有 API 完全不了解。此类 Skill 填补了这一知识空白。

```
my-lib-skill/
├── skill.md          # 主要使用说明 + 陷阱
├── examples/
│   ├── basic.ts      # 基础用法
│   └── advanced.ts   # 高级模式
└── gotchas.md        # 常见错误和修复
```

---

### 4.2 产品验证 (Product Verification)

**用途：** 用外部工具（Playwright、tmux）测试和验证代码正确性。

**典型场景：**
- `signup-flow-driver` — 无头浏览器测试注册流程
- `checkout-verifier` — Stripe 集成测试
- `tmux-cli-driver` — 交互式 CLI 测试

**原理：** Claude 默认无法"看到"运行中的应用。通过 Playwright 等工具，Skill 让 Claude 获得了对运行时行为的感知能力。

---

### 4.3 数据获取与分析 (Data Fetching & Analysis)

**用途：** 连接数据和监控基础设施，配合凭证和工作流模式。

**典型场景：**
- `funnel-query` — 用户转化漏斗指标
- `cohort-compare` — 留存分析
- Grafana 数据源查询

**原理：** 将数据查询凭证、连接方式、查询模板封装在 Skill 中，Claude 按需组合查询，而非硬编码每种分析场景。

---

### 4.4 业务流程与团队自动化 (Business Process & Team Automation)

**用途：** 自动化重复性工作流，存储结果以保持一致性。

**典型场景：**
- `standup-post` — 聚合站会信息
- 工单创建（含 schema 校验）
- `weekly-recap` — 周报生成

---

### 4.5 代码脚手架与模板 (Code Scaffolding & Templates)

**用途：** 基于自然语言需求生成框架特定的样板代码。

**典型场景：**
- 新框架工作流脚手架
- 数据库迁移文件模板
- 预配置应用初始化

---

### 4.6 代码质量与审查 (Code Quality & Review)

**用途：** 执行组织标准、促进代码审查。

**典型场景：**
- `adversarial-review` — 对抗式审查 + 迭代修复
- 代码风格强制执行
- 测试实践指南

---

### 4.7 CI/CD 与部署 (CI/CD & Deployment)

**用途：** 管理代码推送、拉取和部署流程。

**典型场景：**
- `babysit-pr` — 监控 PR 并解决冲突
- `deploy-service` — 渐进式发布
- `cherry-pick-prod` — 隔离变更的生产热修复

---

### 4.8 运维手册 (Runbooks)

**用途：** 根据症状产出结构化排查报告，使用多种工具组合。

**典型场景：**
- `service-debugging` — 症状映射排查
- `oncall-runner` — 告警分诊
- `log-correlator` — 请求链路追踪

---

### 4.9 基础设施运维 (Infrastructure Operations)

**用途：** 执行维护任务，对破坏性操作设置安全护栏。

**典型场景：**
- `resource-orphans` — 孤立资源清理
- `dependency-management` — 依赖审批
- `cost-investigation` — 成本分析

---

## 5. Skills 最佳实践

### 5.1 实践总览

```mermaid
graph TD
    A[Skill 开发最佳实践] --> B[内容策略]
    A --> C[结构设计]
    A --> D[运行时策略]

    B --> B1["避免陈述显而易见的事<br/>❌ 'Use try-catch for errors'<br/>✅ '我们的 API 在 429 时返回<br/>非标准 retry-after 格式'"]
    B --> B2["构建 Gotchas 章节<br/>（最高价值内容）"]
    B --> B3["提供灵活性<br/>给信息，不给死板步骤"]

    C --> C1["利用文件系统结构<br/>脚本/引用/示例分层"]
    C --> C2["优化 description 字段<br/>写触发条件，不写摘要"]
    C --> C3["嵌入可复用脚本<br/>让 Claude 聚焦组合"]

    D --> D1["规划配置需求<br/>config.json + AskUserQuestion"]
    D --> D2["实现记忆系统<br/>append-only 日志/JSON"]
    D --> D3["使用按需 Hooks<br/>安全护栏阻止危险命令"]

    style B fill:#e3f2fd
    style C fill:#e8f5e9
    style D fill:#fff3e0
```

### 5.2 Description 字段：触发条件而非摘要

这是决定 Skill 是否被调用的关键字段。

```markdown
# ❌ 错误写法（摘要式）
description: 这个 Skill 帮助处理数据库迁移

# ✅ 正确写法（触发条件式）
description: >
  Use when creating, modifying, or rolling back database migrations.
  Trigger on mentions of "migration", "schema change", "ALTER TABLE",
  or when editing files in db/migrations/.
```

**原理：** Claude 会将用户输入与 description 进行语义匹配。描述越像触发条件，匹配越精准。

### 5.3 Gotchas 章节：最高价值内容

Gotchas 文档记录的是 Claude 在使用你的 Skill 时**常见的失败点**。这是将 Claude 推出其"默认思维模式"的关键。

```markdown
## Gotchas

### ❌ 不要直接调用 billing.charge()
billing.charge() 在金额 < $0.50 时会静默失败。
必须先调用 billing.validate_amount() 检查最小值。

### ❌ 日期字段不是 ISO 8601
我们的 API 返回 "MM/DD/YYYY" 格式（历史遗留），
不是 Claude 默认假设的 ISO 8601。解析前必须转换。
```

### 5.4 记忆持久化策略

```mermaid
graph LR
    subgraph "会话 1"
        A1[执行任务] --> A2[追加写入日志]
    end
    subgraph "存储层"
        A2 --> S[(append-only<br/>JSON/日志文件)]
    end
    subgraph "会话 2"
        S --> B1[读取历史状态]
        B1 --> B2[继续任务]
        B2 --> B3[追加新数据]
        B3 --> S
    end

    style S fill:#fff9c4,stroke:#f9a825
```

**关键点：**
- 使用 **append-only** 模式（追加写入），避免覆盖历史数据
- 存储在 **稳定目录** 中（如 `.claude/` 下），确保跨会话可访问
- 使用 JSON 格式便于结构化读取

### 5.5 安全 Hooks：按需护栏

```mermaid
flowchart LR
    A[Claude 准备执行命令] --> B{Hook 检查}
    B -->|安全| C[正常执行]
    B -->|危险命令| D[阻止并警告]

    D --> E["阻止列表示例：<br/>rm -rf<br/>DROP TABLE<br/>git push --force<br/>kubectl delete"]

    style D fill:#ef5350,stroke:#b71c1c,color:#fff
    style C fill:#66bb6a,stroke:#388e3c
```

Hooks 是会话级别的安全机制，在 Skill 中定义后，自动拦截危险操作。

---

## 6. Skill 开发流程

```mermaid
flowchart TD
    A[识别重复性任务] --> B[确定 Skill 类型<br/>参考九大分类]
    B --> C[设计文件夹结构]
    C --> D[编写 description<br/>触发条件式]
    D --> E[编写核心逻辑<br/>Markdown + 脚本]
    E --> F[构建 Gotchas 章节<br/>记录失败点]
    F --> G[添加配置与数据模板]
    G --> H[测试触发与执行]
    H --> I{效果满意？}
    I -->|否| J[分析失败原因]
    J --> K{问题在哪？}
    K -->|触发不准| D
    K -->|执行不对| E
    K -->|缺少信息| F
    I -->|是| L[发布 Skill]

    style A fill:#e3f2fd,stroke:#1565c0
    style L fill:#c8e6c9,stroke:#2e7d32
    style J fill:#fff3e0,stroke:#e65100
```

---

## 7. 文件系统结构设计

一个成熟 Skill 的典型文件结构：

```
my-skill/
├── skill.md              # 主指令文件（入口）
├── config.json           # 配置参数
├── gotchas.md            # 陷阱与常见错误
├── scripts/
│   ├── setup.sh          # 环境准备脚本
│   ├── validate.py       # 验证脚本
│   └── helpers.ts        # 可复用工具函数
├── examples/
│   ├── basic-usage.md    # 基础示例
│   └── advanced-usage.md # 高级示例
├── references/
│   └── api-spec.yaml     # API 规范参考
└── data/
    └── templates/        # 模板文件
        └── default.json
```

```mermaid
graph TD
    A["skill.md<br/>(入口 + 核心指令)"] --> B["config.json<br/>(参数配置)"]
    A --> C["gotchas.md<br/>(陷阱文档)"]
    A --> D["scripts/<br/>(脚本工具)"]
    A --> E["examples/<br/>(使用示例)"]
    A --> F["references/<br/>(参考资料)"]
    A --> G["data/<br/>(模板和数据)"]

    D --> D1[setup.sh]
    D --> D2[validate.py]
    D --> D3[helpers.ts]

    style A fill:#42a5f5,stroke:#1565c0,color:#fff
    style C fill:#ef5350,stroke:#b71c1c,color:#fff
    style D fill:#66bb6a,stroke:#2e7d32
```

**渐进式发现原理：** Claude 首先读取 `skill.md` 入口文件，根据任务需要再深入读取子目录中的脚本、示例和参考资料。这种分层设计避免了一次性加载过多内容，同时确保所有资源都可被发现。

---

## 参考来源

- 原文：*Lessons from Building Claude Code: How We Use Skills* — Thariq (@trq212), 2026-03-17
- Claude Code 官方文档：[claude.ai/code](https://claude.ai/code)
