# LDS Scripture Citation Index — MCP Server

An MCP (Model Context Protocol) server that exposes the BYU Scripture Citation Index as a hybrid semantic + keyword search tool. Built on Weaviate vector embeddings (Ollama `nomic-embed-text`) of 5,838 General Conference talks (1942–present), covering talks, paragraphs, citations, and footnotes. Connect from Claude.ai, Claude Desktop, or any MCP-compatible client.

## Tools

- **`search`** — Hybrid semantic + keyword search across talks, paragraphs, citations, and footnotes. An `alpha` parameter blends vector and BM25 (0.0 = keyword, 1.0 = semantic, default 0.7); results carry a relevance score. Optional speaker, year, and season filters, plus `group_by_talk` (paragraphs) to spread results across talks.
- **`get_talk`** — Retrieve the full ordered text of a conference talk by ID.
- **`find_by_scripture`** — Find which talks cite a given scripture by book (required), chapter, and verses. No embedding required.
- **`corpus_stats`** — Aggregate counts across a collection, optionally grouped by a field (e.g. speaker, year).

## Guides

| Guide | Description |
|-------|-------------|
| [Connection Guide](docs/CONNECTION.md) | Connect Claude.ai, Claude Desktop, or any MCP client |
| [Self-Deploy Guide](docs/DEPLOY.md) | Deploy the full stack on a new Linux server |
| [Infrastructure Setup](infra/SETUP.md) | Caddy reverse proxy + Cloudflare Tunnel |

## Quick Start

**Connecting to an existing server:**

1. Open Claude.ai → Settings → Integrations → Add MCP Server
2. Enter: `https://mcp.yourdomain.com/mcp`
3. Complete the OAuth login
4. Search for "faith and repentance" in chat

**Deploying a new instance:**

See [docs/DEPLOY.md](docs/DEPLOY.md) for the full walkthrough.

## Tech Stack

- **Runtime:** Python 3.12, FastMCP (HTTP transport)
- **Vector DB:** Weaviate with Ollama nomic-embed-text embeddings
- **Auth:** ScaleKit OAuth 2.1 (JWT via JWKS), RFC 9728 resource metadata
- **Infra:** Docker Compose, Caddy, Cloudflare Tunnel

## License

This project is for personal/educational use.
