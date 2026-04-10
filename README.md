# AxonFlow

**基于多智能体的自治工作流引擎** — 让智能体像团队一样协作，实现 24/7 全自动生产力。

AxonFlow 提供完整的多 Agent 编排系统：Agent 自主调用工具、多 Agent 按路由协作、Supervisor 模式监督、Web 管理界面实时监控、CLI 命令行操作。

---

## 功能特性

- **多智能体协作**：Agent 按工作流路由自动流转，支持 Flat 和 Supervisor 两种编排模式
- **15 个内置工具**：文件读写、Shell 执行、Git 操作、网络搜索、网页抓取、Python 沙箱执行、JSON 查询、文本搜索、目录浏览、文件修补、环境变量、归档压缩、进程管理、HTTP 请求
- **LLM 统一网关**：通过 LiteLLM 支持 OpenAI / Anthropic / 本地模型，自动 fallback
- **Web 管理界面**：React + Ant Design 全功能管理平台，DAG 可视化、实时日志、YAML 在线编辑
- **WebSocket 实时推送**：工作流执行过程中的 tool 调用、Agent 消息实时推送到前端
- **Persona 系统**：每个 Agent 可配置独立的 soul / user / workflow 人格文件
- **插件工具系统**：通过配置文件动态加载自定义工具
- **定时调度**：Cron 表达式触发工作流自动执行

---

## 系统要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.11 | 推荐 3.12+ |
| Node.js | >= 18 | 前端构建需要，推荐 20 LTS |
| npm | >= 9 | 随 Node.js 安装 |
| Redis | >= 5.0 | **可选**，不装则自动降级为内存消息总线 |
| Git | >= 2.0 | 项目管理和 git_ops 工具需要 |

---

## 快速开始

### 一键安装

我们提供了自动化安装脚本，会完成环境检测、依赖安装、前端构建、配置初始化等所有步骤。

**macOS / Linux：**

```bash
git clone <your-repo-url> AxonFlow
cd AxonFlow
chmod +x setup.sh
./setup.sh
```

**Windows（PowerShell，以管理员身份运行）：**

```powershell
git clone <your-repo-url> AxonFlow
cd AxonFlow
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

安装完成后，按照脚本提示启动服务即可。

---

### 手动安装

如果你不想使用一键脚本，也可以手动完成每一步。

#### 第 1 步：安装 Python 后端

```bash
# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate     # macOS/Linux
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell

# 安装项目及所有依赖
pip install -e ".[dev]"
```

#### 第 2 步：配置 LLM API Key

AxonFlow 使用 OpenAI 兼容 API 格式。你需要设置环境变量：

```bash
# macOS/Linux — 添加到 ~/.bashrc 或 ~/.zshrc 以永久生效
export OPENAI_API_KEY="your-api-key-here"

# 如果使用自定义 API 端点（如本地模型、第三方兼容服务）：
export OPENAI_BASE_URL="https://your-api-endpoint/v1"
```

```powershell
# Windows PowerShell（仅当前会话）
$env:OPENAI_API_KEY = "your-api-key-here"
$env:OPENAI_BASE_URL = "https://your-api-endpoint/v1"

# 永久设置（系统级）
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-api-key-here", "User")
```

也可以在 `config/axonflow.yaml` 中修改 `default_model` 配置：

```yaml
default_model:
  provider: "openai"
  name: "gpt-4o"            # 模型名称
  temperature: 0.7
  max_tokens: 4096
  api_base: ""               # 留空则使用 OPENAI_BASE_URL 环境变量
  api_key_env: "OPENAI_API_KEY"  # 从哪个环境变量读取 API Key
  fallback_models:
    - "gpt-4o-mini"          # 主模型不可用时的备选
```

#### 第 3 步：安装前端

```bash
cd frontend
npm install
cd ..
```

#### 第 4 步：验证安装

```bash
# 运行后端测试
pytest tests/ -q

# 查看系统状态（CLI 模式）
axonflow status

# 构建前端（可选，生产部署用）
cd frontend && npm run build && cd ..
```

---

## 启动服务

AxonFlow 有两种使用方式：**CLI 模式**和 **Web 界面模式**。

### 方式一：CLI 命令行

适合快速执行单次工作流，无需启动 Web 服务。

```bash
# 查看已注册的 Agent 和工作流
axonflow status

# 执行工作流
axonflow run dev-pipeline --input "实现一个快速排序函数"

# 启动引擎守护进程（持续运行，支持定时任务）
axonflow start --daemon
```

### 方式二：Web 管理界面（推荐）

完整的图形化管理平台，支持实时监控、配置编辑、工作流可视化。

**需要同时启动后端 API 和前端 dev server：**

**终端 1 — 启动后端 API：**

```bash
# macOS/Linux
OPENAI_API_KEY="your-key" python -m uvicorn axonflow.api.app:app --port 8000 --reload

# Windows PowerShell
$env:OPENAI_API_KEY = "your-key"
python -m uvicorn axonflow.api.app:app --port 8000 --reload
```

**终端 2 — 启动前端 dev server：**

```bash
cd frontend
npm run dev
```

然后打开浏览器访问：**http://localhost:5173**

#### Web 界面功能一览

| 页面 | 路径 | 功能 |
|------|------|------|
| Dashboard | `/` | 系统状态总览，Agent 运行状态，工具列表，Token 用量 |
| Workflows | `/workflows` | 工作流列表，DAG 流程图可视化，YAML 在线编辑 |
| Workflow 执行 | `/workflows/:id/run/:runId` | 触发工作流，实时 WebSocket 事件日志 |
| Agents | `/agents` | Agent 列表，模型配置，工具配置查看 |
| Agent 详情 | `/agents/:id` | Agent YAML 编辑，Persona Markdown 编辑 |
| Logs | `/logs` | 执行日志查询，按 Agent/Action 过滤 |
| Settings | `/settings` | 全局配置 YAML 在线编辑（模型、Redis、日志级别等） |

### 生产部署（一体化）

构建前端后，后端可以直接 serve 前端静态文件，无需单独启动前端：

```bash
# 构建前端
cd frontend && npm run build && cd ..

# 启动后端（自动 serve frontend/dist/）
OPENAI_API_KEY="your-key" python -m uvicorn axonflow.api.app:app --port 8000

# 访问 http://localhost:8000 即可使用完整功能
```

---

## 配置说明

### 目录结构

```
config/
├── axonflow.yaml            # 全局配置（模型、Redis、日志、沙箱等）
├── agents/                  # Agent 配置
│   ├── coder/               # 目录模式（含 persona 文件）
│   │   ├── config.yaml      #   Agent 配置
│   │   ├── soul.md          #   价值观与行为准则
│   │   ├── user.md          #   用户画像
│   │   └── workflow.md      #   工作流程指南
│   ├── tester.yaml          # 单文件模式
│   └── publisher.yaml
└── workflows/               # 工作流配置
    ├── dev-pipeline.yaml    #   软件开发流水线
    ├── content-pipeline.yaml #  内容创作流水线
    └── supervised-dev-pipeline.yaml  # Supervisor 模式
```

### Agent 配置示例

```yaml
# config/agents/tester.yaml
id: agent-tester
name: "测试专员"
role: "你是一名资深测试工程师..."

model:
  provider: "openai"
  name: "gpt-4o"
  temperature: 0.2
  max_tokens: 4096

tools:
  - file_write
  - file_read
  - shell_exec
  - python_eval        # 新增：可用 Python 执行测试
  - text_search        # 新增：搜索代码内容

can_request:
  - agent-coder
  - agent-publisher

retry_limit: 3
```

### 工作流配置示例

```yaml
# config/workflows/dev-pipeline.yaml
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
    max_iterations: 10
    timeout: 3600

    routes:
      agent-coder:
        - target: agent-tester
      agent-tester:
        - target: agent-publisher
          condition: { field: status, operator: eq, value: success }
        - target: agent-coder
          condition: { field: status, operator: eq, value: error }

    terminate_on:
      - agent: agent-publisher
        status: success
```

---

## 内置工具列表

AxonFlow 内置 15 个工具，Agent 可在配置中按需引用：

| 工具名 | 功能 | 关键参数 |
|--------|------|---------|
| `shell_exec` | 执行 Shell 命令 | `command`, `timeout`, `cwd` |
| `file_read` | 读取文件内容 | `path` |
| `file_write` | 写入文件（自动创建目录） | `path`, `content` |
| `file_patch` | 文件局部修改（搜索替换/行范围） | `path`, `mode`, `search`, `replace` |
| `git_ops` | Git 操作（commit/push/pull 等） | `operation`, `cwd`, `args` |
| `http_request` | HTTP GET/POST 请求 | `url`, `method`, `headers`, `body` |
| `web_search` | DuckDuckGo 网络搜索 | `query`, `max_results` |
| `web_scrape` | 网页内容抓取（HTML 转纯文本） | `url`, `max_length` |
| `text_search` | 文件/目录内容搜索（正则） | `pattern`, `path`, `recursive` |
| `python_eval` | 沙箱 Python 代码执行 | `code`, `timeout` |
| `json_query` | JMESPath JSON 数据提取 | `data`, `expression` |
| `directory_tree` | 目录树结构显示 | `path`, `max_depth`, `show_size` |
| `env_vars` | 环境变量读取（敏感值脱敏） | `action`, `name`, `prefix` |
| `archive_ops` | tar.gz/zip 压缩解压 | `action`, `archive_path`, `source_paths` |
| `process_manager` | 后台进程管理 | `action`, `command`, `pid`, `name` |

---

## 项目结构

```
AxonFlow/
├── src/axonflow/              # Python 后端
│   ├── api/                   #   FastAPI REST API + WebSocket
│   │   ├── app.py             #     应用入口、lifespan 管理
│   │   ├── ws.py              #     WebSocket 事件广播器
│   │   ├── deps.py            #     依赖注入
│   │   └── routes/            #     API 路由
│   │       ├── system.py      #       系统状态
│   │       ├── workflows.py   #       工作流 CRUD + 执行
│   │       ├── agents.py      #       Agent CRUD + Persona
│   │       ├── logs.py        #       执行日志查询
│   │       └── config.py      #       全局配置管理
│   ├── core/                  #   核心运行时
│   │   ├── agent.py           #     Agent 基类 + 注册中心
│   │   ├── workflow.py        #     工作流编排器（Flat/Supervisor）
│   │   ├── message.py         #     消息协议
│   │   └── context.py         #     工作流上下文
│   ├── llm/                   #   LLM 统一网关
│   │   ├── gateway.py         #     多模型调用 + fallback
│   │   └── token_tracker.py   #     Token 用量追踪
│   ├── tools/                 #   工具系统（15 个内置工具）
│   ├── messaging/             #   消息总线（Redis / InMemory）
│   ├── config/                #   配置加载 + Pydantic 模型
│   ├── observability/         #   执行日志 + 结构化日志
│   ├── memory/                #   Agent 记忆存储
│   ├── cli/                   #   Typer CLI
│   └── engine.py              #   引擎主入口（模块组装）
├── frontend/                  # React 前端 SPA
│   ├── src/
│   │   ├── pages/             #   Dashboard, Workflows, Agents, Logs, Settings
│   │   ├── components/        #   StatusCard, LiveEventLog, YamlEditor
│   │   ├── layouts/           #   侧边栏布局
│   │   └── api/               #   fetch 封装 + WebSocket hook
│   ├── package.json
│   └── vite.config.ts         #   Vite 配置（proxy → 后端）
├── config/                    # 运行时配置
│   ├── axonflow.yaml          #   全局配置
│   ├── agents/                #   Agent 配置
│   └── workflows/             #   工作流配置
├── tests/                     # 测试（150+ 用例）
├── docs/                      # 文档
├── setup.sh                   # macOS/Linux 一键安装脚本
├── setup.ps1                  # Windows 一键安装脚本
└── pyproject.toml             # 项目元数据 + 依赖
```

---

## 开发

```bash
# 运行测试
pytest tests/ -q

# 运行测试 + 覆盖率
pytest tests/ --cov=axonflow --cov-report=html

# 代码格式检查
ruff check src/ tests/

# 类型检查
mypy src/axonflow/
```

---

## 常见问题

### Q: Redis 没装怎么办？

不影响使用。AxonFlow 检测到 Redis 不可用时会自动降级为内存消息总线（InMemory）。日志中会显示：
```
engine.redis_unavailable  fallback=in_memory
```

### Q: 支持哪些 LLM 模型？

通过 LiteLLM 支持所有 OpenAI 兼容 API，包括：
- OpenAI（GPT-4o, GPT-4o-mini 等）
- Anthropic（Claude 系列）
- 本地部署模型（Ollama, vLLM, LM Studio 等）
- 其他 OpenAI 兼容服务

在 `config/axonflow.yaml` 的 `default_model` 中配置即可。每个 Agent 也可以覆盖模型配置。

### Q: 如何添加自定义工具？

1. 创建 Python 类继承 `Tool` 基类
2. 在 `config/axonflow.yaml` 的 `plugins.tools` 中注册

```python
# my_tools/custom_tool.py
from axonflow.tools.base import Tool, ToolResult

class MyCustomTool(Tool):
    name = "my_tool"
    description = "我的自定义工具"
    parameters = {"type": "object", "properties": {...}, "required": [...]}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="done")
```

```yaml
# config/axonflow.yaml
plugins:
  tools:
    - class_path: "my_tools.custom_tool.MyCustomTool"
```

### Q: 前端报 API 连接错误？

确保后端 API 在 `localhost:8000` 运行。Vite dev server 通过 proxy 将 `/api` 和 `/ws` 请求转发到后端。如果后端端口不是 8000，需要修改 `frontend/vite.config.ts`。

---

## 文档

- [产品需求文档 (PRD)](docs/PRD.md)
- [技术实现方案](docs/TECHNICAL_DESIGN.md)
- [项目目录结构](docs/PROJECT_STRUCTURE.md)
- [前端设计规格](docs/superpowers/specs/2026-04-08-frontend-web-ui-design.md)

---

## License

Apache License 2.0
