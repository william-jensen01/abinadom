"""
Unit tests for auth.oauth — mcpauth resource-server setup.

Covers:
  - Test 1: build_mcp_auth returns MCPAuth instance on successful config fetch
  - Test 2: build_mcp_auth propagates exception when fetch_server_config fails
  - Test 3: MCPAuth instance has metadata_route() returning a Starlette Route
  - Test 4: MCPAuth instance has bearer_auth_middleware() returning a callable class

All tests use mocks — no real HTTP calls to Auth0.
"""
import pytest
from unittest.mock import patch, MagicMock

from auth.oauth import build_mcp_auth


FAKE_DOMAIN = "test-tenant.auth0.com"
FAKE_RESOURCE_URL = "https://mcp.example.com"


@patch("auth.oauth.fetch_server_config")
def test_build_mcp_auth_success(mock_fetch):
    """build_mcp_auth returns an MCPAuth instance when fetch_server_config succeeds."""
    from mcpauth.config import AuthServerType, AuthServerConfig, AuthorizationServerMetadata

    # Provide a valid AuthServerConfig so MCPAuth.__init__ passes validation
    meta = AuthorizationServerMetadata(
        issuer=f"https://{FAKE_DOMAIN}/",
        authorization_endpoint=f"https://{FAKE_DOMAIN}/authorize",
        token_endpoint=f"https://{FAKE_DOMAIN}/oauth/token",
        jwks_uri=f"https://{FAKE_DOMAIN}/.well-known/jwks.json",
        response_types_supported=["code"],
        code_challenge_methods_supported=["S256"],
    )
    mock_fetch.return_value = AuthServerConfig(metadata=meta, type=AuthServerType.OIDC)

    result = build_mcp_auth(FAKE_DOMAIN, FAKE_RESOURCE_URL)

    # Verify fetch was called with correct Auth0 URL and OIDC type
    mock_fetch.assert_called_once_with(
        f"https://{FAKE_DOMAIN}",
        AuthServerType.OIDC,
    )

    # Verify result is an MCPAuth instance
    from mcpauth import MCPAuth
    assert isinstance(result, MCPAuth)


@patch("auth.oauth.fetch_server_config")
def test_build_mcp_auth_fetch_failure(mock_fetch):
    """build_mcp_auth propagates exception when Auth0 is unreachable."""
    mock_fetch.side_effect = ConnectionError("Auth0 unreachable")

    with pytest.raises(ConnectionError, match="Auth0 unreachable"):
        build_mcp_auth(FAKE_DOMAIN, FAKE_RESOURCE_URL)


@patch("auth.oauth.fetch_server_config")
def test_mcp_auth_has_metadata_route(mock_fetch):
    """MCPAuth instance from build_mcp_auth has a metadata_route() returning a Starlette Route."""
    from mcpauth.config import AuthServerType, AuthServerConfig, AuthorizationServerMetadata
    from starlette.routing import Route

    meta = AuthorizationServerMetadata(
        issuer=f"https://{FAKE_DOMAIN}/",
        authorization_endpoint=f"https://{FAKE_DOMAIN}/authorize",
        token_endpoint=f"https://{FAKE_DOMAIN}/oauth/token",
        jwks_uri=f"https://{FAKE_DOMAIN}/.well-known/jwks.json",
        response_types_supported=["code"],
        code_challenge_methods_supported=["S256"],
    )
    mock_fetch.return_value = AuthServerConfig(metadata=meta, type=AuthServerType.OIDC)

    mcp_auth = build_mcp_auth(FAKE_DOMAIN, FAKE_RESOURCE_URL)

    route = mcp_auth.metadata_route()
    assert isinstance(route, Route)
    assert route.path is not None
    assert "well-known" in route.path


@patch("auth.oauth.fetch_server_config")
def test_mcp_auth_has_bearer_auth_middleware(mock_fetch):
    """MCPAuth instance from build_mcp_auth has a callable bearer_auth_middleware()."""
    from mcpauth.config import AuthServerType, AuthServerConfig, AuthorizationServerMetadata
    from starlette.middleware.base import BaseHTTPMiddleware

    meta = AuthorizationServerMetadata(
        issuer=f"https://{FAKE_DOMAIN}/",
        authorization_endpoint=f"https://{FAKE_DOMAIN}/authorize",
        token_endpoint=f"https://{FAKE_DOMAIN}/oauth/token",
        jwks_uri=f"https://{FAKE_DOMAIN}/.well-known/jwks.json",
        response_types_supported=["code"],
        code_challenge_methods_supported=["S256"],
    )
    mock_fetch.return_value = AuthServerConfig(metadata=meta, type=AuthServerType.OIDC)

    mcp_auth = build_mcp_auth(FAKE_DOMAIN, FAKE_RESOURCE_URL)

    middleware = mcp_auth.bearer_auth_middleware("jwt", audience=FAKE_RESOURCE_URL)
    assert middleware is not None
    # bearer_auth_middleware returns a class (type), not an instance
    assert isinstance(middleware, type)
    assert issubclass(middleware, BaseHTTPMiddleware)
