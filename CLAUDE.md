# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言要求

- 使用**中文**进行所有对话和解释

## 项目概览

AI Coding Research 多项目工作区，通过 Git Submodules 聚合 AI 记忆系统、规范驱动开发、技能集合、创意写作和监管报送自动化测试等项目。

## 子模块管理

本仓库所有子项目均以 Git Submodule 方式引入，详见 [SUBMODULES.md](SUBMODULES.md)。

```bash
# 首次克隆（含子模块）
git clone --recurse-submodules git@github.com:scutshuxue/ai-coding-research.git

# 已克隆后初始化子模块
git submodule init && git submodule update

# 更新所有子模块到远程最新
git submodule update --remote --merge

# 更新单个子模块
git submodule update --remote --merge <子模块路径>

# 添加新子模块
git submodule add <仓库URL> <本地路径>

# 查看子模块状态
git submodule status
```

## 工作区结构

### ai-memory/ — AI 记忆系统

| 子模块 | 技术栈 | 说明 |
|--------|--------|------|
| `Personal_AI_Infrastructure/` (PAI) | TypeScript, Bun | 个人 AI 平台，完整 `.claude/` 配置（hooks、skills、agents、记忆）。安装到 `~/.claude/` |
| `cortex-mem/` | Rust 1.86+, edition 2024 | 三层记忆框架（L0→L1→L2），7 个 workspace crate |

本地文档：`docs/` 包含记忆系统设计对比、架构对比和选型建议。

### ai-sdd/ — 规范驱动开发（SDD）

有独立的 [CLAUDE.md](ai-sdd/CLAUDE.md)，包含完整的架构说明和约束。

| 子模块 | 说明 |
|--------|------|
| `AI-SDD-template/` | SDD 框架模板，含 SpecKit 命令、Agent、三层知识库（L0 > L1 > L2） |
| `ai-plugin-market/` | Claude Code 插件市场（`web3sdd` 插件） |

本地内容：
- `ai-etl/` — ETL 相关培训材料和分析报告
- `rrs_autodev/` — 监管报送 ETL 项目 AI-Coding 整体设计文档
- `docs/` — 项目分析报告

### ai-skills/ — Claude Code 技能集合

| 子模块 | 说明 |
|--------|------|
| `awesome-claude-code-subagents/` | VoltAgent 子代理精选集 |
| `gstack/` | Garry Tan 的技能栈 |
| `superpowers/` | 超级技能集（计划、调试、TDD、代码审查等） |

本地内容：技能对比分析文档（`AI-Skills-Guide.md`、`skills-comparison.md`、`AI-Agent-Skills-Deep-Dive.md`）和演示幻灯片。

### ai-writing/ — AI 写作

| 子模块 | 说明 |
|--------|------|
| `creative-writing-skills/` | AI 创意写作技能 |
| `book_novel_tang/` | 唐代小说书籍项目 |

### rrs_autotest/ — 监管报送自动化测试

有独立的 [CLAUDE.md](rrs_autotest/CLAUDE.md)。技术栈：Python（PySpark、Pandas、Requests）。

基于 Claude Code Skills 架构，通过对话触发 Skill 编排测试流程：
- `flow-requirement-test` — 需求变更测试
- `flow-bug-diagnose` — 问题排查定位
- `flow-regression` — 回归测试

依赖外部 ETL 工程（`/Users/polarischen/code/book_datatest/etl`）和血缘 API（`http://localhost:8000/api`）。

### dev_notes/ — 开发笔记

环境配置相关笔记：Mutagen 文件同步、Playwright 反向 SSH、SSH 反向隧道。

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

SDD 开发工作流：
- **完整流程**（大功能）：`/speckit.specify` → `/speckit.clarify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.checklist` → `/speckit.implement` → `/speckit.summary` → `/git-commit`
- **轻量流程**（小功能/bug 修复）：`/simplesdd:feature-dev <功能描述>`

### PAI

```bash
cd ai-memory/Personal_AI_Infrastructure/Releases/v4.0.3
cp -r .claude ~/ && cd ~/.claude && bash install.sh
bun ~/.claude/PAI/Tools/BuildCLAUDE.ts    # 安装后构建 CLAUDE.md
```

### rrs_autotest（Python）

```bash
cd rrs_autotest
pip install -r requirements.txt     # 安装依赖
python tools/lineage/client.py      # 测试血缘 API 客户端
python tools/schema/client.py       # 测试表结构查询
```

## 工具策略

- 优先使用 LSP 工具进行代码分析（goToDefinition、findReferences、hover、documentSymbol）
- 仅当 LSP 不可用或失败时降级使用 Grep/Glob

## 关键约束

以下约束适用于 ai-sdd 子项目，详见 [ai-sdd/CLAUDE.md](ai-sdd/CLAUDE.md)：

- AI 生成代码必须人工 Review 后方可合并
- 禁止自动提交到 main/master/release 分支
- 禁止修改安全配置文件（.env、secrets、credentials）
- 禁止 SQL 字符串拼接（必须参数化查询）
- 分层架构：Controller → Service → Mapper，禁止跨层调用
