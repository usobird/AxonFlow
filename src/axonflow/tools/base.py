"""工具基类与工具注册中心"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    output: str | None = None
    error: str | None = None


class Tool(ABC):
    """工具抽象基类

    所有工具必须实现:
    - name: 工具名称（唯一标识）
    - description: 工具描述（供 LLM 理解用途）
    - parameters: JSON Schema 格式的参数定义
    - execute(): 异步执行方法
    """

    name: str
    description: str
    parameters: dict

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        ...

    def to_schema(self) -> dict:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册中心"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        logger.info("tool.registered", name=tool.name)

    def get(self, name: str) -> Tool | None:
        """获取工具实例"""
        return self._tools.get(name)

    def get_schemas(self, tool_names: list[str]) -> list[dict]:
        """批量获取工具的 JSON Schema"""
        schemas = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool:
                schemas.append(tool.to_schema())
        return schemas

    def list_tools(self) -> list[str]:
        """列出所有已注册工具名称"""
        return list(self._tools.keys())

    async def execute(self, tool_name: str, arguments: dict | None = None) -> ToolResult:
        """根据工具名称调度执行

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典，会解包为 **kwargs 传给 tool.execute()
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}. Available: {', '.join(self._tools.keys())}",
            )
        try:
            args = arguments or {}
            logger.info("tool.executing", name=tool_name, args=args)
            result = await tool.execute(**args)
            logger.info("tool.completed", name=tool_name, success=result.success)
            return result
        except Exception as e:
            logger.error("tool.failed", name=tool_name, error=str(e))
            return ToolResult(success=False, error=f"Tool execution failed: {e}")
