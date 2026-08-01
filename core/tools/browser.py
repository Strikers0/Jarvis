from __future__ import annotations

import asyncio
import html as html_mod
import logging
import re
import subprocess
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Optional

import httpx

from core.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def _http_get(url: str, timeout: float = 20.0) -> str:
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _clean_ddg_url(url: str) -> str:
    url = html_mod.unescape(url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" in parsed.netloc:
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return qs["uddg"][0]
    return url


def _parse_ddg(html_text: str, num_results: int) -> list[dict]:
    results: list[dict] = []
    title_re = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    snippet_re = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
    snippets = [html_mod.unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in snippet_re.findall(html_text)]
    for i, m in enumerate(title_re.finditer(html_text)):
        url = _clean_ddg_url(m.group(1))
        title = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2))).split())
        if not title or not url:
            continue
        if "duckduckgo.com" in url or "bing.com" in url:
            continue
        result = {"title": title, "url": url}
        if i < len(snippets):
            result["snippet"] = " ".join(snippets[i].split())[:300]
        results.append(result)
        if len(results) >= num_results:
            break
    return results


async def _open_in_browser(url: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "cmd", "/c", "start", "", url,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await proc.wait()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html_text: str) -> str:
    parser = _TextExtractor()
    parser.feed(html_text)
    text = "".join(parser.parts)
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.split("\n")]
    return "\n".join(l for l in lines if l)


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
                user_agent=_USER_AGENT,
                locale="en-US",
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


async def _handle_google_consent(page: Any) -> None:
    try:
        content = (await page.content())[:3000].lower()
        if "consent.google.com" in page.url or "before you continue" in content:
            for btn_text in ("Accept all", "I agree", "Agree", "Accept"):
                btn = page.get_by_text(btn_text, exact=True)
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(1500)
                    break
    except Exception as e:
        logger.warning("Google consent handling failed: %s", e)


async def _ddg_search(query: str, num_results: int) -> Optional[list[dict]]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        page_html = await _http_get(url)
        results = _parse_ddg(page_html, num_results)
        if results:
            return results
    except Exception as e:
        logger.warning("HTTP DDG search failed for %r: %s", query, e)

    pw = await PlaywrightManager.get_instance()
    if pw.available:
        page = await pw.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            links = await page.eval_on_selector_all(
                "a.result__a",
                f"els => els.slice(0, {num_results}).map(e => ({{title: e.innerText, url: e.href}}))",
            )
            results = []
            for r in links:
                clean = _clean_ddg_url(r["url"])
                if clean and "duckduckgo.com" not in clean:
                    results.append({"title": r["title"], "url": clean})
            if results:
                return results
        except Exception as e:
            logger.warning("Playwright DDG search failed: %s", e)
        finally:
            await page.close()
    return None


async def _google_search(query: str, num_results: int) -> Optional[list[dict]]:
    pw = await PlaywrightManager.get_instance()
    if not pw.available:
        return None
    page = await pw.new_page()
    try:
        await page.goto(
            f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=en&gl=us",
            wait_until="domcontentloaded",
        )
        await _handle_google_consent(page)
        await page.wait_for_timeout(2500)
        results = []
        items = await page.query_selector_all("div.g, div[data-hveid]")
        for item in items[:num_results * 2]:
            title_el = await item.query_selector("h3")
            link_el = await item.query_selector("a")
            if title_el and link_el:
                title = await title_el.inner_text()
                href = await link_el.get_attribute("href")
                if title and href and href.startswith("http"):
                    results.append({"title": title, "url": href})
        if results:
            return results[:num_results]
    except Exception as e:
        logger.warning("Playwright Google search failed: %s", e)
    finally:
        await page.close()
    return None


async def _youtube_search(query: str, num_results: int) -> Optional[list[dict]]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(f"site:youtube.com {query}")
    try:
        page_html = await _http_get(url)
        results = [r for r in _parse_ddg(page_html, num_results * 3) if "youtube.com/watch" in r["url"]][:num_results]
        if results:
            return results
    except Exception as e:
        logger.warning("HTTP YouTube search failed for %r: %s", query, e)

    pw = await PlaywrightManager.get_instance()
    if pw.available:
        page = await pw.new_page()
        try:
            await page.goto(
                f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(3000)
            results = []
            links = await page.query_selector_all("a#video-title")
            for link in links[:num_results]:
                title = await link.get_attribute("title") or await link.inner_text()
                href = await link.get_attribute("href")
                if title and href:
                    results.append({"title": title, "url": f"https://www.youtube.com{href}"})
            if results:
                return results
        except Exception as e:
            logger.warning("Playwright YouTube search failed: %s", e)
        finally:
            await page.close()
    return None


def _format_results(results: list[dict]) -> str:
    lines = []
    for r in results:
        line = f"{r['title']}: {r['url']}"
        if r.get("snippet"):
            line += f"\n  {r['snippet']}"
        lines.append(line)
    return "\n".join(lines)


class SearchWebTool(Tool):
    def __init__(self):
        super().__init__(
            name="search_web",
            description="Search the web and return top result titles and URLs. Use for any web search.",
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
        results = await _ddg_search(query, num_results)
        if results:
            return ToolResult(success=True, output=_format_results(results), data={"results": results})
        await _open_in_browser("https://duckduckgo.com/?q=" + urllib.parse.quote(query))
        return ToolResult(success=True, output=f"Opened DuckDuckGo search for '{query}' in your browser.")


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
        results = await _google_search(query, num_results)
        if results:
            return ToolResult(success=True, output=_format_results(results), data={"results": results})
        results = await _ddg_search(query, num_results)
        if results:
            return ToolResult(success=True, output=_format_results(results), data={"results": results})
        await _open_in_browser("https://www.google.com/search?q=" + urllib.parse.quote(query))
        return ToolResult(success=True, output=f"Opened Google search for '{query}' in your browser.")


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
        results = await _youtube_search(query, num_results)
        if results:
            return ToolResult(success=True, output=_format_results(results), data={"results": results})
        await _open_in_browser("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
        return ToolResult(success=True, output=f"Opened YouTube search for '{query}' in your browser.")


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
        if pw.available:
            page = await pw.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                return ToolResult(success=True, output=f"Opened {url} - Page title: {title}")
            except Exception as e:
                logger.warning("Playwright open_url failed: %s", e)
            finally:
                await page.close()
        try:
            await _open_in_browser(url)
            return ToolResult(success=True, output=f"Opened {url} in your default browser.")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to open URL: {e}")


class ExtractTextTool(Tool):
    def __init__(self):
        super().__init__(
            name="extract_text",
            description="Extract readable text content from a webpage.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract text from"},
                    "selector": {"type": "string", "description": "CSS selector (best effort; default 'body')", "default": "body"},
                },
                "required": ["url"],
            },
            permission_level="auto",
            category="browser",
        )

    async def execute(self, url: str, selector: str = "body") -> ToolResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            page_html = await _http_get(url, timeout=30.0)
            text = _html_to_text(page_html)
            if text.strip():
                truncated = text[:5000]
                return ToolResult(success=True, output=truncated, data={"full_length": len(text), "text": truncated})
        except Exception as e:
            logger.warning("HTTP extract_text failed for %r: %s", url, e)

        pw = await PlaywrightManager.get_instance()
        if pw.available:
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

        return ToolResult(success=False, error=f"Failed to fetch {url}")


class BrowserAutomationToolSet:
    def get_tools(self) -> list[Tool]:
        return [
            SearchWebTool(),
            SearchGoogleTool(),
            SearchYouTubeTool(),
            OpenURLTool(),
            ExtractTextTool(),
        ]
