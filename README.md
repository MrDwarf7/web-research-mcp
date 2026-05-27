# Web Research MCP Server

**Give any AI agent the power to search the web, extract content from any URL, and perform deep research — all through a single MCP server.**

![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)
![Python](https://img.shields.io/badge/Python-3.10%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## What It Does

Three tools that turn any MCP-compatible AI (Claude Desktop, Claude Code, Cursor, VS Code Copilot, OpenClaw, etc.) into a web research powerhouse:

| Tool | What it does |
|------|-------------|
| `web_search` | Search the web via DuckDuckGo or Google. Returns titles, URLs, and snippets. |
| `web_extract` | Extract clean, ad-free content from any URL. Strips nav, ads, sidebars. Returns full text. |
| `web_research` | Deep research: search + fetch top pages + return everything. One command for comprehensive answers. |

## Quick Start

```bash
# Install
pip install web-research-mcp

# Run (stdio mode — works with all MCP clients)
web-research-mcp
```

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "web-research": {
      "command": "web-research-mcp"
    }
  }
}
```

### Claude Code

```bash
claude --mcp "web-research-mcp"
```

### Cursor / VS Code Copilot

Add to your MCP settings:

```json
{
  "mcpServers": {
    "web-research": {
      "command": "web-research-mcp"
    }
  }
}
```

## Tool Reference

### `web_search(query, provider?, num_results?)`

Search the web for a query.

**Parameters:**
- `query` (string, required) — Search query
- `provider` (string, optional) — `"duckduckgo"` (default) or `"google"`
- `num_results` (integer, optional) — Results count (default: 5, max: 10)

**Returns:** Numbered list of results with titles, URLs, and snippets.

### `web_extract(url)`

Extract clean content from any web page.

**Parameters:**
- `url` (string, required) — Full URL to extract

**Returns:** Page title, description, clean markdown-formatted content, word count, extracted links. Strips: scripts, navigation, ads, sidebars, cookie banners, comments.

### `web_research(query, depth?)`

Full research workflow: search → fetch top results → return everything.

**Parameters:**
- `query` (string, required) — Research topic
- `depth` (integer, optional) — Pages to fetch (default: 3, max: 5)

**Returns:** Search results + full extracted content from each page.

## Why This Server?

| Feature | This Server | Free MCP Servers |
|---------|------------|-----------------|
| Clean content extraction | ✅ Strips ads, nav, junk | ❌ Raw HTML only |
| Multiple search providers | ✅ DuckDuckGo + Google | ❌ Usually one |
| Deep research mode | ✅ Search + fetch + return | ❌ Search only |
| Markdown output | ✅ Beautiful formatting | ❌ Raw text |
| No API keys needed | ✅ Zero config | Usually requires API key |
| Content size limit | ✅ 100K chars | ❌ Often pages truncated |

## Requirements

- Python 3.10+
- Works on macOS, Linux, Windows

```bash
pip install web-research-mcp
```

## Privacy

- Search queries go to DuckDuckGo or Google directly
- URL content is fetched directly from the source
- No tracking, no analytics, no data collection
- No API keys = no accounts = no surveillance

## License

MIT — free for personal and commercial use.

## Support

Open an issue on GitHub for bugs or feature requests.
