# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言要求

- 使用**中文**进行所有对话和解释

## 项目概览

AI Coding Research 多项目工作区，通过 Git Submodules 聚合 AI 记忆系统、规范驱动开发、技能集合、创意写作和监管报送自动化测试等项目。

## 探索范围约束

**对话探索范围仅限用户提及的子目录，不要主动扫描或分析未提及的项目。** 本仓库各子目录互相独立，每次对话通常只涉及其中一个子目录。除非用户在提示词中明确展示或提及了多个目录，否则：

- 不要对未提及的子目录执行 Glob/Grep/Read 等探索操作
- 不要在回答中引用或建议修改不相关的子项目
- 专注于当前讨论的目录，提供深入而聚焦的帮助

## 子模块管理

本仓库所有子项目均以 Git Submodule 方式引入，详见 [SUBMODULES.md](SUBMODULES.md)。子模块操作使用标准 `git submodule` 命令。

## 工作区结构

**进入子目录工作时，优先读取该目录下的 CLAUDE.md（如有），其中包含该项目的架构、命令和约束。**

| 目录 | 说明 | 独立 CLAUDE.md |
|------|------|----------------|
| `ai-memory/` | AI 记忆系统（PAI: TypeScript/Bun, cortex-mem: Rust） | — |
| `ai-sdd/` | 规范驱动开发 SDD（AI-SDD-template + ai-plugin-market） | ✅ |
| `ai-skills/` | Claude Code 技能集合（superpowers、gstack、subagents） | — |
| `ai-ide-framework/` | IDE 框架研究（hello-halo 浏览器框架） | — |
| `ai-test/` | AI 测试研究文档 | — |
| `ai-writing/` | AI 写作（创意写作技能 + 唐代小说） | — |
| `dev_project/` | 开发工具（Playwright 离线部署、WSS 隧道代理、VSCode 远程浏览器查看器） | — |
| `rrs_autotest/` | 监管报送自动化测试（Python/PySpark） | ✅ |
| `dev_notes/` | 环境配置笔记（SSH 隧道、Mutagen、Tailscale 等） | — |
| `docs/` | 项目文档（视频字幕工具链、设计文档） | — |

