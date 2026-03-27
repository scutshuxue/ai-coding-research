# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作提供指导。

## 项目概览

这是一个多项目工作区，包含四个独立子项目，涵盖 AI 记忆系统、规范驱动开发工作流和监管报送自动化测试。

## 语言要求

- 使用**中文**进行所有对话和解释

## 工作区结构

### ai-memory/

包含两个独立的 AI 记忆系统项目：

- **Personal_AI_Infrastructure/** (PAI) — 基于 Claude Code 构建的个人 AI 平台。`Releases/` 下包含多个版本（v2.3 至 v4.0.3），每个版本是完整的 `.claude/` 目录，含 hooks、skills、agents、记忆系统和可观测性工具。技术栈：TypeScript、Bun。安装目标为 `~/.claude/`。
- **cortex-mem/** — 基于 Rust 的 AI 记忆框架，采用三层层级架构（L0 抽象 → L1 概览 → L2 详情）。Workspace 包含 7 个 crate：`cortex-mem-core`、`cortex-mem-config`、`cortex-mem-tools`、`cortex-mem-rig`、`cortex-mem-service`、`cortex-mem-cli`、`cortex-mem-mcp`。要求 Rust 1.86+，edition 2024。

### ai-sdd/

AI 驱动的规范驱动开发（SDD）框架工作区，有独立的 [CLAUDE.md](ai-sdd/CLAUDE.md)。包含：

- **AI-SDD-template/** — SDD 框架模板，含 SpecKit 命令、Agent、技能定义和三层知识库系统（L0 企业级 > L1 项目级 > L2 仓库级）。有独立的 [CLAUDE.md](ai-sdd/AI-SDD-template/CLAUDE.md)。
- **ai-plugin-market/** — Claude Code 插件市场，发布为可安装的 `web3sdd` 插件（代码分析、SDD 工作流相关的 agents、commands、skills）。

### rrs_autotest/

银行监管报送（征信/1104/EAST/AML）自动化测试框架，基于 Claude Code Skills 架构。有独立的 [CLAUDE.md](rrs_autotest/CLAUDE.md)。技术栈：Python（PySpark、Pandas、Requests）。

- 通过 Skill 编排实现流程自动化（flow-*）、外部系统封装（tool-*）、测试指导（test-*）、分析框架（analyze-*）、知识管理（knowledge-*）
- **双轨组织**：`story/` 按需求纵向组织一次性内容，`knowledge/` 按类型横向组织可复用资产
- **设计原则**：奥卡姆剃刀 — 如无必要勿增实体，Skill 控制在 100 行内，描述目标而非规定工具
- 依赖外部 ETL 工程（`/Users/polarischen/code/book_datatest/etl`）和血缘 API（`http://localhost:8000/api`）

## 常用命令

### cortex-mem（Rust）

```bash
cd ai-memory/cortex-mem
cargo build                    # 构建所有 workspace crate
cargo test                     # 运行所有测试
cargo test -p cortex-mem-core  # 运行单个 crate 的测试
cargo run -p cortex-mem-cli    # 运行 CLI
cargo run -p cortex-mem-mcp    # 运行 MCP 服务
```

### AI-SDD

```bash
cd ai-sdd/AI-SDD-template
python3 AI-SDD-init.py          # 初始化或增量更新框架
python3 AI-SDD-init.py --full   # 强制完整初始化

# 知识库操作
.specify/scripts/bash/load-knowledge.sh <command> [--json]
.specify/scripts/bash/load-knowledge.sh validate
.specify/scripts/bash/load-knowledge.sh list
```

### PAI

```bash
# 安装最新版本
cd ai-memory/Personal_AI_Infrastructure/Releases/v4.0.3
cp -r .claude ~/ && cd ~/.claude && bash install.sh

# 安装/升级后构建 CLAUDE.md
bun ~/.claude/PAI/Tools/BuildCLAUDE.ts
```

### rrs_autotest（Python）

```bash
cd rrs_autotest
pip install -r requirements.txt     # 安装依赖（PySpark、Pandas、Requests 等）
python tools/lineage/client.py      # 测试血缘 API 客户端
python tools/schema/client.py       # 测试表结构查询
```

Skill 通过对话触发，无需手动执行命令。三类核心流程：
- `flow-requirement-test` — 需求变更测试
- `flow-bug-diagnose` — 问题排查定位
- `flow-regression` — 回归测试

## 架构说明

### AI-SDD 三层知识库

知识库层级有严格优先级（L0 > L1 > L2），L0 约束不可覆盖：

| 层级 | 路径 | 用途 |
|------|------|------|
| L0 企业级 | `.knowledge/upstream/L0-enterprise/` | 强制约束（安全红线、编码规范） |
| L1 项目级 | `.knowledge/upstream/L1-project/` | 项目级知识（业务领域、架构决策） |
| L2 仓库级 | `.knowledge/` / `specs/{feature}/` | 本地仓库上下文 |

### AI-SDD 开发工作流

- **完整流程**（大功能）：`/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.checklist` → `/speckit.implement` → `/speckit.summary` → `/git-commit`
- **轻量流程**（小功能/bug 修复）：`/simplesdd:feature-dev <功能描述>` — 自动执行 7 个阶段

### cortex-mem Crate 关系

- `cortex-mem-core` — 核心记忆类型和存储引擎（虚拟文件系统 + 向量检索）
- `cortex-mem-config` — 配置管理
- `cortex-mem-tools` — AI Agent 集成的工具抽象
- `cortex-mem-rig` — 与 `rig-core` LLM 框架的集成
- `cortex-mem-service` — HTTP API 服务（Axum）
- `cortex-mem-cli` — 命令行接口（Clap）
- `cortex-mem-mcp` — Model Context Protocol 服务

## 工具策略

- 优先使用 LSP 工具进行代码分析（goToDefinition、findReferences、hover、documentSymbol）
- 仅当 LSP 不可用或失败时降级使用 Grep/Glob

## 关键约束（AI-SDD）

- AI 生成代码必须人工 Review 后方可合并
- 禁止自动提交到 main/master/release 分支
- 禁止修改安全配置文件（.env、secrets、credentials）
- 禁止 SQL 字符串拼接（必须参数化查询）
- 分层架构：Controller → Service → Mapper，禁止跨层调用
