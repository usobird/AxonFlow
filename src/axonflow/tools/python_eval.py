"""沙箱化 Python 代码执行工具"""

from __future__ import annotations

import asyncio

from axonflow.tools.base import Tool, ToolResult

_MAX_OUTPUT_CHARS = 10000


class PythonEvalTool(Tool):
    """在子进程中执行 Python 代码并返回输出"""

    name = "python_eval"
    description = "在隔离的子进程中执行 Python 代码，返回标准输出和错误信息"
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 10",
                "default": 10,
            },
        },
        "required": ["code"],
    }

    async def execute(
        self,
        code: str,
        timeout: int = 10,
        **_kwargs,
    ) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3",
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            # Truncate output to prevent memory explosion
            stdout_str = stdout_str[:_MAX_OUTPUT_CHARS]
            stderr_str = stderr_str[:_MAX_OUTPUT_CHARS]

            if proc.returncode == 0:
                return ToolResult(
                    success=True,
                    output=stdout_str,
                    error=stderr_str if stderr_str else None,
                )
            else:
                return ToolResult(
                    success=False,
                    output=stdout_str if stdout_str else None,
                    error=f"Exit code {proc.returncode}: {stderr_str}",
                )
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            return ToolResult(
                success=False,
                error=f"Code execution timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
