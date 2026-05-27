"""
Web Research MCP Server

Provides AI agents with web search, content extraction, and research capabilities.
Install: pip install web-research-mcp
Usage: npx web-research-mcp  OR  python -m web_research_mcp
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

# ── Configuration ──────────────────────────────────────────────────────

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

MAX_CONTENT_LENGTH = 100_000  # chars
REQUEST_TIMEOUT = 30  # seconds
MAX_SEARCH_RESULTS = 8

# Ads to filter out from search results
AD_DOMAINS = {"duckduckgo.com/y.js", "google.com/aclk", "bing.com/aclick"}
AD_KEYWORDS = {"ad_domain", "ad_provider", "aclick", "y.js"}


def is_ad_result(url: str) -> bool:
    """Check if a search result is an ad."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        for ad_domain in AD_DOMAINS:
            if ad_domain in f"{domain}{path}":
                return True
        for kw in AD_KEYWORDS:
            if kw in url.lower():
                return True
    except Exception:
        pass
    return False


def filter_ads(results: list[dict]) -> list[dict]:
    """Remove ad results from search results."""
    return [r for r in results if not is_ad_result(r.get("url", ""))]

# ── Search Providers ───────────────────────────────────────────────────

SEARCH_PROVIDERS: dict[str, Any] = {}


def register_search_provider(name: str, handler: Any) -> None:
    SEARCH_PROVIDERS[name] = handler


async def search_duckduckgo(query: str, num_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Search using DuckDuckGo's HTML interface (no API key needed)."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.post(url, data=params, headers=headers)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for result in soup.select(".result")[:num_results]:
        title_el = result.select_one(".result__title a")
        snippet_el = result.select_one(".result__snippet")

        if not title_el:
            continue

        href = title_el.get("href", "")
        # DDG wraps URLs
        match = re.search(r"uddg=([^&]+)", str(href))
        actual_url = (
            httpx.URL(match.group(1)).path if match else str(title_el.get("href", ""))
        )
        # Better URL extraction from redirect
        if "uddg=" in str(href):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(str(href))
            qs = parse_qs(parsed.query)
            actual_url = qs.get("uddg", [""])[0]
        else:
            actual_url = str(title_el.get("href", ""))

        results.append({
            "title": title_el.get_text(strip=True),
            "url": actual_url,
            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
        })

    return results


async def search_google(query: str, num_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Search using Google HTML (no API key needed, may be rate-limited)."""
    url = "https://www.google.com/search"
    params = {"q": query, "num": min(num_results, 10)}
    headers = {"User-Agent": DEFAULT_USER_AGENT}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for g in soup.select("div.g")[:num_results]:
        a_tag = g.select_one("a")
        h3 = g.select_one("h3")
        snippet_div = g.select_one("div[data-sncf], span.aCOpRe, div.VwiC3b")

        if not a_tag or not h3:
            continue

        results.append({
            "title": h3.get_text(strip=True),
            "url": a_tag.get("href", ""),
            "snippet": snippet_div.get_text(strip=True) if snippet_div else "",
        })

    return results


register_search_provider("duckduckgo", search_duckduckgo)
register_search_provider("google", search_google)


async def search_web(query: str, provider: str = "duckduckgo") -> list[dict]:
    """Search the web using the specified provider."""
    handler = SEARCH_PROVIDERS.get(provider)
    if not handler:
        # Fallback to first available
        handler = list(SEARCH_PROVIDERS.values())[0]

    try:
        results = await handler(query)
        return filter_ads(results)
    except Exception as e:
        # Try fallback provider
        for name, fallback in SEARCH_PROVIDERS.items():
            if name != provider:
                try:
                    return await fallback(query)
                except Exception:
                    continue
        raise


# ── Content Extraction ─────────────────────────────────────────────────


def extract_content(html: str, url: str) -> dict:
    """Extract clean content from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.select(
        "script, style, nav, footer, header, aside, "
        ".sidebar, .menu, .advertisement, .ad, "
        ".cookie-banner, .newsletter, .social-share, "
        "noscript, iframe, .comments, .comment"
    ):
        tag.decompose()

    title = ""
    title_tag = soup.select_one("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        title_tag = soup.select_one("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Get meta description
    meta_desc = ""
    meta_tag = soup.select_one("meta[name='description']")
    if meta_tag and meta_tag.get("content"):
        meta_desc = meta_tag["content"]

    # Extract main content
    main_content = soup.select_one("main, article, .content, #content, .post, .article")
    if not main_content:
        main_content = soup.select_one("body")

    text_parts: list[str] = []
    if main_content:
        for el in main_content.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "code", "blockquote"]):
            text = el.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            if el.name.startswith("h"):
                prefix = "\n" + "#" * int(el.name[1]) + " "
                text_parts.append(f"{prefix}{text}")
            elif el.name in ("pre", "code"):
                text_parts.append(f"\n```\n{text}\n```\n")
            elif el.name == "blockquote":
                text_parts.append(f"> {text}")
            else:
                text_parts.append(text)

    content = "\n\n".join(text_parts)

    # Truncate if too long
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated...]"

    # Extract links
    links = []
    for a in (main_content or soup).find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if text and href and not href.startswith("#") and not href.startswith("javascript:"):
            links.append({"text": text, "url": href})

    return {
        "url": url,
        "title": title,
        "description": meta_desc,
        "content": content,
        "word_count": len(content.split()),
        "links": links[:50],  # max 50 links
    }


async def fetch_url(url: str) -> dict:
    """Fetch and extract content from a URL."""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True, verify=False
    ) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")

        if "application/json" in content_type or url.endswith(".json"):
            data = resp.json()
            return {
                "url": url,
                "title": "",
                "description": "",
                "content": json.dumps(data, indent=2)[:MAX_CONTENT_LENGTH],
                "word_count": 0,
                "links": [],
                "format": "json",
            }

        if "text/" in content_type or "html" in content_type:
            return extract_content(resp.text, url)

        return {
            "url": url,
            "title": "",
            "description": "",
            "content": resp.text[:MAX_CONTENT_LENGTH],
            "word_count": 0,
            "links": [],
            "format": "text",
        }


async def research_topic(query: str, depth: int = 3) -> dict:
    """
    Deep research on a topic: search, fetch top results, synthesize.
    """
    results = await search_web(query)

    pages = []
    for r in results[:depth]:
        try:
            page = await fetch_url(r["url"])
            pages.append(page)
        except Exception:
            continue

    return {
        "query": query,
        "search_results": results,
        "pages": pages,
        "total_pages_fetched": len(pages),
    }


# ── MCP Server ─────────────────────────────────────────────────────────

server = Server("web-research")


@server.list_tools()
async def handle_list_tools() -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(
            name="web_search",
            description="Search the web for a query. Returns title, URL, and snippet for each result. Use when you need current information from the internet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "provider": {
                        "type": "string",
                        "description": "Search provider (duckduckgo or google)",
                        "default": "duckduckgo",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (max 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="web_extract",
            description="Extract clean, readable content from a URL. Returns title, description, main content, word count, and links. Strips ads, navigation, and non-content elements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to extract content from",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="web_research",
            description="Deep research: searches for a topic, fetches the top result pages, and returns structured content from all of them. Use for comprehensive research on a topic.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Research topic or question",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Number of pages to fetch (1-5)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        ),
    ])


@server.call_tool()
async def handle_call_tool(request: CallToolRequest) -> CallToolResult:
    name = request.params.name
    args = request.params.arguments or {}

    try:
        if name == "web_search":
            query = args.get("query", "")
            provider = args.get("provider", "duckduckgo")
            num = min(int(args.get("num_results", 5)), 10)
            results = await search_web(query, provider)

            if not results:
                return CallToolResult(
                    content=[TextContent(type="text", text="No search results found.", mimeType="text/plain")]
                )

            output = []
            for i, r in enumerate(results[:num], 1):
                output.append(f"{i}. [{r['title']}]({r['url']})")
                if r.get("snippet"):
                    output.append(f"   {r['snippet']}")
                output.append("")

            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(output).strip(), mimeType="text/plain")]
            )

        elif name == "web_extract":
            url = args.get("url", "")
            if not url:
                return CallToolResult(
                    content=[TextContent(type="text", text="Error: 'url' parameter is required.", mimeType="text/plain")]
                )

            result = await fetch_url(url)
            output = f"# {result['title']}\n\n"
            if result.get("description"):
                output += f"*{result['description']}*\n\n"
            output += result.get("content", "")
            output += f"\n\n---\nWord count: {result.get('word_count', 0)}"

            return CallToolResult(
                content=[TextContent(type="text", text=output, mimeType="text/markdown")]
            )

        elif name == "web_research":
            query = args.get("query", "")
            depth = min(int(args.get("depth", 3)), 5)
            result = await research_topic(query, depth)

            output = [f"# Research: {query}", f"\nSearch results found: {len(result['search_results'])}", f"Pages fetched: {result['total_pages_fetched']}", ""]

            for i, r in enumerate(result["search_results"], 1):
                output.append(f"## {i}. {r['title']}")
                output.append(f"URL: {r['url']}")
                if r.get("snippet"):
                    output.append(f"_{r['snippet']}_")
                output.append("")

            for page in result["pages"]:
                output.append(f"---\n## Content from: {page['title']}")
                output.append(page.get("content", "")[:5000])
                output.append("")

            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(output), mimeType="text/markdown")]
            )

        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}", mimeType="text/plain")]
            )

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}", mimeType="text/plain")]
        )


# ── Entry Point ────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options(),
        )


# ── CLI Entry Point ────────────────────────────────────────────────────

def cli_entry():
    """CLI entry point for the web-research-mcp command."""
    import anyio
    anyio.run(main)


if __name__ == "__main__":
    import anyio
    anyio.run(main)