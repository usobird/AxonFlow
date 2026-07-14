"""FastAPI 应用入口"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from axonflow.api.deps import set_config_dir, set_engine, set_platform_store
from axonflow.api.routes import (
    agents,
    config,
    credentials,
    logs,
    model_profiles,
    observability,
    system,
    workflows,
)
from axonflow.api.ws import broadcaster
from axonflow.config.loader import load_global_config
from axonflow.engine import AxonFlowEngine
from axonflow.observability.execution_log import ExecutionLogEntry
from axonflow.platform.store import PlatformStore

logger = structlog.get_logger()


def _make_log_callback(loop: asyncio.AbstractEventLoop):
    """创建一个将 ExecutionLogEntry 转发到 WebSocket broadcaster 的回调"""

    def _on_log(entry: ExecutionLogEntry, run_id: str | None) -> None:
        if run_id is None:
            return
        event = {
            "type": f"execution.{entry.action}",
            "workflow_id": entry.workflow_id,
            "run_id": run_id,
            "timestamp": entry.timestamp,
            "data": {
                "agent_id": entry.agent_id,
                "action": entry.action,
                "tool_name": entry.tool_name,
                "arguments": entry.arguments,
                "result": entry.result,
                "error": entry.error,
                "round": entry.round,
            },
        }
        asyncio.run_coroutine_threadsafe(broadcaster.broadcast(run_id, event), loop)

    return _on_log


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 启动/关闭 AxonFlowEngine"""
    config_dir = Path(app.state.config_dir) if hasattr(app.state, "config_dir") else Path("config")
    set_config_dir(config_dir)

    config = load_global_config(config_dir / "axonflow.yaml")
    workspace_dir = Path(config.workspace_dir)
    if not workspace_dir.is_absolute():
        workspace_dir = config_dir.parent / workspace_dir
    platform_store = PlatformStore(workspace_dir / "axonflow.db")
    set_platform_store(platform_store)

    engine = AxonFlowEngine(
        config_dir=str(config_dir),
        config=config,
        platform_store=platform_store,
    )
    await engine.initialize()
    await engine.start()
    set_engine(engine)

    # Wire ExecutionLogger -> WebSocket broadcaster
    if engine._execution_logger is not None:
        loop = asyncio.get_running_loop()
        log_callback = _make_log_callback(loop)
        engine._execution_logger.add_callback(log_callback)

    logger.info("api.started", config_dir=str(config_dir))
    yield

    await engine.stop()
    platform_store.close()
    logger.info("api.stopped")


def create_app(config_dir: str = "config") -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="AxonFlow API",
        description="AxonFlow Multi-Agent Workflow Engine API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.config_dir = config_dir

    # CORS — 开发模式允许前端 dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(system.router)
    app.include_router(workflows.router)
    app.include_router(agents.router)
    app.include_router(logs.router)
    app.include_router(config.router)
    app.include_router(credentials.router)
    app.include_router(model_profiles.router)
    app.include_router(observability.router)

    # WebSocket 端点
    @app.websocket("/ws/events")
    async def websocket_events(ws: WebSocket, run_id: str | None = None):
        await broadcaster.connect(ws, run_id)
        try:
            while True:
                # Keep connection alive, receive pings
                await ws.receive_text()
        except WebSocketDisconnect:
            broadcaster.disconnect(ws, run_id)

    # 尝试挂载前端静态文件（生产模式）
    frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


# Default app instance for uvicorn
app = create_app()
