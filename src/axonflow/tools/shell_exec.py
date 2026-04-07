"""Shell 命令执行工具"""

from __future__ import annotations

import asyncio

from axonflow.tools.base import Tool, ToolResult


class ShellExecTool(Tool):
    """执行 Shell 命令并返回输出"""

    name = "shell_exec"
    description = "执行 Shell 命令并返回标准输出和标准错误"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 30",
                "default": 30,
            },
            "cwd": {
                "type": "string",
                "description": "工作目录（可选）",
            },
        },
        "required": ["command"],
    }

    async def execute(
        self,
        command: str,
        timeout: int = 30,
        cwd: str | None = None,
        **_kwargs,
    ) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode == 0:
                return ToolResult(success=True, output=stdout_str)
            else:
                return ToolResult(
                    success=False,
                    output=stdout_str,
                    error=f"Exit code {proc.returncode}: {stderr_str}",
                )
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
