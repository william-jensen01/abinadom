"""
mcpauth resource-server setup for Auth0 JWT verification (Phase 16.1).

Provides build_mcp_auth() which fetches Auth0 OIDC config and returns
an MCPAuth instance configured for resource-server mode.

Design decisions (from 16.1-CONTEXT.md):
  D-01: Auth0 is the Authorization Server.
  D-02: MCP server is a pure Resource Server.
  D-06: Use mcpauth library for JWT validation, metadata, WWW-Authenticate.
  D-08 (REVISED): Static bearer token auth dropped — Auth0 JWT only.
"""
import logging

from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.utils import fetch_server_config

logger = logging.getLogger(__name__)


def build_mcp_auth(domain: str, resource_url: str) -> MCPAuth:
    """Build an MCPAuth instance in resource-server mode.

    Fetches Auth0's OIDC discovery config (blocking HTTP call — call at
    startup, not per-request). Returns an MCPAuth configured with the
    Auth0 server as the authorization server.

    Args:
        domain: Auth0 tenant domain (e.g. "my-tenant.auth0.com").
        resource_url: The MCP server's public base URL (e.g.
            "https://mcp.yourdomain.com"). Used as the JWT audience in
            bearer_auth_middleware.

    Returns:
        MCPAuth instance with bearer_auth_middleware() and
        metadata_route() ready for Starlette wiring.

    Raises:
        Exception: If fetch_server_config fails (Auth0 unreachable,
            invalid domain, network error). Let the caller handle this.
    """
    auth_server_config = fetch_server_config(
        f"https://{domain}",
        AuthServerType.OIDC,
    )
    logger.info("Fetched Auth0 OIDC config from %s", domain)

    return MCPAuth(server=auth_server_config)
