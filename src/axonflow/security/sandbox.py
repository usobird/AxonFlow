"""沙箱执行器 — 对工具执行施加安全限制"""

from __future__ import annotations

import structlog

from axonflow.config.models import SandboxConfig
from axonflow.tools.base import Tool, ToolResult

logger = structlog.get_logger()


class SandboxExecutor:
    """沙箱化工具执行器

    对 Shell 命令和文件操作施加白名单/黑名单限制。
    """

    def __init__(self, config: SandboxConfig) -> None:
        self.enabled = config.enabled
        self.allowed_commands = set(config.command_whitelist)
        self.blocked_paths = [p.rstrip("/") for p in config.blocked_paths]

    async def execute(self, tool: Tool, **kwargs) -> ToolResult:
        """在沙箱策略下执行工具"""
        if not self.enabled:
            return await tool.execute(**kwargs)

        # Shell 命令白名单检查
        if tool.name == "shell_exec":
            command = kwargs.get("command", "")
            base_cmd = command.split()[0] if command.strip() else ""
            if self.allowed_commands and base_cmd not in self.allowed_commands:
                logger.warning(
                    "sandbox.blocked_command",
                    command=command,
                    base_cmd=base_cmd,
                )
                return ToolResult(
                    success=False,
                    error=f"Command blocked by sandbox policy: {base_cmd}",
                )

        # 文件路径检查
        path = kwargs.get("path", "")
        if path and self._is_blocked_path(path):
            logger.warning("sandbox.blocked_path", path=path)
            return ToolResult(
                success=False,
                error=f"Path blocked by sandbox policy: {path}",
            )

        return await tool.execute(**kwargs)

    def _is_blocked_path(self, path: str) -> bool:
        """检查路径是否被阻止"""
        for blocked in self.blocked_paths:
            if path.startswith(blocked):
                return True
        return False
