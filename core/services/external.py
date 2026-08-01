from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from core.services.base import Service, service_tool
from core.tools.base import Tool

logger = logging.getLogger(__name__)

_USER_AGENT = "JARVIS-Assistant/0.1 (personal AI assistant)"


class ExternalAPIsService(Service):
    """Weather, news, stocks, crypto and reference lookups via public APIs."""

    name = "external"
    description = "External data lookups: weather, news, stocks, crypto, Wikipedia."

    def __init__(self, weather_api_key: str = "", news_api_key: str = "", default_city: str = ""):
        self.weather_api_key = weather_api_key or os.getenv("WEATHER_API_KEY", "")
        self.news_api_key = news_api_key or os.getenv("NEWS_API_KEY", "")
        self.default_city = default_city
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
        return self._client

    async def get_weather(self, city: str = "") -> str:
        city = (city or self.default_city or "").strip()
        if not city:
            return "No city provided. Tell me a city to get its weather."
        if self.weather_api_key:
            try:
                resp = await self.client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": city, "units": "metric", "appid": self.weather_api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                main = data.get("main", {})
                weather = (data.get("weather") or [{}])[0]
                return (
                    f"Weather in {data.get('name', city)}: {weather.get('description', 'n/a')}. "
                    f"Temperature: {main.get('temp', '?')}°C (feels like {main.get('feels_like', '?')}°C). "
                    f"Humidity: {main.get('humidity', '?')}%. Wind: {data.get('wind', {}).get('speed', '?')} m/s."
                )
            except Exception as e:
                logger.warning("OpenWeatherMap failed for %r: %s", city, e)
        try:
            resp = await self.client.get(f"https://wttr.in/{city}", params={"format": "j1"})
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            area = (data.get("nearest_area") or [{}])[0].get("areaName", [{}])[0].get("value", city)
            return (
                f"Weather in {area}: {current.get('weatherDesc', [{}])[0].get('value', 'n/a')}. "
                f"Temperature: {current.get('temp_C', '?')}°C (feels like {current.get('FeelsLikeC', '?')}°C). "
                f"Humidity: {current.get('humidity', '?')}%. Wind: {current.get('windspeedKmph', '?')} km/h."
            )
        except Exception as e:
            return f"Could not fetch weather for '{city}': {e}"

    async def get_news(self, query: str = "", count: int = 5) -> str:
        if self.news_api_key:
            try:
                if query:
                    resp = await self.client.get(
                        "https://newsapi.org/v2/everything",
                        params={"q": query, "pageSize": count, "language": "en"},
                        headers={"X-Api-Key": self.news_api_key},
                    )
                else:
                    resp = await self.client.get(
                        "https://newsapi.org/v2/top-headlines",
                        params={"country": "us", "pageSize": count},
                        headers={"X-Api-Key": self.news_api_key},
                    )
                resp.raise_for_status()
                articles = resp.json().get("articles", [])
                lines = [
                    f"- {a.get('title', '')} ({a.get('source', {}).get('name', 'unknown')})"
                    for a in articles[:count]
                ]
                return "\n".join(lines) if lines else "No news found."
            except Exception as e:
                logger.warning("NewsAPI failed: %s", e)
        try:
            import urllib.parse
            q = urllib.parse.quote(query or "world news")
            resp = await self.client.get(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            items = []
            for item in root.iter("item"):
                title = item.findtext("title", "")
                source = item.findtext("source", "")
                items.append(f"- {title} ({source})")
                if len(items) >= count:
                    break
            return "\n".join(items) if items else "No news found."
        except Exception as e:
            return f"Could not fetch news: {e}"

    async def get_stock(self, symbol: str = "AAPL") -> str:
        symbol = symbol.strip().upper()
        if not symbol:
            return "No stock symbol provided."
        try:
            resp = await self.client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1d"},
            )
            resp.raise_for_status()
            data = resp.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None:
                return f"Could not fetch price for {symbol}."
            change = ""
            if prev:
                pct = (price - prev) / prev * 100
                change = f" ({pct:+.2f}% today)"
            return f"{symbol}: ${price:,.2f}{change}"
        except Exception as e:
            return f"Could not fetch stock {symbol}: {e}"

    async def get_crypto(self, symbol: str = "bitcoin") -> str:
        symbol = symbol.strip().lower()
        try:
            resp = await self.client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": symbol, "vs_currencies": "usd", "include_24hr_change": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
            if symbol not in data:
                return f"Unknown cryptocurrency: {symbol}. Try 'bitcoin', 'ethereum', etc."
            entry = data[symbol]
            price = entry.get("usd")
            change = entry.get("usd_24h_change")
            if price is None:
                return f"Could not fetch price for {symbol}."
            change_str = f" ({change:+.2f}% 24h)" if change is not None else ""
            return f"{symbol.title()}: ${price:,.2f}{change_str}"
        except Exception as e:
            return f"Could not fetch crypto {symbol}: {e}"

    async def get_wikipedia(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "No search term provided."
        try:
            resp = await self.client.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_"),
            )
            resp.raise_for_status()
            data = resp.json()
            title = data.get("title", query)
            extract = (data.get("extract") or "No summary available.").strip()
            return f"{title}: {extract[:1000]}"
        except Exception as e:
            logger.warning("Wikipedia REST summary failed for %r: %s", query, e)
        try:
            import urllib.parse
            resp = await self.client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "prop": "extracts",
                    "explaintext": "1",
                    "exintro": "1",
                    "redirects": "1",
                    "titles": urllib.parse.unquote(query),
                },
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                if extract := page.get("extract"):
                    return f"{page.get('title', query)}: {extract[:1000]}"
            return f"No Wikipedia article found for '{query}'."
        except Exception as e:
            logger.warning("Wikipedia action API failed for %r: %s", query, e)
        try:
            from core.tools.browser import _ddg_search
            results = await _ddg_search(query, 1)
            if results:
                top = results[0]
                return f"Could not fetch Wikipedia summary directly. Top result for '{query}': {top['title']} - {top['url']}"
        except Exception:
            pass
        return f"Could not fetch Wikipedia summary for '{query}'. Wikipedia API is unreachable from this network."

    def get_tools(self) -> list[Tool]:
        return [
            service_tool(
                name="get_weather",
                description="Get current weather for a city.",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name, e.g. 'Mumbai'", "default": ""},
                    },
                    "required": [],
                },
                handler=self.get_weather,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="get_news",
                description="Get latest news headlines, optionally about a topic.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "News topic (optional)", "default": ""},
                        "count": {"type": "integer", "description": "Number of headlines", "default": 5},
                    },
                    "required": [],
                },
                handler=self.get_news,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="get_stock",
                description="Get current stock price for a ticker symbol.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker symbol, e.g. 'AAPL'", "default": "AAPL"},
                    },
                    "required": [],
                },
                handler=self.get_stock,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="get_crypto",
                description="Get current cryptocurrency price.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Coin id, e.g. 'bitcoin'", "default": "bitcoin"},
                    },
                    "required": [],
                },
                handler=self.get_crypto,
                category="services",
                permission_level="auto",
            ),
            service_tool(
                name="get_wikipedia",
                description="Get a short Wikipedia summary for a topic.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Topic to look up"},
                    },
                    "required": ["query"],
                },
                handler=self.get_wikipedia,
                category="services",
                permission_level="auto",
            ),
        ]

    async def health_check(self) -> dict:
        try:
            resp = await self.client.get("https://api.github.com", headers={"Accept": "application/vnd.github+json"})
            return {"ok": resp.status_code == 200, "detail": "External API reachable"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
