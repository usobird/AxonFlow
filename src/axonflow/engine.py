"""AxonFlow 引擎主入口 — 组装所有模块并启动系统"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import structlog

from axonflow.config.loader import (
    load_all_agent_configs,
    load_all_workflow_configs,
    load_global_config,
)
from axonflow.config.models import AxonFlowConfig
from axonflow.core.agent import AgentRegistry, create_agent
from axonflow.memory.local import InMemoryStore
from axonflow.core.scheduler import Scheduler
from axonflow.core.orchestrator_factory import create_orchestrator
from axonflow.core.workflow import WorkflowResult
from axonflow.llm.gateway import LLMGateway
from axonflow.messaging.base import MessageBus
from axonflow.messaging.memory_bus import InMemoryMessageBus
from axonflow.observability.execution_log import ExecutionLogger
from axonflow.observability.logger import setup_logging
from axonflow.tools.base import Tool, ToolRegistry
from axonflow.tools.file_ops import FileReadTool, FileWriteTool
from axonflow.tools.git_ops import GitOpsTool
from axonflow.tools.http_request import HttpRequestTool
from axonflow.tools.shell_exec import ShellExecTool

logger = structlog.get_logger()


class AxonFlowEngine:
    """AxonFlow 引擎

    职责:
    1. 加载配置
    2. 初始化各模块（消息总线、LLM 网关、工具注册中心、Agent 注册中心）
    3. 启动所有 Agent 的消息监听
    4. 提供工作流执行入口
    5. 管理生命周期
    """

    def __init__(
        self,
        config_dir: str = "config",
        config: AxonFlowConfig | None = None,
    ) -> None:
        self._config_dir = Path(config_dir)
        self._config = config
        self._message_bus: MessageBus | None = None
        self._llm_gateway: LLMGateway | None = None
        self._tool_registry: ToolRegistry | None = None
        self._agent_registry: AgentRegistry | None = None
        self._scheduler: Scheduler | None = None
        self._memory_store: InMemoryStore | None = None
        self._execution_logger: ExecutionLogger | None = None
        self._agent_tasks: list[asyncio.Task] = []
        self._running = False
        self._initialized = False

    @property
    def config(self) -> AxonFlowConfig:
        if self._config is None:
            raise RuntimeError("Engine not initialized. Call initialize() first.")
        return self._config

    @property
    def agent_registry(self) -> AgentRegistry:
        if self._agent_registry is None:
            raise RuntimeError("Engine not initialized.")
        return self._agent_registry

    @property
    def message_bus(self) -> MessageBus:
        if self._message_bus is None:
            raise RuntimeError("Engine not initialized.")
        return self._message_bus

    async def initialize(self) -> None:
        """初始化引擎 — 加载配置并组装模块"""
        if self._initialized:
            return

        # 1. 加载全局配置
        if self._config is None:
            global_config_path = self._config_dir / "axonflow.yaml"
            self._config = load_global_config(global_config_path)

        # 2. 配置日志
        setup_logging(
            level=self.config.log_level,
            fmt=self.config.log_format,
        )

        logger.info("engine.initializing")

        # 3. 初始化消息总线
        self._message_bus = await self._create_message_bus()

        # 4. 初始化 LLM 网关
        self._llm_gateway = LLMGateway(
            default_model=self.config.default_model,
            token_budget=self.config.token_budget,
        )

        # 5. 注册内置工具
        self._tool_registry = ToolRegistry()
        self._register_builtin_tools()

        # 5.1 加载外部工具插件
        self._load_plugin_tools()

        # 5.5 初始化共享记忆存储
        self._memory_store = InMemoryStore()

        # 5.6 初始化执行日志
        self._execution_logger = ExecutionLogger(
            workspace_dir=self.config.workspace_dir,
        )

        # 6. 加载并注册 Agent
        self._agent_registry = AgentRegistry()
        await self._load_agents()

        # 7. 初始化调度器
        self._scheduler = Scheduler()
        self._scheduler.set_run_callback(self._scheduled_run)
        self._load_cron_jobs()

        self._initialized = True
        logger.info("engine.initialized")

    async def _create_message_bus(self) -> MessageBus:
        """创建消息总线（尝试 Redis，失败则降级到内存）"""
        try:
            from axonflow.messaging.redis_bus import RedisMessageBus
            import redis.asyncio as aioredis

            bus = RedisMessageBus(self.config.redis.url)
            await bus.start()
            # 实际检测 Redis 连通性
            r = aioredis.from_url(self.config.redis.url)
            await r.ping()
            await r.aclose()
            logger.info("engine.message_bus", type="redis")
            return bus
        except Exception as e:
            logger.warning(
                "engine.redis_unavailable",
                error=str(e),
                fallback="in_memory",
            )
            bus = InMemoryMessageBus()
            logger.info("engine.message_bus", type="in_memory")
            return bus

    def _register_builtin_tools(self) -> None:
        """注册内置工具"""
        assert self._tool_registry is not None
        self._tool_registry.register(ShellExecTool())
        self._tool_registry.register(FileReadTool())
        self._tool_registry.register(FileWriteTool())
        self._tool_registry.register(GitOpsTool())
        self._tool_registry.register(HttpRequestTool())

    def _load_plugin_tools(self) -> None:
        """加载外部工具插件"""
        assert self._tool_registry is not None

        for plugin_cfg in self.config.plugins.tools:
            try:
                module_path, class_name = plugin_cfg.class_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                tool_cls = getattr(module, class_name)

                if not (isinstance(tool_cls, type) and issubclass(tool_cls, Tool)):
                    logger.warning(
                        "engine.plugin_tool_invalid",
                        class_path=plugin_cfg.class_path,
                        error="Not a subclass of Tool",
                    )
                    continue

                # Instantiate — pass config if tool accepts it
                try:
                    tool = tool_cls(**plugin_cfg.config)
                except TypeError:
                    tool = tool_cls()

                self._tool_registry.register(tool)
                logger.info(
                    "engine.plugin_tool_loaded",
                    class_path=plugin_cfg.class_path,
                    tool_name=tool.name,
                )
            except Exception as e:
                logger.error(
                    "engine.plugin_tool_failed",
                    class_path=plugin_cfg.class_path,
                    error=str(e),
                )

    async def _load_agents(self) -> None:
        """从配置目录加载所有 Agent"""
        assert self._agent_registry is not None
        assert self._message_bus is not None
        assert self._llm_gateway is not None
        assert self._tool_registry is not None

        agents_dir = self._config_dir / "agents"
        skills_dir = self._config_dir / "skills"
        agent_configs = load_all_agent_configs(agents_dir)

        for cfg in agent_configs:
            agent = create_agent(
                config=cfg,
                message_bus=self._message_bus,
                llm_gateway=self._llm_gateway,
                tool_registry=self._tool_registry,
                memory_store=self._memory_store,
                execution_logger=self._execution_logger,
                skills_dir=skills_dir,
            )
            self._agent_registry.register(agent)

        logger.info(
            "engine.agents_loaded",
            count=len(agent_configs),
        )

    def _load_cron_jobs(self) -> None:
        """从工作流配置中加载 Cron 任务"""
        assert self._scheduler is not None
        workflows_dir = self._config_dir / "workflows"
        workflow_configs = load_all_workflow_configs(workflows_dir)

        for wf in workflow_configs:
            if wf.trigger.type == "cron" and wf.trigger.cron:
                self._scheduler.add_job(
                    workflow_id=wf.id,
                    cron_expr=wf.trigger.cron,
                )

    async def start(self) -> None:
        """启动引擎 — 启动所有 Agent 和调度器"""
        if not self._initialized:
            await self.initialize()

        self._running = True
        logger.info("engine.starting")

        # 启动所有 Agent 的消息监听
        assert self._agent_registry is not None
        for agent in self._agent_registry.list_agents():
            task = asyncio.create_task(agent.start())
            self._agent_tasks.append(task)

        # 启动调度器
        assert self._scheduler is not None
        scheduler_task = asyncio.create_task(self._scheduler.start())
        self._agent_tasks.append(scheduler_task)

        logger.info(
            "engine.started",
            agents=len(self._agent_registry.list_agents()),
        )

    async def stop(self) -> None:
        """停止引擎"""
        self._running = False
        logger.info("engine.stopping")

        # 停止所有 Agent
        if self._agent_registry:
            for agent in self._agent_registry.list_agents():
                await agent.stop()

        # 停止调度器
        if self._scheduler:
            await self._scheduler.stop()

        # 取消所有异步任务
        for task in self._agent_tasks:
            task.cancel()
        if self._agent_tasks:
            await asyncio.gather(*self._agent_tasks, return_exceptions=True)
        self._agent_tasks.clear()

        # 关闭消息总线
        if self._message_bus:
            await self._message_bus.stop()

        logger.info("engine.stopped")

    async def run_workflow(self, workflow_id: str, input_data: str) -> WorkflowResult:
        """执行指定工作流"""
        workflows_dir = self._config_dir / "workflows"
        workflow_configs = load_all_workflow_configs(workflows_dir)

        wf_config = None
        for wf in workflow_configs:
            if wf.id == workflow_id:
                wf_config = wf
                break

        if wf_config is None:
            raise ValueError(f"Workflow not found: {workflow_id}")

        assert self._agent_registry is not None
        assert self._message_bus is not None

        orchestrator = create_orchestrator(
            config=wf_config,
            agent_registry=self._agent_registry,
            message_bus=self._message_bus,
            llm_gateway=self._llm_gateway,
        )

        return await orchestrator.execute(input_data)

    async def _scheduled_run(self, workflow_id: str, input_data: str) -> None:
        """调度器回调 — 执行工作流"""
        try:
            result = await self.run_workflow(workflow_id, input_data)
            logger.info(
                "engine.scheduled_workflow_completed",
                workflow_id=workflow_id,
                status=result.status,
            )
        except Exception as e:
            logger.error(
                "engine.scheduled_workflow_failed",
                workflow_id=workflow_id,
                error=str(e),
            )

    def status(self) -> dict:
        """获取系统状态"""
        return {
            "running": self._running,
            "agents": (self._agent_registry.get_states() if self._agent_registry else {}),
            "tools": (self._tool_registry.list_tools() if self._tool_registry else []),
            "token_usage": (self._llm_gateway.token_tracker.summary() if self._llm_gateway else {}),
        }
