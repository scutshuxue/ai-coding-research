# AI-SDD 工作区项目分析报告

> 分析日期：2026-03-09
> 分析范围：AI-SDD-template 与 ai-plugin-market 两个项目的完整对比

---

## 目录

1. [概述：两个项目分别是干什么的](#1-概述两个项目分别是干什么的)
2. [AI-SDD-template 详解](#2-ai-sdd-template-详解)
3. [ai-plugin-market 详解](#3-ai-plugin-market-详解)
4. [实现层面的深度差异对比](#4-实现层面的深度差异对比)
5. [组件级逐项对比](#5-组件级逐项对比)
6. [架构设计哲学差异](#6-架构设计哲学差异)
7. [总结与关系图](#7-总结与关系图)

---

## 1. 概述：两个项目分别是干什么的

### 一句话定义

| 项目 | 定位 | 类比 |
|------|------|------|
| **AI-SDD-template** | SDD 框架的**源码仓库 + 集成工具** | 相当于一个"操作系统安装镜像" |
| **ai-plugin-market** | SDD 框架的**插件分发渠道** | 相当于一个"应用商店" |

### 用大白话解释

**AI-SDD-template** 是整个 SDD（Specification-Driven Development，规范驱动开发）框架的"老家"。它包含了框架的所有源文件、初始化脚本、知识库内容、设计文档和示例规范。当你想把 SDD 框架集成到一个新项目时，你需要克隆这个模板仓库，然后运行 `AI-SDD-init.py` 脚本把框架文件复制到目标项目里。

**ai-plugin-market** 是一个 Claude Code 插件市场。它把同样的 SDD 框架打包成了一个名为 `web3sdd` 的 Claude Code 插件。用户可以通过 `/plugin install web3sdd@ai-plugin-market` 一键安装，不需要手动克隆和运行脚本。

**核心关系**：两者包含**几乎完全相同的核心组件**（agents、commands、skills），但分发和安装方式完全不同。

---

## 2. AI-SDD-template 详解

### 2.1 项目定位

AI-SDD-template 是一个**框架模板仓库**，它的核心使命是：

1. **定义 SDD 开发流程** — 从需求规范到代码实现的完整工作流
2. **提供三层知识库系统** — 企业级（L0）、项目级（L1）、仓库级（L2）的知识管理
3. **通过脚本集成到目标项目** — `AI-SDD-init.py` 负责将框架文件复制到用户项目

### 2.2 完整目录结构

```
AI-SDD-template/
├── AI-SDD-init.py                    # [核心] 初始化脚本，将框架集成到目标项目
├── CLAUDE.md                         # Claude Code 工作指引和项目约束
├── README.md                         # 项目说明
├── AI-SDD-INTEGRATION.md             # 集成指南（详细）
├── SDD-Speckit-GUIDE.md              # 快速开始指南
├── 05-knowledge-spaces.md            # 知识库结构说明
│
├── .claude/                          # === Claude Code 框架核心 ===
│   ├── agents/                       #   12 个专业化 Agent
│   │   ├── api-analyzer.md
│   │   ├── code-architect.md
│   │   ├── code-documenter.md
│   │   ├── code-explorer.md
│   │   ├── code-quality-scorer.md
│   │   ├── code-structure-analyzer.md
│   │   ├── data-flow-analyzer.md
│   │   ├── dependency-analyzer.md
│   │   ├── knowledge-loader.md
│   │   ├── markdown-generator-zh.md
│   │   ├── request-flow-analyzer.md
│   │   └── work-summarizer.md
│   ├── commands/                     #   14 个命令（含 simplesdd 子目录）
│   │   ├── speckit.specify.md
│   │   ├── speckit.plan.md
│   │   ├── speckit.implement.md
│   │   ├── speckit.tasks.md
│   │   ├── speckit.summary.md
│   │   ├── speckit.clarify.md
│   │   ├── speckit.checklist.md
│   │   ├── speckit.analyze.md
│   │   ├── speckit.constitution.md
│   │   ├── speckit.knowledge.md
│   │   ├── speckit.taskstoissues.md
│   │   ├── full-analysis.md
│   │   ├── git-commit.md
│   │   ├── copy-specify.md
│   │   └── simplesdd/
│   │       └── feature-dev.md
│   └── skills/                       #   11 个技能模块
│       ├── code-review/
│       ├── spec-knowledge-loader/
│       ├── spec-summary/
│       ├── kb-retriever/
│       ├── kb-index-generator/
│       ├── simplesdd-init/
│       ├── claudemd-init/
│       ├── spec-brainstorm/
│       ├── wiki-write/
│       ├── wiki-update/
│       └── wiki-init/
│
├── .specify/                         # === 配置、脚本和模板 ===
│   ├── knowledge-config.yaml         #   [核心] 知识库加载配置
│   ├── knowledge-config.json         #   JSON 格式的配置
│   ├── memory/
│   │   └── constitution.md           #   [核心] 项目章程（10大原则）
│   ├── scripts/                      #   三种语言的辅助脚本
│   │   ├── bash/       (7 个 .sh)
│   │   ├── python/     (8 个 .py，含 create-simple-feature.py)
│   │   └── powershell/ (7 个 .ps1)
│   └── templates/                    #   规范和知识库提示模板
│       ├── spec-template.md
│       ├── plan-template.md
│       ├── tasks-template.md
│       ├── checklist-template.md
│       ├── agent-file-template.md
│       └── knowledge-prompts/  (9 个提示模板)
│
├── .knowledge/                       # === 三层知识库 ===
│   ├── context.md                    #   仓库级上下文
│   └── upstream/
│       ├── L0-enterprise/            #   企业级强制约束（30+ 文件）
│       │   ├── constitution/         #     架构原则、安全基线、合规要求
│       │   ├── standards/            #     编码规范（Java/Python/Vue/React）
│       │   ├── technology-radar/     #     技术采纳状态
│       │   ├── ai-coding/            #     AI 编码策略和红线
│       │   ├── governance/           #     发布和审查流程
│       │   └── speckit-config/       #     SpecKit 更新配置
│       └── L1-project/               #   项目级知识
│           ├── business/             #     领域模型（custody/lending/tokenization等）
│           └── architecture/         #     技术栈、服务目录
│
├── docs/                             # === 设计文档和指南 ===
│   ├── AI-SDD-guide.md
│   ├── ai-sdd-example.md
│   ├── integration-guide.md
│   ├── code-review/
│   ├── designs/
│   └── wiki-writer/
│
├── specs/                            # === 功能规范示例 ===
│   └── 001-speckit-update-redesign/
│       ├── spec.md
│       ├── plan.md
│       ├── tasks.md
│       ├── research.md
│       ├── data-model.md
│       ├── quickstart.md
│       ├── contracts/
│       └── checklists/
│
└── dev/                              # === 开发中的插件原型 ===
    └── marketplace/plugins/feature-dev/
        ├── plugin.json
        ├── agents/   (6 个，含中英文版本)
        └── commands/
```

### 2.3 核心组件说明

#### Agents（12 个专业化 Agent）

| Agent | 职责 | 核心能力 |
|-------|------|---------|
| **code-explorer** | 代码库探索分析 | 追踪执行路径、映射架构层、记录依赖 |
| **code-architect** | 软件架构设计 | L0/L1 约束验证、技术雷达检查、实现蓝图 |
| **work-summarizer** | 工作总结文档 | 9 维度合规评分（TDD/架构/安全等）、Mermaid 图表 |
| **code-quality-scorer** | 代码质量评估 | 基于目录结构的模块化评分（0-100 分） |
| **code-documenter** | 技术文档生成 | README.md 生成、C4 模型文档 |
| **api-analyzer** | API 文档分析 | REST/GraphQL/gRPC/WebSocket/RMB 分析 |
| **dependency-analyzer** | 依赖关系映射 | 循环依赖检测、RMB 消息队列分析 |
| **data-flow-analyzer** | 数据流分析 | 数据转换、持久化、验证机制分析 |
| **knowledge-loader** | 知识库加载 | 按阶段加载 L0/L1/L2 约束、CRITICAL 检查 |
| **code-structure-analyzer** | 代码结构分析 | MVC/分层/六边形/DDD 等架构模式识别 |
| **request-flow-analyzer** | 请求流分析 | 入口点、路由、中间件、认证流程映射 |
| **markdown-generator-zh** | CLAUDE.md 生成 | 整合分析结果生成项目配置文件 |

#### Commands（SDD 流程命令）

**完整 SDD 流程**：
```
/speckit.specify    自然语言 → 功能规范（spec.md）
    ↓
/speckit.clarify    识别歧义、澄清需求（可选）
    ↓
/speckit.plan       生成实施计划（plan.md + data-model.md + contracts/）
    ↓
/speckit.tasks      生成任务列表（tasks.md）
    ↓
/speckit.checklist  生成检查清单（可选）
    ↓
/speckit.implement  按任务执行实现（TDD + 代码审查）
    ↓
/speckit.summary    生成总结文档（summary.md）
    ↓
/git-commit         智能提交
```

**轻量流程**：
```
/simplesdd:feature-dev  一步完成 7 阶段（发现→探索→澄清→设计→实现→审查→总结）
```

#### Skills（11 个技能模块）

| Skill | 用途 |
|-------|------|
| **spec-knowledge-loader** | 为各阶段加载知识库约束和检查项 |
| **code-review** | 并行启动 3-6 个 subagent 进行代码审查 |
| **spec-summary** | 委托 work-summarizer 生成总结 |
| **kb-retriever** | 知识库检索（分层导航 + 渐进式检索） |
| **kb-index-generator** | 自动生成知识库索引 |
| **wiki-write/wiki-update/wiki-init** | Wiki 文档管理 |
| **simplesdd-init** | SimpleSDD 初始化 |
| **claudemd-init** | CLAUDE.md 初始化 |
| **spec-brainstorm** | 规范头脑风暴 |

### 2.4 独有内容（ai-plugin-market 没有的）

1. **`AI-SDD-init.py`** — 核心初始化脚本，支持全量/增量初始化，自动挂载 L0 知识库
2. **`.knowledge/` 目录** — 完整的三层知识库内容（L0 企业级 30+ 文件，L1 项目级业务领域知识）
3. **`docs/` 目录** — 设计文档、指南、示例
4. **`specs/` 目录** — 功能规范示例（001-speckit-update-redesign）
5. **`dev/` 目录** — 开发中的 feature-dev 插件原型
6. **`CLAUDE.md`** — 详尽的项目指引
7. **`AI-SDD-INTEGRATION.md`、`SDD-Speckit-GUIDE.md`** — 集成和使用指南
8. **`create-simple-feature.py`** — template 独有的 Python 脚本

---

## 3. ai-plugin-market 详解

### 3.1 项目定位

ai-plugin-market 是一个 **Claude Code 插件市场仓库**，它的核心使命是：

1. **作为插件分发渠道** — 让用户可以通过 `/plugin install` 一键安装 SDD 框架
2. **提供标准化的插件包** — 遵循 Claude Code 插件规范（`.claude-plugin/plugin.json`）
3. **降低框架使用门槛** — 不需要克隆模板、运行脚本，安装即用

### 3.2 完整目录结构

```
ai-plugin-market/
├── README.md                         # 项目概述（英文）
├── INSTALL.md                        # 安装指南（中文）
├── LICENSE                           # MIT 许可证
├── cleanup-claude.sh                 # 清理旧版项目级插件文件的脚本
│
└── plugins/
    └── web3sdd/                      # === 核心插件包 ===
        ├── .claude-plugin/
        │   └── plugin.json           #   插件元数据
        ├── README.md                 #   插件介绍
        ├── agents/                   #   12 个 Agent（与 template 完全相同）
        ├── commands/                 #   15 个命令（比 template 多 1 个）
        │   ├── (与 template 相同的 14 个)
        │   └── simplesdd.feature-dev.md  # [额外] 顶层 feature-dev 命令
        ├── skills/                   #   13 个技能（比 template 多 2 个）
        │   ├── (与 template 相同的 11 个)
        │   ├── safe-copy/            # [额外] 安全复制技能
        │   └── skill-development/    # [额外] 技能开发指南
        └── .specify/                 #   配置和脚本（少 1 个脚本）
            ├── knowledge-config.yaml
            ├── knowledge-config.json
            └── scripts/
                ├── bash/      (7 个 .sh)
                ├── python/    (7 个 .py，缺少 create-simple-feature.py)
                └── powershell/(7 个 .ps1)
```

### 3.3 独有内容（AI-SDD-template 没有的）

1. **`plugin.json`** — Claude Code 插件元数据
   ```json
   {
     "name": "web3sdd",
     "description": "A plugin for building AI Software Development (AI-SDD).",
     "author": { "name": "ThroughSky", "url": "https://github.com/throughsky" }
   }
   ```
2. **`simplesdd.feature-dev.md`** — 顶层 feature-dev 命令（可能是为了兼容插件命名空间）
3. **`safe-copy` skill** — 安全复制技能（带排除配置和独立 Python 脚本）
4. **`skill-development` skill** — 技能开发指南
5. **`cleanup-claude.sh`** — 清理旧版项目级文件的迁移脚本
6. **`INSTALL.md`** — 详细的安装步骤指南
7. **`LICENSE`** — MIT 开源许可证

### 3.4 安装和使用流程

```bash
# 1. 添加插件市场
/plugin marketplace add git@github.com:WeTechHK/ai-plugin-market.git

# 2. 安装插件
/plugin install web3sdd@ai-plugin-market

# 3. 重启 Claude Code
/exit && claude

# 4. 安装 .specify 配置到项目
/web3sdd:copy-specify

# 5. 挂载知识库（如需要）
/web3sdd:speckit.knowledge
```

---

## 4. 实现层面的深度差异对比

### 4.1 分发机制差异（最核心的区别）

这是两个项目**最本质的区别**——同一个框架的两种分发方式：

```
┌─────────────────────────────────────────────────────────────┐
│                    AI-SDD 框架（源头）                        │
│    agents + commands + skills + .specify + .knowledge        │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
     ┌─────────▼─────────┐  ┌────────▼──────────┐
     │  AI-SDD-template  │  │  ai-plugin-market  │
     │   脚本集成模式     │  │    插件分发模式     │
     └─────────┬─────────┘  └────────┬──────────┘
               │                      │
     运行 AI-SDD-init.py      /plugin install web3sdd
               │                      │
     ┌─────────▼─────────┐  ┌────────▼──────────┐
     │   目标项目/.claude  │  │  ~/.claude/plugins │
     │   项目级（优先级高）│  │  全局级（优先级低） │
     └───────────────────┘  └───────────────────┘
```

| 维度 | AI-SDD-template（脚本模式） | ai-plugin-market（插件模式） |
|------|---------------------------|---------------------------|
| **安装方式** | 克隆仓库 → `python3 AI-SDD-init.py` | `/plugin install web3sdd@ai-plugin-market` |
| **安装位置** | 目标项目的 `.claude/` 目录 | 全局 `~/.claude/plugins/` 或类似位置 |
| **优先级** | **项目级（高优先级）** | **插件级（低优先级）** |
| **命令前缀** | `/speckit.specify` | `/web3sdd:speckit.specify` |
| **更新方式** | 重新运行 `AI-SDD-init.py` | `/plugin update web3sdd` |
| **知识库** | 完整的 L0/L1/L2 内容随项目 | 需额外挂载（`/web3sdd:speckit.knowledge`） |
| **版本管理** | git subtree | 插件市场版本 |
| **可定制性** | 可直接修改项目内文件 | 插件文件不建议直接修改 |

### 4.2 文件组织结构差异

```
AI-SDD-template                          ai-plugin-market
─────────────────                        ──────────────────
.claude/                                 plugins/web3sdd/
├── agents/                              ├── .claude-plugin/
├── commands/                            │   └── plugin.json    ← 插件元数据
├── skills/                              ├── agents/
                                         ├── commands/
.specify/                                ├── skills/
├── scripts/                             └── .specify/
├── templates/                               ├── scripts/
├── memory/                                  (无 templates/)
│   └── constitution.md                      (无 memory/)
└── knowledge-config.yaml

.knowledge/                              (无 .knowledge 目录)
├── upstream/L0-enterprise/
└── upstream/L1-project/

AI-SDD-init.py                           (无初始化脚本)
docs/                                    (无设计文档)
specs/                                   (无功能规范示例)
dev/                                     (无开发原型)
```

### 4.3 组件数量差异

| 组件类型 | AI-SDD-template | ai-plugin-market | 差异 |
|---------|----------------|-----------------|------|
| **Agents** | 12 | 12 | 完全相同 |
| **Commands** | 14（含 simplesdd 子目录） | 15（多 1 个顶层 feature-dev） | +1 |
| **Skills** | 11 | 13（多 safe-copy、skill-development） | +2 |
| **Scripts (bash)** | 7 | 7 | 相同 |
| **Scripts (python)** | 8 | 7（缺 create-simple-feature.py） | -1 |
| **Scripts (powershell)** | 7 | 7 | 相同 |
| **Templates** | 14 | 0 | -14 |
| **知识库文件** | 30+ | 0 | -30+ |
| **文档/指南** | 10+ | 3 | -7+ |

### 4.4 内容一致性验证

通过 `diff` 对比验证，以下内容在两个项目中**完全一致（逐字节相同）**：

- 全部 12 个 Agent 定义
- 全部 14 个共有 Command 定义（含 simplesdd/feature-dev.md）
- 10 个共有 Skill（claudemd-init 有微小 description 差异）
- knowledge-config.yaml / knowledge-config.json
- 所有共有的 bash/python/powershell 脚本

**唯一的内容差异**：`skills/claudemd-init/SKILL.md` 的 description 字段有细微文本差异。

### 4.5 .specify 配置差异

| 子目录/文件 | AI-SDD-template | ai-plugin-market | 说明 |
|------------|----------------|-----------------|------|
| `knowledge-config.yaml` | 有 | 有 | 内容相同 |
| `knowledge-config.json` | 有 | 有 | 内容相同 |
| `memory/constitution.md` | 有 | **无** | 项目章程在 template 中维护 |
| `templates/` | 有（14 个模板） | **无** | 模板文件不随插件分发 |
| `scripts/bash/` | 7 个 | 7 个 | 相同 |
| `scripts/python/` | **8 个** | **7 个** | 缺少 `create-simple-feature.py` |
| `scripts/powershell/` | 7 个 | 7 个 | 相同 |

**关键缺失**：
- `templates/` 目录完全缺失 — 这意味着插件模式下，规范模板需要从其他地方获取或由命令自行生成
- `memory/constitution.md` 缺失 — 项目章程需要用户自行创建或通过 `/speckit.constitution` 生成
- `create-simple-feature.py` 缺失 — SimpleSDD 的功能创建脚本不可用

---

## 5. 组件级逐项对比

### 5.1 Agents 对比（12/12 完全相同）

所有 Agent 在两个项目中完全一致，没有任何差异。这说明 Agent 定义是框架的核心不变量。

### 5.2 Commands 对比

| 命令 | template | plugin-market | 状态 |
|------|----------|--------------|------|
| speckit.specify | 有 | 有 | 完全相同 |
| speckit.plan | 有 | 有 | 完全相同 |
| speckit.implement | 有 | 有 | 完全相同 |
| speckit.tasks | 有 | 有 | 完全相同 |
| speckit.summary | 有 | 有 | 完全相同 |
| speckit.clarify | 有 | 有 | 完全相同 |
| speckit.checklist | 有 | 有 | 完全相同 |
| speckit.analyze | 有 | 有 | 完全相同 |
| speckit.constitution | 有 | 有 | 完全相同 |
| speckit.knowledge | 有 | 有 | 完全相同 |
| speckit.taskstoissues | 有 | 有 | 完全相同 |
| full-analysis | 有 | 有 | 完全相同 |
| git-commit | 有 | 有 | 完全相同 |
| copy-specify | 有 | 有 | 完全相同 |
| simplesdd/feature-dev | 有 | 有 | 完全相同 |
| **simplesdd.feature-dev** | **无** | **有** | **plugin-market 独有** |

`simplesdd.feature-dev.md` 是一个 382 行的顶层命令文件，推测是为了解决插件命令命名空间的问题——插件模式下子目录命令可能需要一个顶层入口。

### 5.3 Skills 对比

| Skill | template | plugin-market | 状态 |
|-------|----------|--------------|------|
| code-review | 有 | 有 | 完全相同 |
| spec-knowledge-loader | 有 | 有 | 完全相同 |
| spec-summary | 有 | 有 | 完全相同 |
| kb-retriever | 有 | 有 | 完全相同 |
| kb-index-generator | 有 | 有 | 完全相同 |
| simplesdd-init | 有 | 有 | 完全相同 |
| claudemd-init | 有 | 有 | **微小差异**（description 文本） |
| spec-brainstorm | 有 | 有 | 完全相同 |
| wiki-write | 有 | 有 | 完全相同 |
| wiki-update | 有 | 有 | 完全相同 |
| wiki-init | 有 | 有 | 完全相同 |
| **safe-copy** | **无** | **有** | **plugin-market 独有** |
| **skill-development** | **无** | **有** | **plugin-market 独有** |

**`safe-copy` skill**：提供安全复制功能，包含排除配置（`exclude-config.json`）和独立 Python 脚本（`safe-copy.py`），用于在复制 `.specify/` 目录时排除不需要的文件。这在插件模式下更有意义——因为插件需要将配置复制到用户项目。

**`skill-development` skill**：技能开发指南，帮助开发者创建新的 skill。这是面向框架扩展者的工具。

---

## 6. 架构设计哲学差异

### 6.1 集成深度 vs 安装便捷

```
          集成深度（深）                    安装便捷（高）
              ↑                                ↑
              │                                │
 AI-SDD-template ←──────────────────→ ai-plugin-market
              │                                │
 - 完整知识库随项目                    - 一键安装
 - 项目级优先级                       - 全局插件级
 - 可深度定制                         - 开箱即用
 - 需要手动初始化                     - 需后续配置
 - 含示例和文档                       - 精简分发包
```

### 6.2 "源码 vs 发行版" 的关系

这很像软件的源码构建 vs 预编译包的关系：

| 类比 | AI-SDD-template | ai-plugin-market |
|------|----------------|-----------------|
| Linux | 从源码编译内核 | 用 apt/yum 安装包 |
| Node.js | 克隆 repo + npm link | npm install -g |
| Python | 开发模式 pip install -e | pip install |

**AI-SDD-template 更适合**：
- 框架开发者和贡献者
- 需要深度定制知识库的企业
- 需要管理 L0/L1 知识库内容的团队
- 大型项目的首次集成

**ai-plugin-market 更适合**：
- 框架的最终用户
- 快速试用和评估
- 不需要修改框架核心的团队
- 多项目共享同一份插件

### 6.3 知识库策略差异

这是两者在**实际使用体验上**最大的差异：

**AI-SDD-template**：
- L0 知识库通过 `git subtree` 自动挂载
- L1 知识库按需挂载
- 知识库内容物理存在于项目中（`.knowledge/upstream/`）
- `AI-SDD-init.py` 自动处理挂载流程

**ai-plugin-market**：
- 不包含知识库内容
- 需要用户通过 `/web3sdd:speckit.knowledge` 手动挂载
- 知识库依赖外部 git 仓库
- `copy-specify` 命令将配置复制到项目，但不含知识库

### 6.4 模板和章程的处理

**AI-SDD-template**：
- 包含完整的 `templates/` 目录（14 个模板文件）
- 包含 `constitution.md`（10 大核心原则的项目章程）
- 这些文件通过 `AI-SDD-init.py` 复制到目标项目

**ai-plugin-market**：
- 不包含 `templates/` 和 `constitution.md`
- 用户需要通过 `/speckit.constitution` 命令创建章程
- 模板可能内嵌在命令定义中，或需要从 template 仓库获取

---

## 7. 总结与关系图

### 7.1 整体关系

```
                 ┌──────────────────────────────────┐
                 │       AI-SDD 框架生态系统         │
                 └──────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼                               ▼
   ┌─────────────────────┐       ┌─────────────────────┐
   │  AI-SDD-template    │       │  ai-plugin-market    │
   │                     │       │                     │
   │  角色：源码仓库      │  ───→ │  角色：分发渠道      │
   │  受众：开发者/企业   │ 同步   │  受众：最终用户      │
   │  方式：脚本集成      │       │  方式：插件安装      │
   │                     │       │                     │
   │  [完整]             │       │  [精简]             │
   │  ✓ 12 Agents        │       │  ✓ 12 Agents        │
   │  ✓ 14 Commands      │       │  ✓ 15 Commands (+1) │
   │  ✓ 11 Skills        │       │  ✓ 13 Skills (+2)   │
   │  ✓ 30+ 知识库文件    │       │  ✗ 无知识库内容      │
   │  ✓ 14 模板文件       │       │  ✗ 无模板文件        │
   │  ✓ 项目章程          │       │  ✗ 无章程            │
   │  ✓ 设计文档/示例     │       │  ✗ 无文档/示例       │
   │  ✓ 初始化脚本        │       │  ✓ plugin.json      │
   │                     │       │  ✓ cleanup 脚本      │
   │                     │       │  ✓ safe-copy skill   │
   └─────────────────────┘       └─────────────────────┘
              │                               │
              ▼                               ▼
   ┌─────────────────────┐       ┌─────────────────────┐
   │  目标项目/.claude/   │       │  全局插件目录        │
   │  (项目级，高优先级)   │       │  (插件级，低优先级)   │
   └─────────────────────┘       └─────────────────────┘
```

### 7.2 核心结论

1. **本质相同**：两个项目包含几乎完全相同的核心组件（agents/commands/skills），它们是同一个 SDD 框架的两种分发形态。

2. **最核心差异是分发方式**：template 通过脚本集成（深度嵌入项目），plugin-market 通过插件安装（全局共享）。

3. **知识库是关键区分点**：template 包含完整的三层知识库内容，是知识驱动开发的完整体现；plugin-market 不含知识库，依赖后续挂载。

4. **优先级机制**：项目级（template 方式）优先于插件级（plugin-market 方式），这意味着两种方式可以共存但 template 方式的配置会覆盖插件配置。

5. **plugin-market 多了实用工具**：额外的 `safe-copy` skill 和 `simplesdd.feature-dev.md` 顶层命令，是为了适配插件分发场景的实际需求。

6. **template 更完整但更重**：包含文档、示例、知识库、开发原型——适合框架维护者和深度用户。

7. **plugin-market 更轻便但需补充**：安装后还需手动复制配置和挂载知识库，但入门门槛低得多。

### 7.3 推荐使用场景

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| 首次评估 SDD 框架 | ai-plugin-market | 安装简单，快速体验 |
| 企业级项目集成 | AI-SDD-template | 需要完整知识库和深度定制 |
| 多项目统一使用 | ai-plugin-market | 全局安装，一次配置 |
| 框架二次开发 | AI-SDD-template | 源码在手，自由修改 |
| CI/CD 集成 | AI-SDD-template | 脚本可集成到构建流程 |
| 个人开发者日常使用 | ai-plugin-market | 即装即用 |
