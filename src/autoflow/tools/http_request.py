"""HTTP 请求工具"""

from __future__ import annotations

import json

import aiohttp

from autoflow.tools.base import Tool, ToolResult


class HttpRequestTool(Tool):
    """发起 HTTP 请求"""

    name = "http_request"
    description = "发起 HTTP GET/POST 请求并返回响应"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "请求 URL",
            },
            "method": {
                "type": "string",
                "description": "HTTP 方法: GET / POST",
                "enum": ["GET", "POST"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "请求头（可选）",
            },
            "body": {
                "type": "string",
                "description": "请求体（POST 时使用，可选）",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 30",
                "default": 30,
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: str | None = None,
        timeout: int = 30,
        **_kwargs,
    ) -> ToolResult:
        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                kwargs: dict = {"headers": headers or {}}
                if method == "POST" and body:
                    kwargs["data"] = body

                async with session.request(method, url, **kwargs) as resp:
                    response_text = await resp.text()
                    status = resp.status

                    if 200 <= status < 300:
                        return ToolResult(
                            success=True,
                            output=json.dumps(
                                {"status": status, "body": response_text},
                                ensure_ascii=False,
                            ),
                        )
                    else:
                        return ToolResult(
                            success=False,
                            error=f"HTTP {status}: {response_text[:500]}",
                        )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
