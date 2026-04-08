# AxonFlow Frontend Web UI — Design Spec

## Overview

为 AxonFlow 多 Agent 工作流引擎构建全功能 Web 管理平台，涵盖实时监控、workflow/agent 配置编辑、执行日志浏览等能力。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 API | FastAPI + Uvicorn |
| 实时通信 | WebSocket（FastAPI 原生） |
| 前端框架 | React 18 + TypeScript |
| UI 组件库 | Ant Design 5（ProLayout） |
| 构建工具 | Vite |
| DAG 流程图 | React Flow |
| 代码编辑器 | Monaco Editor（YAML / Markdown） |
| 路由 | React Router v6 |

## 项目结构

```
src/axonflow/
  api/                        # FastAPI 后端
    __init__.py
    app.py                    # FastAPI app 创建、lifespan 管理 engine 单例
    deps.py                   # 依赖注入（get_engine）
    ws.py                     # WebSocket 端点 + EventBroadcaster
    routes/
      __init__.py
      workflows.py            # /api/workflows — CRUD + 执行
      agents.py               # /api/agents — CRUD（含 persona）
      system.py               # /api/system — status, token usage
      logs.py                 # /api/logs — 执行日志查询
      config.py               # /api/config — 全局配置读写

frontend/                     # React SPA（独立 package.json）
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    api/                      # API 客户端
      client.ts               # fetch 封装
      ws.ts                   # WebSocket hook
    layouts/
      MainLayout.tsx          # ProLayout 侧边栏布局
    pages/
      Dashboard.tsx
      Workflows.tsx
      WorkflowDetail.tsx
      WorkflowRun.tsx         # DAG + 实时日志
      Agents.tsx
      AgentDetail.tsx
      Logs.tsx
      Settings.tsx
    components/
      WorkflowDAG.tsx         # React Flow DAG 流程图
      LiveEventLog.tsx        # 实时事件日志面板
      YamlEditor.tsx          # Monaco YAML 编辑器
      MarkdownEditor.tsx      # Monaco Markdown 编辑器
      StatusCard.tsx          # 数字指标卡片
      AgentCard.tsx           # Agent 信息卡片
```

## 后端 API 设计

### REST 端点

| 方法 | 路径 | 描述 | 请求体 | 响应 |
|------|------|------|--------|------|
| GET | `/api/system/status` | 系统状态 | — | `{running, agents, tools, token_usage}` |
| GET | `/api/workflows` | 列出所有 workflow | — | `WorkflowConfig[]` |
| GET | `/api/workflows/{id}` | 单个 workflow 详情 | — | `WorkflowConfig` |
| PUT | `/api/workflows/{id}` | 更新 workflow 配置 | `{yaml: string}` | `WorkflowConfig` or 422 |
| POST | `/api/workflows/{id}/run` | 触发执行 | `{input: string}` | `{run_id: string}` |
| GET | `/api/workflows/{id}/runs` | 执行历史 | — | `WorkflowRunSummary[]` |
| GET | `/api/agents` | 列出所有 agent | — | `AgentConfig[]` |
| GET | `/api/agents/{id}` | 单个 agent 详情（含 persona） | — | `AgentConfig + persona` |
| PUT | `/api/agents/{id}` | 更新 agent 配置 | `{yaml: string}` | `AgentConfig` or 422 |
| PUT | `/api/agents/{id}/persona/{file}` | 更新 persona 文件 | `{content: string}` | 200 |
| GET | `/api/logs/{run_id}` | 获取执行日志 | — | `ExecutionLogEntry[]` |
| GET | `/api/logs` | 全局日志查询 | `?workflow_id=&agent_id=&action=` | `ExecutionLogEntry[]` |
| GET | `/api/config` | 获取全局配置 | — | `AxonFlowConfig`（隐藏 API key） |
| PUT | `/api/config` | 更新全局配置 | `{yaml: string}` | `AxonFlowConfig` or 422 |

### WebSocket 端点

| 路径 | 描述 |
|------|------|
| `/ws/events?run_id={run_id}` | 实时事件流，按 run_id 过滤 |

### WebSocket 消息格式

```json
{
  "type": "routing | tool_call | tool_error | llm_summary | agent_message | workflow.started | workflow.completed | agent.status_changed",
  "workflow_id": "wf-abc123",
  "run_id": "run-001",
  "timestamp": "2026-04-08T12:03:01Z",
  "data": { ... }
}
```

### EventBroadcaster 机制

- `EventBroadcaster` 维护 `dict[str, set[WebSocket]]`，key 为 run_id
- `ExecutionLogger` 扩展 `on_log` 回调，每次 `log()` 时触发
- 回调将 `ExecutionLogEntry` 序列化后广播给对应 run_id 的所有 WebSocket
- 前端连接时指定 `run_id` 进行过滤

## 前端页面设计

### 布局

经典侧边栏布局（Ant Design ProLayout）：左侧固定导航 + 右侧内容区。

导航项：Dashboard / Workflows / Agents / Logs / Settings

### 页面详情

**Dashboard (`/`)**
- 三张 StatusCard：Active Agents、Workflows Run、Tokens Used
- 最近 workflow 执行列表（表格：名称、状态、耗时、时间）

**Workflows (`/workflows`)**
- Ant Design Table 列出所有 workflow
- 列：名称、agents 数量、trigger 类型、操作（Run / 编辑）

**Workflow Detail (`/workflows/:id`)**
- Tab 1: 配置查看/编辑（YamlEditor）
- Tab 2: 执行历史列表
- Run 按钮 → 弹窗输入 input → 触发执行 → 跳转到 Run 页面

**Workflow Run (`/workflows/:id/runs/:runId`)**
- 上方：WorkflowDAG 流程图（React Flow），节点高亮当前 agent 状态
  - 已完成 = 绿色、运行中 = 蓝色+发光、待执行 = 灰色
- 下方：LiveEventLog 实时日志（WebSocket 驱动）
  - 每行：时间戳 + action 类型（颜色编码） + 详情
  - 支持按 action 类型过滤

**Agents (`/agents`)**
- 卡片网格或表格展示所有 agent
- 每个 agent 展示：id、name、role、model、状态徽标

**Agent Detail (`/agents/:id`)**
- Tab 1: 配置编辑（YamlEditor）
- Tab 2-4: Persona 编辑（soul.md / user.md / workflow.md — MarkdownEditor）
- 工具列表展示

**Logs (`/logs`)**
- 全局执行日志浏览器
- 筛选器：workflow_id / agent_id / action 类型
- Ant Design Table 展示日志条目

**Settings (`/settings`)**
- 全局配置编辑（YamlEditor）
- default_model、redis、sandbox、log_level 等
- `api_key_env` 只读展示（安全考虑）

## 配置编辑与持久化

### 编辑流程
```
Monaco Editor (YAML) → PUT API → 后端 yaml.safe_load → Pydantic 校验 → 写入文件 → 热重载
```

### 校验策略
- 后端用 Pydantic 模型校验，失败返回 422 + 字段级错误信息
- 前端在编辑器中高亮错误

### 热重载
- 全局配置变更：重新初始化 LLMGateway 的 default_model
- Agent 配置变更：重建 Agent 实例并替换 AgentRegistry 中的注册
- Workflow 配置变更：无需重载（run_workflow 每次从磁盘读取最新配置）

### 安全约束
- `api_key_env` 在 GET 响应中只返回环境变量名，不返回实际值
- 前端编辑时 `api_key_env` 为只读

## Workflow 执行流程

1. 用户在 Workflow Detail 页点击 Run，输入 initial_input
2. `POST /api/workflows/{id}/run` → 后端 `asyncio.create_task` 启动 workflow → 立即返回 `run_id`
3. 前端跳转到 `/workflows/{id}/runs/{runId}`，建立 WebSocket 连接 `/ws/events?run_id={run_id}`
4. 后端通过 EventBroadcaster 实时推送事件
5. 前端 WorkflowDAG 更新节点状态，LiveEventLog 追加日志行
6. Workflow 完成后推送 `workflow.completed` 事件，前端更新最终状态

## 依赖新增

### Python（pyproject.toml）
```
fastapi >= 0.115, < 1.0
uvicorn[standard] >= 0.30, < 1.0
```

### Node.js（frontend/package.json）
```
react, react-dom, @types/react, @types/react-dom
typescript
vite, @vitejs/plugin-react
antd, @ant-design/pro-layout, @ant-design/icons
react-router-dom
@monaco-editor/react
reactflow
```

## 启动方式

```bash
# 后端（开发模式）
uvicorn axonflow.api.app:app --reload --port 8000

# 前端（开发模式）
cd frontend && npm run dev   # Vite dev server on :5173, proxy /api → :8000

# 生产模式
# 前端 build 后由 FastAPI 的 StaticFiles 托管
```
