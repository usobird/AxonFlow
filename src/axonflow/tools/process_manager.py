"""后台进程管理工具"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from datetime import datetime, timezone

from axonflow.tools.base import Tool, ToolResult

# 模块级进程注册表：pid -> 进程元信息
_managed_processes: dict[int, dict] = {}


def _is_alive(pid: int) -> bool:
    """通过 signal 0 检查进程是否存活"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但无权限发信号——仍视为存活
        return True
    return True


class ProcessManagerTool(Tool):
    """启动、停止和列举后台进程"""

    name = "process_manager"
    description = "管理后台进程：启动、停止、列举、查询状态"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "list", "status"],
                "description": "操作类型",
            },
            "command": {
                "type": "string",
                "description": "要执行的命令（start 时使用）",
            },
            "pid": {
                "type": "integer",
                "description": "目标进程 PID（stop/status 时使用）",
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（start 时使用）",
            },
            "name": {
                "type": "string",
                "description": "进程的可读标签（start 时使用）",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self,
        action: str,
        command: str | None = None,
        pid: int | None = None,
        cwd: str | None = None,
        name: str | None = None,
        **_kwargs,
    ) -> ToolResult:
        if action == "start":
            return await self._start(command, cwd, name)
        if action == "stop":
            return await self._stop(pid)
        if action == "list":
            return self._list()
        if action == "status":
            return self._status(pid)
        return ToolResult(success=False, error=f"Unknown action: {action}")

    # ------------------------------------------------------------------
    # start
    # ------------------------------------------------------------------

    @staticmethod
    async def _start(command: str | None, cwd: str | None, name: str | None) -> ToolResult:
        if not command:
            return ToolResult(
                success=False, error="Parameter 'command' is required for action 'start'"
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to start process: {e}")

        label = name or command
        _managed_processes[proc.pid] = {
            "pid": proc.pid,
            "name": label,
            "command": command,
            "cwd": cwd,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        return ToolResult(
            success=True,
            output=json.dumps({"pid": proc.pid, "name": label}),
        )

    # ------------------------------------------------------------------
    # stop
    # ------------------------------------------------------------------

    @staticmethod
    async def _stop(pid: int | None) -> ToolResult:
        if pid is None:
            return ToolResult(success=False, error="Parameter 'pid' is required for action 'stop'")

        if pid not in _managed_processes:
            return ToolResult(success=False, error=f"PID {pid} is not managed by this tool")

        # SIGTERM -> 等待 5 秒 -> SIGKILL
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            _managed_processes.pop(pid, None)
            return ToolResult(success=True, output=f"Process {pid} already exited")

        # 给进程 5 秒优雅退出的时间
        for _ in range(50):
            await asyncio.sleep(0.1)
            if not _is_alive(pid):
                break
        else:
            # 仍然存活，强制终止
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        _managed_processes.pop(pid, None)
        return ToolResult(success=True, output=f"Process {pid} stopped")

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    @staticmethod
    def _list() -> ToolResult:
        entries = []
        for info in _managed_processes.values():
            entries.append(
                {
                    **info,
                    "status": "running" if _is_alive(info["pid"]) else "stopped",
                }
            )
        return ToolResult(success=True, output=json.dumps(entries))

    # ------------------------------------------------------------------
    # status
    # ------------------------------------------------------------------

    @staticmethod
    def _status(pid: int | None) -> ToolResult:
        if pid is None:
            return ToolResult(
                success=False, error="Parameter 'pid' is required for action 'status'"
            )

        info = _managed_processes.get(pid)
        if info is None:
            return ToolResult(success=False, error=f"PID {pid} is not managed by this tool")

        result = {
            **info,
            "status": "running" if _is_alive(pid) else "stopped",
        }
        return ToolResult(success=True, output=json.dumps(result))
