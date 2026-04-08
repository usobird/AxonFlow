"""文件局部修改工具（搜索替换 / 行范围替换）"""

from __future__ import annotations

import difflib
from pathlib import Path

from axonflow.tools.base import Tool, ToolResult


def _make_diff(original: str, modified: str, path: str) -> str:
    """生成 unified diff 格式的变更摘要"""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, mod_lines, fromfile=path, tofile=path)
    return "".join(diff)


class FilePatchTool(Tool):
    """对文件进行局部修改，支持搜索替换和行范围替换两种模式"""

    name = "file_patch"
    description = (
        "对文件进行局部修改：支持 search_replace（搜索替换）和 line_range（行范围替换）两种模式"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要修改的文件路径",
            },
            "mode": {
                "type": "string",
                "enum": ["search_replace", "line_range"],
                "description": "修改模式：search_replace 或 line_range",
            },
            "search": {
                "type": "string",
                "description": "（search_replace 模式）要查找的文本",
            },
            "replace": {
                "type": "string",
                "description": "（search_replace 模式）替换后的文本",
            },
            "start_line": {
                "type": "integer",
                "description": "（line_range 模式）起始行号，从 1 开始",
            },
            "end_line": {
                "type": "integer",
                "description": "（line_range 模式）结束行号，从 1 开始，包含该行",
            },
            "content": {
                "type": "string",
                "description": "（line_range 模式）用于替换指定行范围的新内容",
            },
        },
        "required": ["path", "mode"],
    }

    async def execute(
        self,
        path: str,
        mode: str,
        search: str | None = None,
        replace: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        content: str | None = None,
        **_kwargs,
    ) -> ToolResult:
        file_path = Path(path)

        if not file_path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if not file_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")

        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read file: {e}")

        if mode == "search_replace":
            return await self._search_replace(file_path, original, search, replace)
        elif mode == "line_range":
            return await self._line_range(file_path, original, start_line, end_line, content)
        else:
            return ToolResult(success=False, error=f"Unknown mode: {mode}")

    async def _search_replace(
        self,
        file_path: Path,
        original: str,
        search: str | None,
        replace: str | None,
    ) -> ToolResult:
        if search is None:
            return ToolResult(
                success=False, error="Parameter 'search' is required for search_replace mode"
            )
        if replace is None:
            return ToolResult(
                success=False, error="Parameter 'replace' is required for search_replace mode"
            )

        if search not in original:
            return ToolResult(success=False, error=f"Search string not found in {file_path}")

        modified = original.replace(search, replace, 1)
        diff = _make_diff(original, modified, str(file_path))

        try:
            file_path.write_text(modified, encoding="utf-8")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {e}")

        return ToolResult(success=True, output=diff)

    async def _line_range(
        self,
        file_path: Path,
        original: str,
        start_line: int | None,
        end_line: int | None,
        content: str | None,
    ) -> ToolResult:
        if start_line is None:
            return ToolResult(
                success=False, error="Parameter 'start_line' is required for line_range mode"
            )
        if end_line is None:
            return ToolResult(
                success=False, error="Parameter 'end_line' is required for line_range mode"
            )
        if content is None:
            return ToolResult(
                success=False, error="Parameter 'content' is required for line_range mode"
            )

        lines = original.splitlines(keepends=True)
        total = len(lines)

        if start_line < 1 or end_line < 1:
            return ToolResult(success=False, error="Line numbers must be >= 1")
        if start_line > end_line:
            return ToolResult(
                success=False, error=f"start_line ({start_line}) > end_line ({end_line})"
            )
        if start_line > total:
            return ToolResult(
                success=False,
                error=f"start_line ({start_line}) exceeds file length ({total} lines)",
            )

        # Clamp end_line to file length
        end_line = min(end_line, total)

        # Build replacement content ensuring it ends with a newline if replacing mid-file
        replacement = content
        if not replacement.endswith("\n") and end_line < total:
            replacement += "\n"

        # Replace lines (convert to 0-indexed)
        new_lines = lines[: start_line - 1] + [replacement] + lines[end_line:]
        modified = "".join(new_lines)

        diff = _make_diff(original, modified, str(file_path))

        try:
            file_path.write_text(modified, encoding="utf-8")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {e}")

        return ToolResult(success=True, output=diff)
