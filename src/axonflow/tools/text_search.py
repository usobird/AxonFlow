"""File content search tool (grep-like)."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

import structlog

from axonflow.tools.base import Tool, ToolResult

logger = structlog.get_logger()

_MAX_FILE_SIZE = 1_048_576  # 1 MB


def _is_binary(path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 1024 bytes."""
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
        return b"\x00" in chunk
    except OSError:
        return True


def _search_file(
    path: Path,
    pattern: re.Pattern[str],
    max_results: int,
    results: list[dict],
) -> None:
    """Search a single file for pattern matches, appending to *results*."""
    if path.stat().st_size > _MAX_FILE_SIZE:
        return
    if _is_binary(path):
        return

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    for lineno, line in enumerate(text.splitlines(), start=1):
        if len(results) >= max_results:
            return
        m = pattern.search(line)
        if m:
            results.append(
                {
                    "file": str(path),
                    "line_number": lineno,
                    "line_content": line.rstrip(),
                    "match": m.group(),
                }
            )


class TextSearchTool(Tool):
    """在文件内容中搜索匹配的文本模式"""

    name = "text_search"
    description = "在文件或目录中搜索文本内容（支持正则表达式），类似 grep"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式（正则表达式，若无效则退化为纯文本匹配）",
            },
            "path": {
                "type": "string",
                "description": "要搜索的文件或目录路径",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归搜索子目录，默认 true",
                "default": True,
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回匹配数，默认 50",
                "default": 50,
            },
            "file_pattern": {
                "type": "string",
                "description": "文件名过滤 glob，例如 '*.py'（可选）",
            },
        },
        "required": ["pattern", "path"],
    }

    async def execute(
        self,
        pattern: str,
        path: str,
        recursive: bool = True,
        max_results: int = 50,
        file_pattern: str | None = None,
        **_kwargs,
    ) -> ToolResult:
        target = Path(path)
        if not target.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        # Compile regex — fall back to escaped literal on bad patterns
        try:
            compiled = re.compile(pattern)
        except re.error:
            logger.debug("text_search.regex_fallback", pattern=pattern)
            compiled = re.compile(re.escape(pattern))

        logger.debug(
            "text_search.start",
            pattern=pattern,
            path=path,
            recursive=recursive,
        )

        results: list[dict] = []

        if target.is_file():
            _search_file(target, compiled, max_results, results)
        elif target.is_dir():
            iterator = target.rglob("*") if recursive else target.iterdir()
            for entry in iterator:
                if len(results) >= max_results:
                    break
                if not entry.is_file():
                    continue
                if file_pattern and not fnmatch.fnmatch(entry.name, file_pattern):
                    continue
                _search_file(entry, compiled, max_results, results)
        else:
            return ToolResult(success=False, error=f"Not a file or directory: {path}")

        logger.debug("text_search.done", matches=len(results))
        return ToolResult(
            success=True,
            output=json.dumps(results, ensure_ascii=False),
        )
