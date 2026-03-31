# AutoFlow 项目目录结构

```
autoflow/
├── docs/                          # 项目文档
│   ├── PRD.md                     # 产品需求文档
│   ├── TECHNICAL_DESIGN.md        # 技术实现方案
│   └── PROJECT_STRUCTURE.md       # 本文件
│
├── src/
│   └── autoflow/                  # 主包
│       ├── __init__.py
│       ├── __main__.py            # python -m autoflow 入口
│       │
│       ├── core/                  # 核心模块
│       │   ├── __init__.py
│       │   ├── agent.py           # BaseAgent 基类 & AgentRegistry
│       │   ├── message.py         # Message / MessageType 数据模型
│       │   ├── workflow.py        # WorkflowOrchestrator 工作流引擎
│       │   ├── context.py         # WorkflowContext 上下文管理
│       │   └── scheduler.py       # Cron 调度器
│       │
│       ├── messaging/             # 消息系统
│       │   ├── __init__.py
│       │   ├── base.py            # MessageBus 抽象接口
│       │   ├── redis_bus.py       # Redis Streams 实现
│       │   └── memory_bus.py      # 进程内 asyncio.Queue 实现
│       │
│       ├── llm/                   # LLM 集成
│       │   ├── __init__.py
│       │   ├── gateway.py         # LLMGateway 统一调用入口
│       │   ├── token_tracker.py   # Token 用量追踪
│       │   └── prompt_builder.py  # Prompt 构建器
│       │
│       ├── tools/                 # 工具系统
│       │   ├── __init__.py
│       │   ├── base.py            # Tool 基类 & ToolRegistry
│       │   ├── shell_exec.py      # Shell 命令执行
│       │   ├── file_ops.py        # 文件读写操作
│       │   ├── git_ops.py         # Git 操作
│       │   ├── http_request.py    # HTTP 请求
│       │   └── docker_ops.py      # Docker 操作
│       │
│       ├── agents/                # 预置智能体实现
│       │   ├── __init__.py
│       │   ├── coder.py           # 编码专员
│       │   ├── tester.py          # 测试专员
│       │   └── publisher.py       # 发布专员
│       │
│       ├── config/                # 配置管理
│       │   ├── __init__.py
│       │   ├── models.py          # Pydantic 配置模型
│       │   ├── loader.py          # YAML 配置加载器
│       │   └── defaults.py        # 默认配置值
│       │
│       ├── observability/         # 可观测性
│       │   ├── __init__.py
│       │   ├── logger.py          # structlog 配置
│       │   ├── metrics.py         # 指标采集
│       │   ├── tracer.py          # 执行轨迹追踪
│       │   └── webhook.py         # Webhook 通知
│       │
│       ├── security/              # 安全模块
│       │   ├── __init__.py
│       │   ├── sandbox.py         # 沙箱执行器
│       │   └── secrets.py         # 密钥管理
│       │
│       ├── cli/                   # CLI 命令
│       │   ├── __init__.py
│       │   ├── app.py             # Typer CLI 主应用
│       │   ├── commands/
│       │   │   ├── __init__.py
│       │   │   ├── start.py       # autoflow start
│       │   │   ├── run.py         # autoflow run
│       │   │   ├── status.py      # autoflow status
│       │   │   ├── stop.py        # autoflow stop
│       │   │   ├── logs.py        # autoflow logs
│       │   │   ├── history.py     # autoflow history
│       │   │   └── agent.py       # autoflow agent *
│       │   └── utils.py           # CLI 工具函数
│       │
│       └── engine.py              # AutoFlow 引擎主入口
│
├── config/                        # 用户配置目录
│   ├── autoflow.yaml              # 全局配置
│   ├── agents/                    # 智能体配置
│   │   ├── coder.yaml
│   │   ├── tester.yaml
│   │   └── publisher.yaml
│   └── workflows/                 # 工作流配置
│       └── dev-pipeline.yaml
│
├── templates/                     # 配置模板
│   ├── agents/
│   │   ├── coder.yaml.template
│   │   ├── tester.yaml.template
│   │   └── publisher.yaml.template
│   └── workflows/
│       └── dev-pipeline.yaml.template
│
├── plugins/                       # 第三方插件目录
│   └── README.md
│
├── tests/                         # 测试
│   ├── __init__.py
│   ├── conftest.py                # pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_agent.py
│   │   ├── test_message.py
│   │   ├── test_workflow.py
│   │   ├── test_tools.py
│   │   └── test_llm_gateway.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_message_bus.py
│   │   └── test_workflow_execution.py
│   └── e2e/
│       ├── __init__.py
│       └── test_dev_pipeline.py
│
├── workspace/                     # Agent 工作目录（运行时生成）
│   └── .gitkeep
│
├── logs/                          # 日志输出目录
│   └── .gitkeep
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── pyproject.toml                 # 项目元数据 & 依赖
├── LICENSE                        # Apache 2.0
├── README.md                      # 项目说明
├── Makefile                       # 常用命令快捷方式
└── .gitignore
```

## 模块依赖关系

```
cli/
 └── engine.py
      ├── core/
      │    ├── agent.py ─────── llm/gateway.py
      │    │                     tools/base.py
      │    ├── workflow.py ──── messaging/base.py
      │    ├── context.py
      │    └── scheduler.py ─── workflow.py
      │
      ├── messaging/
      │    ├── redis_bus.py
      │    └── memory_bus.py
      │
      ├── config/
      │    ├── models.py
      │    └── loader.py
      │
      ├── observability/
      │    ├── logger.py
      │    ├── metrics.py
      │    └── webhook.py
      │
      └── security/
           ├── sandbox.py
           └── secrets.py
```

## 关键依赖包

```toml
[project]
name = "autoflow"
version = "0.1.0"
requires-python = ">=3.11"

[project.dependencies]
# 核心
asyncio-extras = ">=1.3"
pydantic = ">=2.0"
pyyaml = ">=6.0"

# LLM
litellm = ">=1.0"

# 消息队列
redis = {version = ">=5.0", extras = ["hiredis"]}

# CLI
typer = ">=0.9"
rich = ">=13.0"

# 日志
structlog = ">=24.0"

# HTTP
aiohttp = ">=3.9"

# 调度
croniter = ">=2.0"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.scripts]
autoflow = "autoflow.cli.app:main"
```
