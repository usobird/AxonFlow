"""Git 操作工具"""

from __future__ import annotations

import asyncio

from axonflow.tools.base import Tool, ToolResult


class GitOpsTool(Tool):
    """执行 Git 操作"""

    name = "git_ops"
    description = "执行 Git 命令，支持 commit、push、pull、branch、status 等操作"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Git 操作: status / add / commit / push / pull / branch / checkout / log",
                "enum": ["status", "add", "commit", "push", "pull", "branch", "checkout", "log"],
            },
            "args": {
                "type": "string",
                "description": "操作参数，如 commit 的 message、branch 的名称等",
                "default": "",
            },
            "cwd": {
                "type": "string",
                "description": "Git 仓库工作目录",
            },
        },
        "required": ["operation", "cwd"],
    }

    _OPERATION_MAP = {
        "status": "git status",
        "add": "git add {args}",
        "commit": 'git commit -m "{args}"',
        "push": "git push {args}",
        "pull": "git pull {args}",
        "branch": "git branch {args}",
        "checkout": "git checkout {args}",
        "log": "git log --oneline -20 {args}",
    }

    async def execute(
        self,
        operation: str,
        cwd: str,
        args: str = "",
        **_kwargs,
    ) -> ToolResult:
        template = self._OPERATION_MAP.get(operation)
        if template is None:
            return ToolResult(
                success=False,
                error=f"Unknown git operation: {operation}",
            )

        command = template.format(args=args).strip()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode == 0:
                return ToolResult(success=True, output=stdout_str or stderr_str)
            else:
                return ToolResult(
                    success=False,
                    output=stdout_str,
                    error=stderr_str,
                )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Git command timed out")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
