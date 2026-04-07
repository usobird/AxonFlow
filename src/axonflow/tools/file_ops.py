"""文件读写工具"""

from __future__ import annotations

from pathlib import Path

from axonflow.tools.base import Tool, ToolResult


class FileReadTool(Tool):
    """读取文件内容"""

    name = "file_read"
    description = "读取指定文件的内容并返回"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
        },
        "required": ["path"],
    }

    async def execute(self, path: str, **_kwargs) -> ToolResult:
        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            if not file_path.is_file():
                return ToolResult(success=False, error=f"Not a file: {path}")
            content = file_path.read_text(encoding="utf-8")
            return ToolResult(success=True, output=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileWriteTool(Tool):
    """写入文件内容"""

    name = "file_write"
    description = "将内容写入指定文件，自动创建父目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件路径",
            },
            "content": {
                "type": "string",
                "description": "要写入的内容",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **_kwargs) -> ToolResult:
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"File written: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
