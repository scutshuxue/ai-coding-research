# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-SDD (AI-driven Specification-Driven Development) 是一个 Claude Code 工作流框架，通过三层知识库系统驱动从规范到代码的完整开发流程。本工作区包含两个独立 Git 仓库：

- **AI-SDD-template/** — SDD 框架模板仓库，包含 SpecKit 命令、Agent、技能定义和知识库结构
- **ai-plugin-market/** — Claude Code 插件市场，发布为可安装的 `web3sdd` 插件

## 语言要求

- **对话语言**: 使用**中文**进行所有对话和解释

## 代码分析工具策略

- 优先使用 LSP 工具进行代码静态语义分析（goToDefinition, findReferences, hover, documentSymbol）
- 仅当 LSP 不可用或失败时降级使用 Grep/Glob

## Architecture

### 三层知识库系统

| 层级 | 路径 | 用途 | 优先级 |
|------|------|------|--------|
| L0 Enterprise | `.knowledge/upstream/L0-enterprise/` | 企业级强制约束（安全红线、编码规范、架构原则），不可覆盖 | 最高 |
| L1 Project | `.knowledge/upstream/L1-project/` | 项目级知识（业务领域、架构决策、项目规范） | 中 |
| L2 Repository | `.knowledge/` / `specs/{feature}/` | 仓库级上下文，本地生成 | 最低 |

冲突时高层级优先：L0 > L1 > L2。

### AI-SDD-template 结构

```
.claude/
├── agents/       # 专业化 Agent（code-explorer, code-architect, work-summarizer 等）
├── commands/     # SpecKit 命令定义（speckit.specify, speckit.plan 等）
└── skills/       # 技能扩展（code-review, kb-retriever, wiki-write 等）

.specify/
├── scripts/      # 辅助脚本（load-knowledge, check-prerequisites）
├── templates/    # 模板文件（spec, plan, tasks, checklist）
├── memory/       # 项目记忆（constitution.md）
└── knowledge-config.yaml  # 知识库加载配置

.knowledge/upstream/  # L0/L1 知识库（通过 git subtree 挂载）
```

### ai-plugin-market 结构

```
plugins/web3sdd/
├── agents/       # 与 template 中相同的 Agent 定义（插件分发版本）
├── commands/     # SpecKit 命令（插件分发版本）
├── skills/       # 技能模块（插件分发版本）
└── .specify/     # 配置和脚本（含 bash/python/powershell 三种脚本实现）
```

### 两个仓库的关系

- `AI-SDD-template` 是源头，通过 `AI-SDD-init.py` 脚本集成到目标项目
- `ai-plugin-market` 是插件分发渠道，通过 `/plugin install web3sdd@ai-plugin-market` 安装
- 两者包含相同的 agents/commands/skills，但分发方式不同（脚本复制 vs 插件安装）

## SDD 开发流程

### 完整流程（大功能，任务数 >10 或涉及多模块）

```
/speckit.specify → /speckit.clarify（可选）→ /speckit.plan → /speckit.tasks → /speckit.checklist（可选）→ /speckit.implement → /speckit.summary → /git-commit
```

### 轻量流程（小功能/bug 修复）

```
/simplesdd:feature-dev <功能描述>
```

自动执行 7 阶段：发现 → 代码库探索 → 澄清 → 架构设计 → 实现 → 质量审查 → 总结

## Commands

### 初始化与知识库

```bash
python3 AI-SDD-init.py          # 首次初始化或增量更新框架
python3 AI-SDD-init.py --full   # 强制完整初始化
/speckit.knowledge               # 挂载/同步知识库（L0 自动挂载，L1 按需）
```

### 知识库脚本

```bash
.specify/scripts/bash/load-knowledge.sh <command> [--json]  # 加载指定命令所需知识库
.specify/scripts/bash/load-knowledge.sh validate             # 验证知识库结构
.specify/scripts/bash/load-knowledge.sh list                 # 列出支持的命令
```

## Key Constraints

### AI 编码红线（L0 强制）

- AI 生成代码必须人工 Review 后方可合并
- 禁止自动提交到 main/master/release 分支
- 禁止修改安全配置文件（.env、secrets、credentials）
- 测试必须有有效断言，禁止跳过失败测试

### 安全基线

- 禁止硬编码凭证（密码、API Key、Token）
- 禁止 SQL 字符串拼接（必须参数化查询）
- 所有外部输入必须校验
- 分层架构：Controller → Service → Mapper，禁止跨层调用
