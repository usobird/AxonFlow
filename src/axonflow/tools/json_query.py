"""JSON 结构化数据查询工具（基于 JMESPath）"""

from __future__ import annotations

import json

from axonflow.tools.base import Tool, ToolResult

try:
    import jmespath

    _HAS_JMESPATH = True
except ImportError:
    _HAS_JMESPATH = False


class JsonQueryTool(Tool):
    """使用 JMESPath 表达式查询 JSON 数据"""

    name = "json_query"
    description = "解析 JSON 字符串并使用 JMESPath 表达式提取数据"
    parameters = {
        "type": "object",
        "properties": {
            "data": {
                "type": "string",
                "description": "要查询的 JSON 字符串",
            },
            "expression": {
                "type": "string",
                "description": "JMESPath 查询表达式",
            },
        },
        "required": ["data", "expression"],
    }

    async def execute(
        self,
        data: str,
        expression: str,
        **_kwargs,
    ) -> ToolResult:
        if not _HAS_JMESPATH:
            return ToolResult(
                success=False,
                error="jmespath library is not installed. Run: pip install jmespath",
            )

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            return ToolResult(success=False, error=f"Invalid JSON data: {e}")

        try:
            result = jmespath.search(expression, parsed)
        except jmespath.exceptions.JMESPathError as e:
            return ToolResult(success=False, error=f"Invalid JMESPath expression: {e}")

        try:
            output = json.dumps(result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as e:
            return ToolResult(success=False, error=f"Failed to serialize result: {e}")

        return ToolResult(success=True, output=output)
