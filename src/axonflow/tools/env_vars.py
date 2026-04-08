"""环境变量读取工具"""

from __future__ import annotations

import fnmatch
import os

from axonflow.tools.base import Tool, ToolResult

# 敏感变量名匹配模式（大小写不敏感）
_SENSITIVE_PATTERNS = ["*SECRET*", "*PASSWORD*", "*TOKEN*", "*KEY*"]

# 显式允许访问的变量名（即使匹配敏感模式也放行）
ALLOWLIST: set[str] = set()


def _is_sensitive(name: str) -> bool:
    """检查变量名是否匹配敏感模式且不在允许列表中"""
    if name in ALLOWLIST:
        return False
    upper = name.upper()
    return any(fnmatch.fnmatch(upper, pattern) for pattern in _SENSITIVE_PATTERNS)


class EnvVarsTool(Tool):
    """读取和列举环境变量"""

    name = "env_vars"
    description = "读取或列举环境变量。get 返回指定变量的值，list 列出变量名（不含值）"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "list"],
                "description": "操作类型：get 获取单个变量值，list 列出所有变量名",
            },
            "name": {
                "type": "string",
                "description": "环境变量名称（action 为 get 时使用）",
            },
            "prefix": {
                "type": "string",
                "description": "按前缀过滤变量名（action 为 list 时使用）",
            },
        },
        "required": ["action"],
    }

    async def execute(
        self, action: str, name: str | None = None, prefix: str | None = None, **_kwargs
    ) -> ToolResult:
        if action == "get":
            return self._get(name)
        if action == "list":
            return self._list(prefix)
        return ToolResult(success=False, error=f"Unknown action: {action}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get(name: str | None) -> ToolResult:
        if not name:
            return ToolResult(success=False, error="Parameter 'name' is required for action 'get'")

        value = os.environ.get(name)
        if value is None:
            return ToolResult(success=False, error=f"Environment variable not found: {name}")

        if _is_sensitive(name):
            return ToolResult(success=True, output="[REDACTED]")

        return ToolResult(success=True, output=value)

    @staticmethod
    def _list(prefix: str | None) -> ToolResult:
        names = sorted(os.environ.keys())
        if prefix:
            names = [n for n in names if n.startswith(prefix)]
        return ToolResult(success=True, output="\n".join(names))
