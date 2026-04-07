# AxonFlow 产品需求文档 (PRD)

> 版本: v1.0  
> 日期: 2026-03-31  
> 状态: 草案  

---

## 1. 项目概述

### 1.1 项目名称
**AxonFlow** — 基于多智能体的自治工作流引擎

### 1.2 项目愿景
让智能体像团队一样协作，实现 24/7 全自动生产力。

### 1.3 项目定位
AxonFlow 是一款基于多智能体系统（Multi-Agent System, MAS）的轻量级自动化工作流搭建平台。通过为不同智能体分配独立职责，智能体之间能够自发地相互发起请求、反馈结果并迭代优化，无需用户实时干预，即可实现复杂任务从开发到交付的全流程闭环。

### 1.4 目标用户
| 用户类型 | 使用场景 |
|---------|---------|
| 独立开发者 | 搭建个人自动化开发流水线，让 AI 代替自己处理编码-测试-部署循环 |
| 小型技术团队 | 构建 7x24 小时运转的自动化任务处理系统 |
| AI 应用探索者 | 实验多智能体协作模式，验证自治系统可行性 |

---

## 2. 核心需求

### 2.1 功能需求

#### FR-01: 智能体定义与管理
- **FR-01-01**: 用户可以通过配置文件（YAML/JSON）定义智能体，包括：
  - 智能体名称与唯一标识
  - 角色描述（Role Prompt）
  - 职责范围（可执行的动作列表）
  - 使用的 LLM 模型及参数
  - 可用工具（Tools）列表
- **FR-01-02**: 系统提供预置的智能体模板（编码、测试、发布等）
- **FR-01-03**: 支持智能体的热加载，无需重启系统即可添加/修改智能体

#### FR-02: 工作流编排
- **FR-02-01**: 用户可通过 YAML 配置文件定义工作流，指定：
  - 参与的智能体列表
  - 触发条件（定时、事件、手动）
  - 智能体间的协作关系（谁可以向谁发起请求）
  - 终止条件（最大迭代次数、目标达成判定）
- **FR-02-02**: 支持以下工作流模式：
  - **线性链式**: A → B → C，按顺序执行
  - **循环迭代**: A → B → C → A（当 C 发现问题时回到 A 重做）
  - **并行扇出**: A 同时向 B、C、D 发起任务
  - **条件分支**: 根据上一步结果决定下一步走向
- **FR-02-03**: 每个工作流拥有独立的上下文（Context），智能体可读写共享状态

#### FR-03: 智能体间通信
- **FR-03-01**: 智能体之间通过消息队列（Message Queue）进行异步通信
- **FR-03-02**: 消息格式统一为结构化 JSON，包含：
  - 发送方 / 接收方标识
  - 消息类型（任务请求 / 结果响应 / 反馈 / 异常）
  - 负载数据（Payload）
  - 关联的工作流 ID 和步骤 ID
- **FR-03-03**: 支持消息的优先级队列
- **FR-03-04**: 支持消息的持久化存储，防止丢失

#### FR-04: 工具系统（Tool System）
- **FR-04-01**: 提供内置工具集：
  - `shell_exec`: 执行 Shell 命令
  - `file_read` / `file_write`: 文件读写操作
  - `git_ops`: Git 操作（commit、push、pull、branch）
  - `http_request`: 发起 HTTP 请求
  - `docker_ops`: Docker 容器操作（build、run、stop）
- **FR-04-02**: 支持用户自定义工具（Plugin 机制）
- **FR-04-03**: 工具执行结果统一返回格式，包含成功/失败状态及输出内容

#### FR-05: LLM 多模型支持
- **FR-05-01**: 支持以下 LLM 后端：
  - OpenAI API（GPT-4o / GPT-4 等）
  - Anthropic API（Claude 系列）
  - 本地模型（通过 Ollama / vLLM）
  - 兼容 OpenAI 格式的任意 API
- **FR-05-02**: 不同智能体可配置不同的 LLM 模型
- **FR-05-03**: 支持模型降级策略（主模型不可用时自动切换备用模型）

#### FR-06: 24/7 守护进程
- **FR-06-01**: 系统以守护进程（Daemon）模式运行，支持后台常驻
- **FR-06-02**: 支持定时任务触发（Cron 表达式）
- **FR-06-03**: 内置健康检查与自动重启机制
- **FR-06-04**: 异常场景下的优雅降级（单个 Agent 失败不影响整体系统）

#### FR-07: 可观测性
- **FR-07-01**: 完整的结构化日志系统（每条消息、每次 LLM 调用、每次工具执行）
- **FR-07-02**: 工作流执行轨迹可视化（Timeline 视图）
- **FR-07-03**: 实时状态面板（Dashboard），展示：
  - 各智能体状态（空闲 / 工作中 / 异常）
  - 消息队列深度
  - 当前活跃工作流
  - LLM Token 消耗统计
- **FR-07-04**: 支持 Webhook 通知（工作流完成/异常时推送）

### 2.2 非功能需求

#### NFR-01: 可靠性
- 消息传递保证 At-Least-Once 语义
- 工作流状态持久化，进程重启后可恢复执行
- 单个智能体崩溃不影响其他智能体运行

#### NFR-02: 可扩展性
- 新增智能体角色只需添加配置文件，零代码改动
- 工具系统插件化，第三方可按接口规范扩展
- 支持水平扩展（多 Worker 消费同一队列）

#### NFR-03: 安全性
- 工具执行支持沙箱模式（可选 Docker 隔离）
- LLM API Key 加密存储
- 支持对智能体的权限控制（限制可使用的工具和可访问的资源）

#### NFR-04: 性能
- 单智能体消息处理延迟 < 500ms（不含 LLM 调用时间）
- 支持同时运行 ≥ 10 个并行工作流
- 消息队列吞吐量 ≥ 1000 msg/s

---

## 3. 核心场景

### 3.1 场景一：自动化软件开发流水线

```
用户输入: "实现一个 Python 的快速排序函数并发布到 PyPI"

Agent-Coder (编码专员):
  → 理解需求，编写 quicksort.py
  → 生成 setup.py / pyproject.toml
  → 发消息给 Agent-Tester

Agent-Tester (测试专员):
  → 接收代码，编写 test_quicksort.py
  → 执行 pytest，收集结果
  → 如果测试失败 → 发消息给 Agent-Coder 附带失败信息
  → 如果测试通过 → 发消息给 Agent-Publisher

Agent-Publisher (发布专员):
  → 接收通过测试的代码
  → 执行 build & publish 流程
  → 输出发布结果
```

### 3.2 场景二：24/7 内容监控与处理

```
Cron 触发 (每小时):

Agent-Monitor (监控专员):
  → 抓取指定 RSS / 网页内容
  → 分析是否有新的有价值信息
  → 如有 → 发消息给 Agent-Processor

Agent-Processor (处理专员):
  → 接收原始信息
  → 进行摘要 / 翻译 / 结构化处理
  → 发消息给 Agent-Reporter

Agent-Reporter (报告专员):
  → 汇总处理后的信息
  → 生成报告并通过 Webhook 推送到飞书/钉钉
```

### 3.3 场景三：数据处理流水线

```
用户输入: "分析 data/ 目录下的 CSV 文件，生成可视化报告"

Agent-Analyst (分析专员):
  → 读取 CSV 文件，分析数据结构和质量
  → 制定分析计划
  → 发消息给 Agent-DataEngineer

Agent-DataEngineer (数据工程专员):
  → 清洗数据、处理缺失值
  → 生成统计指标
  → 发消息给 Agent-Visualizer

Agent-Visualizer (可视化专员):
  → 生成 matplotlib/plotly 图表
  → 组织为 HTML 报告
  → 输出到 output/ 目录
```

---

## 4. 用户交互方式

### 4.1 CLI 命令

```bash
# 启动系统
axonflow start

# 以守护进程模式启动
axonflow start --daemon

# 提交一个任务到工作流
axonflow run <workflow_name> --input "你的需求描述"

# 查看当前运行状态
axonflow status

# 查看工作流执行历史
axonflow history [workflow_id]

# 停止系统
axonflow stop

# 查看实时日志
axonflow logs [--follow]

# 管理智能体
axonflow agent list
axonflow agent add <config_file>
axonflow agent remove <agent_id>
```

### 4.2 配置文件示例

**智能体定义 (agents/coder.yaml):**
```yaml
agent:
  id: agent-coder
  name: "编码专员"
  role: |
    你是一名资深软件工程师。你的职责是根据需求编写高质量的代码。
    你必须遵循以下原则：
    - 代码简洁、可读、有注释
    - 遵循语言最佳实践
    - 包含必要的错误处理
  model:
    provider: openai
    name: gpt-4o
    temperature: 0.2
    max_tokens: 4096
  tools:
    - file_write
    - file_read
    - shell_exec
    - git_ops
  can_request:
    - agent-tester
    - agent-publisher
```

**工作流定义 (workflows/dev-pipeline.yaml):**
```yaml
workflow:
  id: dev-pipeline
  name: "软件开发流水线"
  trigger:
    type: manual
  agents:
    - agent-coder
    - agent-tester
    - agent-publisher
  flow:
    entry: agent-coder
    max_iterations: 5
    terminate_on:
      - agent: agent-publisher
        status: success
  context:
    shared:
      project_dir: "./workspace"
      language: "python"
```

---

## 5. 约束与假设

### 5.1 约束
- V1.0 版本仅支持 CLI 交互，不提供 Web UI
- 消息队列暂定使用 Redis Streams（轻量级，减少部署依赖）
- 单机部署优先，分布式部署作为后续规划

### 5.2 假设
- 用户具备基本的终端操作能力
- 用户已自行准备 LLM API Key 或本地模型环境
- 运行环境为 Linux/macOS，Python ≥ 3.11

---

## 6. 里程碑规划

| 阶段 | 里程碑 | 内容 | 预计周期 |
|------|--------|------|---------|
| M0 | 基础骨架 | 项目结构搭建、核心抽象定义、消息协议设计 | 1 周 |
| M1 | 最小可用 | Agent 基类实现、进程内消息通信、单工作流执行 | 2 周 |
| M2 | 核心功能 | Redis 消息队列集成、多模型支持、工具系统、循环迭代流程 | 3 周 |
| M3 | 生产就绪 | 守护进程、Cron 调度、日志系统、异常恢复、CLI 完善 | 2 周 |
| M4 | 可观测性 | Dashboard、执行轨迹可视化、Webhook 通知 | 2 周 |
| M5 | 生态扩展 | 插件市场、预置工作流模板库、社区 Agent 分享 | 持续迭代 |

---

## 7. 风险识别

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 输出不稳定导致智能体行为异常 | 高 | 设置最大迭代次数、输出格式校验、异常兜底逻辑 |
| 智能体间死循环 | 高 | 全局迭代计数器、环路检测、超时自动终止 |
| LLM API 调用成本失控 | 中 | Token 用量监控、预算上限配置、低优先级任务使用廉价模型 |
| 工具执行的安全风险（如 shell 命令） | 高 | 沙箱隔离、命令白名单、危险操作二次确认 |
| Redis 单点故障 | 中 | 支持降级到进程内队列、后续支持 Redis Sentinel |
