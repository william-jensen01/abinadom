# LDS Scripture Citation Index — MCP Server

An MCP (Model Context Protocol) server that exposes the BYU Scripture Citation Index as a semantic search tool. Built on ChromaDB vector embeddings of 5,800+ General Conference talks (1971–present), covering talks, paragraphs, citations, and footnotes. Connect from Claude.ai, Claude Desktop, or any MCP-compatible client.

## Tools

- **`search`** — Semantic search across talks, paragraphs, citations, and footnotes. Supports speaker, year, and season filters.
- **`get_talk`** — Retrieve the full ordered text of a conference talk by ID.

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

- **Runtime:** Python 3.12, FastAPI, Uvicorn
- **Vector DB:** ChromaDB with Ollama nomic-embed-text embeddings
- **Auth:** Auth0 OAuth 2.1 (JWT), RFC 9728 resource metadata
- **Infra:** Docker Compose, Caddy, Cloudflare Tunnel

## License

This project is for personal/educational use.
