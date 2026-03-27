# Git Submodules 说明

本仓库使用 Git Submodules 管理外部依赖项目。以下是所有子模块的详细信息和使用方法。

## 子模块列表

| 子模块路径 | 远程仓库 | 说明 |
|-----------|---------|------|
| `ai-memory/Personal_AI_Infrastructure` | [danielmiessler/Personal_AI_Infrastructure](https://github.com/danielmiessler/Personal_AI_Infrastructure) | 个人 AI 平台（PAI），基于 Claude Code 的完整 `.claude/` 配置 |
| `ai-memory/cortex-mem` | [sopaco/cortex-mem](https://github.com/sopaco/cortex-mem) | Rust 三层记忆框架（L0→L1→L2），7 个 workspace crate |
| `ai-sdd/AI-SDD-template` | [WeTechHK/AI-SDD-template](https://github.com/WeTechHK/AI-SDD-template) | SDD 框架模板，含 SpecKit 命令和三层知识库 |
| `ai-sdd/ai-plugin-market` | [WeTechHK/ai-plugin-market](https://github.com/WeTechHK/ai-plugin-market) | Claude Code 插件市场（`web3sdd` 插件） |
| `ai-skills/awesome-claude-code-subagents` | [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | Claude Code 子代理精选集 |
| `ai-skills/gstack` | [garrytan/gstack](https://github.com/garrytan/gstack) | Garry Tan 的 Claude Code 技能栈 |
| `ai-skills/superpowers` | [obra/superpowers](https://github.com/obra/superpowers) | Claude Code 超级技能集（计划、调试、TDD 等） |
| `ai-writing/book_novel_tang` | [scutshuxue/book_novel_tang](https://github.com/scutshuxue/book_novel_tang) | 唐代小说书籍项目 |
| `ai-writing/creative-writing-skills` | [haowjy/creative-writing-skills](https://github.com/haowjy/creative-writing-skills) | AI 创意写作技能 |
| `rrs_autotest` | [scutshuxue/rrs_autotest](https://github.com/scutshuxue/rrs_autotest) | 银行监管报送自动化测试框架 |

## 常用操作

### 首次克隆（含子模块）

```bash
git clone --recurse-submodules git@github.com:scutshuxue/ai-coding-research.git
```

或者克隆后再初始化子模块：

```bash
git clone git@github.com:scutshuxue/ai-coding-research.git
cd ai-coding-research
git submodule init
git submodule update
```

### 更新所有子模块到最新提交

```bash
git submodule update --remote --merge
```

### 更新单个子模块

```bash
git submodule update --remote --merge ai-skills/superpowers
```

### 查看子模块状态

```bash
git submodule status
```

### 添加新子模块

```bash
git submodule add <仓库URL> <本地路径>
```

### 移除子模块

```bash
# 1. 取消注册
git submodule deinit -f <子模块路径>
# 2. 删除 .git/modules 中的缓存
rm -rf .git/modules/<子模块路径>
# 3. 删除工作目录中的文件
git rm -f <子模块路径>
```

### 批量拉取子模块的最新代码

```bash
git submodule foreach 'git pull origin main || git pull origin master || true'
```

## 注意事项

- 子模块指向特定的 commit，而非分支。执行 `git submodule update` 会检出记录的 commit
- 使用 `--remote` 参数才会拉取子模块远程分支的最新代码
- 修改子模块内容后，需在子模块目录内单独提交，再回到主仓库提交子模块引用的更新
- 部分子模块使用 SSH 协议（`git@github.com:`），需确保已配置 SSH 密钥
