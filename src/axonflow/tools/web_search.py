"""Web search tool using DuckDuckGo."""

from __future__ import annotations

import json

import structlog

from axonflow.tools.base import Tool, ToolResult

logger = structlog.get_logger()

try:
    from duckduckgo_search import DDGS

    _HAS_DDGS = True
except ImportError:
    _HAS_DDGS = False


class WebSearchTool(Tool):
    """使用 DuckDuckGo 进行网络搜索"""

    name = "web_search"
    description = "通过 DuckDuckGo 搜索网络内容，返回标题、链接和摘要"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数，默认 5",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        **_kwargs,
    ) -> ToolResult:
        if not _HAS_DDGS:
            return ToolResult(
                success=False,
                error="duckduckgo_search library is not installed. "
                "Install it with: pip install duckduckgo_search",
            )

        try:
            logger.debug("web_search.start", query=query, max_results=max_results)

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw_results
            ]

            logger.debug("web_search.done", count=len(results))
            return ToolResult(
                success=True,
                output=json.dumps(results, ensure_ascii=False),
            )
        except TimeoutError:
            return ToolResult(success=False, error="Search timed out")
        except Exception as e:
            logger.error("web_search.error", error=str(e))
            return ToolResult(success=False, error=f"Search failed: {e}")
