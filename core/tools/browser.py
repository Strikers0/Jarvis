from __future__ import annotations

import logging
from typing import Any, Optional

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class PlaywrightManager:
    _instance: Optional[PlaywrightManager] = None
    _playwright: Any = None
    _browser: Any = None
    _context: Any = None

    @classmethod
    async def get_instance(cls) -> PlaywrightManager:
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._init()
        return cls._instance

    async def _init(self) -> None:
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
        except ImportError:
            self._playwright = None
            self._browser = None
            self._context = None
        except Exception as e:
            logger.error("Failed to initialize Playwright: %s", e)
            self._playwright = None
            self._browser = None
            self._context = None

    @property
    def available(self) -> bool:
        return self._browser is not None

    async def new_page(self):
        if not self._context:
            return None
        return await self._context.new_page()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._context = None


class SearchGoogleTool(Tool):
    def __init__(self):
        super().__init__(
            name="search_google",
            description="Search Google and return top result titles and URLs.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results to return", "default": 5},
                },
                "required": ["query"],
            },
            permission_level="auto",
            category="browser",
        )

    async def execute(self, query: str, num_results: int = 5) -> ToolResult:
        pw = await PlaywrightManager.get_instance()
        if not pw.available:
            return ToolResult(success=False, error="Playwright is not available. Install with: pip install playwright && playwright install chromium")

        page = await pw.new_page()
        try:
            await page.goto(f"https://www.google.com/search?q={query}", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            results = []
            items = await page.query_selector_all("div.g")
            for item in items[:num_results]:
                title_el = await item.query_selector("h3")
                link_el = await item.query_selector("a")
                if title_el and link_el:
                    title = await title_el.inner_text()
                    href = await link_el.get_attribute("href")
                    results.append(f"{title}: {href}")
            if not results:
                page_text = await page.inner_text("body")
                lines = [l.strip() for l in page_text.split("\n") if l.strip()]
                snippet = "\n".join(lines[:30])
                return ToolResult(success=True, output=f"Search results page loaded. Content preview:\n{snippet}")
            output = "\n".join(results)
            return ToolResult(success=True, output=output, data={"results": results})
        except Exception as e:
            return ToolResult(success=False, error=f"Google search failed: {e}")
        finally:
            await page.close()


class SearchYouTubeTool(Tool):
    def __init__(self):
        super().__init__(
            name="search_youtube",
            description="Search YouTube and return top video titles and URLs.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results", "default": 5},
                },
                "required": ["query"],
            },
            permission_level="auto",
            category="browser",
        )

    async def execute(self, query: str, num_results: int = 5) -> ToolResult:
        pw = await PlaywrightManager.get_instance()
        if not pw.available:
            return ToolResult(success=False, error="Playwright is not available")

        page = await pw.new_page()
        try:
            await page.goto(f"https://www.youtube.com/results?search_query={query}", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            results = []
            links = await page.query_selector_all("a#video-title")
            for link in links[:num_results]:
                title = await link.get_attribute("title") or await link.inner_text()
                href = await link.get_attribute("href")
                if title and href:
                    results.append(f"{title}: https://www.youtube.com{href}")
            if not results:
                page_text = await page.inner_text("body")
                lines = [l.strip() for l in page_text.split("\n") if l.strip()]
                snippet = "\n".join(lines[:30])
                return ToolResult(success=True, output=f"Search results loaded. Content preview:\n{snippet}")
            output = "\n".join(results)
            return ToolResult(success=True, output=output, data={"results": results})
        except Exception as e:
            return ToolResult(success=False, error=f"YouTube search failed: {e}")
        finally:
            await page.close()


class OpenURLTool(Tool):
    def __init__(self):
        super().__init__(
            name="open_url",
            description="Open a URL in the browser.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to open"},
                    "new_tab": {"type": "boolean", "description": "Open in new tab", "default": True},
                },
                "required": ["url"],
            },
            permission_level="auto",
            category="browser",
        )

    async def execute(self, url: str, new_tab: bool = True) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        pw = await PlaywrightManager.get_instance()
        if not pw.available:
            return ToolResult(success=False, error="Playwright is not available")
        page = await pw.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await page.title()
            return ToolResult(success=True, output=f"Opened {url} - Page title: {title}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open URL: {e}")
        finally:
            await page.close()


class ExtractTextTool(Tool):
    def __init__(self):
        super().__init__(
            name="extract_text",
            description="Extract text content from a webpage using CSS selector.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract text from"},
                    "selector": {"type": "string", "description": "CSS selector (default: 'body')", "default": "body"},
                },
                "required": ["url"],
            },
            permission_level="auto",
            category="browser",
        )

    async def execute(self, url: str, selector: str = "body") -> ToolResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        pw = await PlaywrightManager.get_instance()
        if not pw.available:
            return ToolResult(success=False, error="Playwright is not available")
        page = await pw.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            element = await page.query_selector(selector)
            if not element:
                return ToolResult(success=False, error=f"No element found for selector: {selector}")
            text = await element.inner_text()
            truncated = text[:5000]
            return ToolResult(success=True, output=truncated, data={"full_length": len(text), "text": truncated})
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to extract text: {e}")
        finally:
            await page.close()


class BrowserAutomationToolSet:
    def get_tools(self) -> list[Tool]:
        return [
            SearchGoogleTool(),
            SearchYouTubeTool(),
            OpenURLTool(),
            ExtractTextTool(),
        ]
