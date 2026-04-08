"""Web page scraping tool."""

from __future__ import annotations

import json
import re

import aiohttp
import structlog

from axonflow.tools.base import Tool, ToolResult

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

logger = structlog.get_logger()

_USER_AGENT = "Mozilla/5.0 (compatible; AxonFlow/1.0; +https://github.com/axonflow)"


class WebScrapeTool(Tool):
    """抓取网页内容并转换为纯文本"""

    name = "web_scrape"
    description = "抓取指定 URL 的网页内容，去除 HTML 标签后返回纯文本"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页 URL",
            },
            "max_length": {
                "type": "integer",
                "description": "返回文本的最大字符数，默认 5000",
                "default": 5000,
            },
        },
        "required": ["url"],
    }

    async def execute(
        self,
        url: str,
        max_length: int = 5000,
        **_kwargs,
    ) -> ToolResult:
        if not _HAS_BS4:
            return ToolResult(
                success=False,
                error="beautifulsoup4 is not installed. Run: pip install beautifulsoup4",
            )
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, error=f"Invalid URL: {url}")

        try:
            logger.debug("web_scrape.start", url=url, max_length=max_length)

            timeout = aiohttp.ClientTimeout(total=10)
            headers = {"User-Agent": _USER_AGENT}

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return ToolResult(
                            success=False,
                            error=f"HTTP {resp.status}: {resp.reason}",
                        )
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n")

            # Collapse excess whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r"[ \t]+", " ", text)
            text = text.strip()

            if len(text) > max_length:
                text = text[:max_length] + "\n\n... [truncated]"

            result = {
                "url": url,
                "length": len(text),
                "content": text,
            }

            logger.debug("web_scrape.done", url=url, length=len(text))
            return ToolResult(
                success=True,
                output=json.dumps(result, ensure_ascii=False),
            )
        except TimeoutError:
            return ToolResult(success=False, error=f"Request timed out for {url}")
        except aiohttp.ClientError as e:
            return ToolResult(success=False, error=f"Network error: {e}")
        except Exception as e:
            logger.error("web_scrape.error", url=url, error=str(e))
            return ToolResult(success=False, error=f"Scrape failed: {e}")
