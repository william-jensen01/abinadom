# Connecting to the LDS MCP Server

This guide covers connecting MCP clients to a running LDS MCP server instance.

## Prerequisites

- The server must be running and reachable. See [docs/DEPLOY.md](DEPLOY.md) for setup.
- You need the server's public URL (e.g. `https://mcp.yourdomain.com`).
- Verify connectivity:

```bash
curl -f https://mcp.yourdomain.com/health
```

## Claude.ai (OAuth 2.0)

1. Open Claude.ai settings — navigate to **Settings > Integrations** (or `claude.ai/settings/integrations`).
2. Click **Add MCP Server** (or **Add Integration**).
3. Enter the server URL: `https://mcp.yourdomain.com/mcp`
4. Claude.ai discovers OAuth metadata via `/.well-known/oauth-protected-resource/mcp` and redirects to Auth0 for login.
5. Complete the Auth0 login and consent flow.
6. After redirect, the MCP tools (`search`, `get_talk`) appear in Claude.ai.

> **Note:** The server implements RFC 9728 (Protected Resource Metadata) and proxies RFC 8414 (Authorization Server Metadata) from Auth0. Claude.ai handles the full OAuth 2.1 flow automatically.

## Claude Desktop (Remote MCP)

1. Open Claude Desktop settings: **Settings > Developer > Edit Config**.
2. Add the server to `mcpServers` in the config JSON:

```json
{
  "mcpServers": {
    "lds-scripture-index": {
      "url": "https://mcp.yourdomain.com/mcp"
    }
  }
}
```

3. Restart Claude Desktop.
4. Claude Desktop performs the OAuth handshake with Auth0 automatically.
5. After authentication, `search` and `get_talk` tools are available in chat.

## Other Clients (curl, HTTP)

For clients that do not support OAuth discovery, obtain an access token from Auth0 first, then include it in requests.

### Obtaining a Token

Auth0 Machine-to-Machine (M2M) client credentials flow:

```bash
curl -X POST https://YOUR_AUTH0_DOMAIN/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "https://mcp.yourdomain.com"
  }'
```

> **Requires** an Auth0 Machine-to-Machine application configured for the MCP API audience.

### MCP Protocol Requests

The MCP server uses JSON-RPC 2.0 over HTTP POST. Follow this three-step flow:

**Step 1 — Initialize (no auth required):**

```bash
curl -X POST https://mcp.yourdomain.com/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

Save the `Mcp-Session-Id` header value from the response — required for all subsequent requests.

**Step 2 — List tools (auth required):**

```bash
curl -X POST https://mcp.yourdomain.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Mcp-Session-Id: SESSION_ID_FROM_STEP_1" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

**Step 3 — Call a tool (auth required):**

```bash
curl -X POST https://mcp.yourdomain.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Mcp-Session-Id: SESSION_ID_FROM_STEP_1" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search","arguments":{"query":"faith and repentance","collection":"paragraphs","n_results":3}}}'
```

## Discovery Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Server health check (no auth) |
| `GET /.well-known/oauth-protected-resource` | RFC 9728 Protected Resource Metadata |
| `GET /.well-known/oauth-protected-resource/mcp` | RFC 9728 (MCP-specific path) |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 Authorization Server Metadata (proxied from Auth0) |

## Troubleshooting

- **401 Unauthorized** — Token expired or invalid. Re-authenticate and use the new token.
- **404 on well-known endpoints** — `AUTH0_DOMAIN` or `MCP_BASE_URL` not set in the server `.env`. Check environment configuration.
- **Connection refused** — Server not running. Check `docker compose ps` and verify `/health` responds.
- **OAuth redirect fails** — Auth0 callback URLs do not include the client's redirect URI. Add the redirect URI in the Auth0 dashboard under **Applications > Settings > Allowed Callback URLs**.
