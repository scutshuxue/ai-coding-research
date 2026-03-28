# LangGraph DeepAgent 架构深度解析

## 目录

- [背景与动机](#背景与动机)
- [三层架构总览](#三层架构总览)
- [四大核心支柱](#四大核心支柱)
- [中间件架构](#中间件架构)
- [Skills 技能系统](#skills-技能系统)
- [与普通 LangGraph Agent 对比](#与普通-langgraph-agent-对比)
- [快速上手](#快速上手)
- [使用场景决策](#使用场景决策)
- [参考资源](#参考资源)

---

## 背景与动机

传统"浅层 Agent"基于工具调用循环（tool-call loop），在复杂长周期任务中存在四大瓶颈：

| 痛点 | 说明 |
|------|------|
| 上下文溢出 | 工具返回大量中间结果，快速填满上下文窗口 |
| 任务漂移 | 缺乏规划机制，多步骤执行中偏离目标 |
| 单线程瓶颈 | 无法将复杂任务分解委托给子 Agent |
| 状态不持久 | 跨会话信息无法有效保留 |

LangChain 团队观察到 Claude Code、Manus、Deep Research 等系统的成功模式，将其系统化为 **DeepAgents** 框架。

> 核心洞察：深度不来自算法创新，而来自精心的工程设计——详细提示词 + 规划工具 + 文件系统 + 子 Agent。

```mermaid
graph LR
    A[传统浅层 Agent] -->|上下文溢出| B[失败]
    A -->|任务漂移| B
    A -->|单线程| B
    C[Claude Code / Manus / Deep Research] -->|成功模式提取| D[DeepAgents 框架]
    D -->|解决| E[复杂自主长任务]
```

---

## 三层架构总览

DeepAgents 在 LangGraph 和 LangChain 之上构建了 **Agent Harness（代理装具）层**：

```mermaid
graph TB
    subgraph "DeepAgents 三层架构"
        H["🔧 DeepAgents<br/>(Agent Harness)<br/>规划 · 上下文管理 · 多Agent编排"]
        F["📦 LangChain<br/>(Agent Framework)<br/>Agent抽象 · 工具绑定"]
        R["⚙️ LangGraph<br/>(Agent Runtime)<br/>有状态图执行引擎"]
    end
    H --> F --> R

    style H fill:#4A90D9,stroke:#333,color:#fff
    style F fill:#7B68EE,stroke:#333,color:#fff
    style R fill:#2ECC71,stroke:#333,color:#fff
```

**关键点**：`create_deep_agent()` 返回的是编译好的 LangGraph 图，可直接使用流式输出、Studio 调试、Checkpointer 持久化等全部能力。

---

## 四大核心支柱

```mermaid
graph TB
    DA[DeepAgents] --> P["📋 规划工具<br/>write_todos"]
    DA --> FS["📁 文件系统后端<br/>ls / read / write / edit"]
    DA --> SP["📝 详细系统提示词<br/>Few-shot + 行为规范"]
    DA --> SA["🤖 子Agent<br/>task 工具"]

    P --> P1[任务拆解为离散步骤]
    P --> P2[动态追踪完成进度]
    P --> P3[自适应调整计划]

    FS --> FS1[大结果卸载到存储]
    FS --> FS2["可插拔后端<br/>内存/磁盘/S3"]
    FS --> FS3[跨会话知识持久化]

    SP --> SP1[工具使用说明]
    SP --> SP2[Few-shot 示例]
    SP --> SP3[行为指导规范]

    SA --> SA1[独立上下文窗口]
    SA --> SA2[只返回最终结果]
    SA --> SA3[支持并行执行]

    style DA fill:#E74C3C,stroke:#333,color:#fff
    style P fill:#3498DB,stroke:#333,color:#fff
    style FS fill:#2ECC71,stroke:#333,color:#fff
    style SP fill:#F39C12,stroke:#333,color:#fff
    style SA fill:#9B59B6,stroke:#333,color:#fff
```

### 1. 详细系统提示词（Detailed System Prompt）

类比 Claude Code 的系统提示词设计，包含详细工具使用说明、Few-shot 示例和行为指导规范，是"上下文工程"的基础层。

### 2. 规划工具（Planning Tool）

内置 `write_todos` 工具，将复杂目标拆解为离散步骤，动态追踪完成进度，随新信息出现自适应调整计划。本质上是一个"无副作用"工具，用于保持 Agent 在长时间执行中的方向感。

### 3. 文件系统后端（Filesystem Backend）

内置文件操作工具集（`ls`、`read_file`、`write_file`、`edit_file`），将大型工具返回结果卸载到存储，解决上下文溢出问题。支持可插拔后端（内存、本地磁盘、LangGraph State/Store、S3 等）。

### 4. 子 Agent（Sub-agents）

内置 `task` 工具，主 Agent 可委派任务给隔离的子 Agent。每个子 Agent 拥有独立上下文窗口，防止状态泄漏；主 Agent 只接收子 Agent 的最终结果，支持并行执行。

---

## 中间件架构

DeepAgents 的关键工程创新是将四大要素实现为**可组合的中间件层**，类似 Express.js / Django 的中间件模式。

### AgentMiddleware 协议

每个中间件实现三个生命周期钩子：

```python
class AgentMiddleware:
    def before_agent(self, state):
        """会话初始化时运行一次，用于状态设置"""
        pass

    def wrap_model_call(self, call_model, state):
        """拦截每次模型调用，可修改提示词"""
        pass

    def wrap_tool_call(self, call_tool, tool_call, state):
        """拦截工具执行，可修改参数或处理结果"""
        pass
```

### 内置中间件执行链

```mermaid
graph TD
    U[用户调用] --> T1

    T1["📋 TodoListMiddleware<br/>任务规划"] --> T2
    T2["🧠 MemoryMiddleware<br/>加载 AGENTS.md 上下文记忆"] --> T3
    T3["🎯 SkillsMiddleware<br/>加载 SKILL.md 技能定义"] --> T4
    T4["📁 FilesystemMiddleware<br/>文件操作 + 大结果卸载"] --> T5
    T5["🤖 SubAgentMiddleware<br/>子Agent委派"] --> T6
    T6["📐 SummarizationMiddleware<br/>上下文窗口压缩"] --> T7
    T7["💰 AnthropicPromptCachingMiddleware<br/>提示词缓存（降低成本）"] --> T8
    T8["🔧 PatchToolCallsMiddleware<br/>修复工具调用ID"] --> T9
    T9["👤 自定义用户中间件"] --> T10
    T10["🛡️ HumanInTheLoopMiddleware<br/>人工审批门（最后一关）"] --> E

    E[工具执行]

    style T1 fill:#3498DB,stroke:#333,color:#fff
    style T2 fill:#2ECC71,stroke:#333,color:#fff
    style T3 fill:#E67E22,stroke:#333,color:#fff
    style T4 fill:#1ABC9C,stroke:#333,color:#fff
    style T5 fill:#9B59B6,stroke:#333,color:#fff
    style T6 fill:#E74C3C,stroke:#333,color:#fff
    style T7 fill:#F1C40F,stroke:#333,color:#000
    style T8 fill:#95A5A6,stroke:#333,color:#fff
    style T9 fill:#34495E,stroke:#333,color:#fff
    style T10 fill:#C0392B,stroke:#333,color:#fff
```

### 中间件拦截机制

```mermaid
sequenceDiagram
    participant User as 用户
    participant MW as 中间件链
    participant LLM as 大模型
    participant Tool as 工具

    User->>MW: 发送消息
    Note over MW: before_agent() 初始化

    loop 每次模型调用
        MW->>MW: wrap_model_call() 拦截
        MW->>LLM: 转发（可能修改了提示词）
        LLM-->>MW: 返回响应

        alt LLM 决定调用工具
            MW->>MW: wrap_tool_call() 拦截
            MW->>Tool: 执行工具（可能修改了参数）
            Tool-->>MW: 返回结果
            Note over MW: 中间件可修改/卸载结果
            MW->>LLM: 将结果返回给模型
        else LLM 直接回复
            MW-->>User: 返回最终结果
        end
    end
```

---

## Skills 技能系统

Skills 实现了"能力渐进披露"机制，采用**按需加载**设计避免 Token 浪费。

### 加载流程

```mermaid
graph LR
    A["Agent 启动"] -->|加载| B["所有技能的<br/>name + description<br/>（轻量索引）"]
    B -->|用户请求匹配| C{"匹配到技能？"}
    C -->|是| D["动态加载完整<br/>SKILL.md 内容"]
    C -->|否| E["使用默认能力"]
    D --> F["按技能指令执行"]

    style A fill:#3498DB,stroke:#333,color:#fff
    style D fill:#2ECC71,stroke:#333,color:#fff
```

### 目录结构

```
.deepagents/
└── skills/
    ├── web-research/
    │   ├── SKILL.md        # 必需：YAML frontmatter + Markdown 指令
    │   └── helper.py       # 可选：辅助脚本
    └── code-review/
        └── SKILL.md
```

### SKILL.md 格式示例

```yaml
---
name: web-research
description: Perform comprehensive web research on any topic
version: 1.0.0
tags: [research, web, search]
---

# Web Research Skill

When the user asks to research a topic, follow these steps:
1. Identify key search queries
2. Search multiple sources
3. Synthesize findings
4. Write summary to research.md
```

---

## 与普通 LangGraph Agent 对比

| 维度 | 普通 LangGraph Agent | DeepAgents |
|------|---------------------|------------|
| **抽象层级** | 低层：手动定义图节点和边 | 高层：开箱即用的 Agent Harness |
| **控制粒度** | 精确控制每一步执行 | 信任 LLM 自主决策 |
| **规划能力** | 需手动实现 | 内置 `write_todos` |
| **上下文管理** | 需手动处理 | 自动卸载 + 自动摘要 |
| **子 Agent** | 需手动编排 | 内置 `task` 工具 |
| **Token 消耗** | 相对较少 | 约为 LangGraph 的 **20 倍** |
| **执行速度** | 相对较慢 | 并行子 Agent，Wall-time 更快 |
| **适用场景** | 确定性工作流 + Agent 混合 | 复杂自主长任务 |

```mermaid
quadrantChart
    title 技术选型象限图
    x-axis 低控制粒度 --> 高控制粒度
    y-axis 低复杂度 --> 高复杂度
    quadrant-1 DeepAgents 最佳
    quadrant-2 LangGraph 最佳
    quadrant-3 简单 LLM 调用即可
    quadrant-4 LangChain 框架
    DeepAgents: [0.3, 0.85]
    LangGraph: [0.8, 0.7]
    LangChain: [0.6, 0.4]
    直接 API 调用: [0.2, 0.2]
```

---

## 快速上手

### 安装

```bash
# Python
pip install deepagents
# 或
uv add deepagents

# JavaScript/TypeScript
npm install deepagents
```

### 最简使用

```python
from deepagents import create_deep_agent

# 开箱即用
agent = create_deep_agent()

result = agent.invoke({
    "messages": [{"role": "user", "content": "Research LangGraph and write a summary to summary.md"}]
})
```

### 自定义工具和模型

```python
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent

def get_stock_price(ticker: str) -> str:
    """获取股票实时价格"""
    return f"{ticker}: $150.00"

agent = create_deep_agent(
    model=init_chat_model("openai:gpt-4o"),
    tools=[get_stock_price],
    system_prompt="你是一个专业的金融分析助手，擅长市场研究。",
)

# 支持流式输出（底层是 LangGraph 图）
for chunk in agent.stream({"messages": [{"role": "user", "content": "分析 AAPL 股票"}]}):
    print(chunk)
```

### Agent 完整生命周期

```mermaid
sequenceDiagram
    participant Dev as 开发者
    participant DA as create_deep_agent()
    participant Graph as LangGraph 图
    participant LLM as 大模型
    participant Tools as 工具集

    Dev->>DA: 传入 model, tools, system_prompt
    DA->>DA: 组装中间件链
    DA->>DA: 注入内置工具 (todos, fs, task)
    DA->>Graph: 编译为 LangGraph 图
    Graph-->>Dev: 返回可执行 Agent

    Dev->>Graph: agent.invoke() 或 agent.stream()
    Graph->>LLM: 发送消息 + 系统提示词

    loop 自主执行循环
        LLM->>LLM: 思考下一步
        alt 调用 write_todos
            LLM->>Tools: 拆解任务计划
        else 调用 task (子Agent)
            LLM->>Tools: 委派子任务
            Tools->>LLM: 返回子Agent结果
        else 调用文件工具
            LLM->>Tools: 读写文件
        else 调用自定义工具
            LLM->>Tools: 执行业务逻辑
        else 完成
            LLM-->>Graph: 最终回复
        end
    end

    Graph-->>Dev: 返回结果
```

---

## 使用场景决策

```mermaid
flowchart TD
    Start["新任务"] --> Q1{"任务类型？"}

    Q1 -->|"确定性工作流<br/>+ 部分 Agent"| LG["使用 LangGraph<br/>手动定义图"]
    Q1 -->|"复杂自主<br/>长时间运行"| Deep["使用 DeepAgents<br/>开箱即用"]
    Q1 -->|"从零构建<br/>自定义 Agent"| LC["使用 LangChain<br/>框架层"]

    Deep --> D1["研究报告生成"]
    Deep --> D2["代码编写助手"]
    Deep --> D3["数据分析流水线"]
    Deep --> D4["多步骤自动化"]

    LG --> L1["ETL 管道"]
    LG --> L2["审批工作流"]
    LG --> L3["确定性状态机"]

    style Deep fill:#E74C3C,stroke:#333,color:#fff
    style LG fill:#3498DB,stroke:#333,color:#fff
    style LC fill:#2ECC71,stroke:#333,color:#fff
```

---

## 参考资源

| 资源 | 链接 |
|------|------|
| 官方博客 | https://blog.langchain.com/deep-agents/ |
| GitHub 仓库 | https://github.com/langchain-ai/deepagents |
| 官方文档 | https://docs.langchain.com/oss/python/deepagents/overview |
| Skills 使用指南 | https://blog.langchain.com/using-skills-with-deep-agents/ |
| 多 Agent 应用构建 | https://blog.langchain.com/building-multi-agent-applications-with-deep-agents/ |
| DataCamp 教程 | https://www.datacamp.com/tutorial/deep-agents |
| 成本对比分析 | LangGraph vs DeepAgents Token 消耗约 1:20 |

---

*文档生成日期：2026-03-27*
