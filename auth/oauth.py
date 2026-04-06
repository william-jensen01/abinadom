"""
OAuth 2.1 token verification for Auth0-issued JWTs.

Auth0JWTVerifier validates JWTs against Auth0's JWKS endpoint (RS256).
DualTokenVerifier composes JWT + static bearer token validation (D-08).

Design decisions (from 16.1-CONTEXT.md):
  D-01: Auth0 is the Authorization Server.
  D-02: MCP server is a pure Resource Server.
  D-08: Both OAuth JWTs and static bearer tokens must be accepted.
  D-11: Token lifetime managed by Auth0, not by server code.
"""
import logging

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken

from auth.store import KeyStore

logger = logging.getLogger(__name__)


class Auth0JWTVerifier:
    """Validates Auth0-issued JWTs against the Auth0 JWKS endpoint (RS256).

    Uses PyJWKClient to fetch and cache Auth0's public keys, then validates
    the JWT signature, audience, and issuer on each call.

    Pitfall 1 (from research): The issuer URL MUST have a trailing slash to
    match Auth0's token claims (e.g. "https://tenant.auth0.com/", not
    "https://tenant.auth0.com").
    """

    def __init__(self, domain: str, audience: str) -> None:
        """Initialize with Auth0 domain and expected audience.

        Args:
            domain: Auth0 tenant domain (e.g. "my-tenant.auth0.com").
            audience: Expected JWT audience (e.g. "https://mcp.example.com").
        """
        self._audience = audience
        self._issuer = f"https://{domain}/"  # Trailing slash required (Pitfall 1)
        self._jwks_client = PyJWKClient(
            f"https://{domain}/.well-known/jwks.json",
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate an RS256 JWT and return an AccessToken, or None on any failure.

        Fetches the signing key from Auth0's JWKS endpoint (cached), then
        decodes and validates the JWT (signature, audience, issuer, expiry).

        Args:
            token: Raw bearer token string from the Authorization header.

        Returns:
            AccessToken if the JWT is valid and verified, None otherwise.
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
            return AccessToken(
                token=token,
                client_id=payload.get("sub", "unknown"),
                scopes=payload.get("scope", "").split(),
            )
        except jwt.exceptions.PyJWTError as exc:
            logger.debug("JWT validation failed (PyJWTError): %s", exc)
            return None
        except Exception as exc:
            logger.warning("JWT validation failed (unexpected error): %s", exc)
            return None


class DualTokenVerifier:
    """Composite token verifier that supports both OAuth JWTs and static bearer tokens.

    Implements D-08: both OAuth (Auth0 JWT) and static bearer tokens (Phase 14
    SqliteKeyStore) must be accepted. JWT validation is tried first; if it
    fails (returns None), falls back to the static token store.

    This class implements the TokenVerifier protocol expected by the MCP server:
        async def verify_token(self, token: str) -> AccessToken | None
    """

    def __init__(self, jwt_verifier: Auth0JWTVerifier, store: KeyStore) -> None:
        """Initialize with an Auth0JWTVerifier and a KeyStore for static tokens.

        Args:
            jwt_verifier: Auth0JWTVerifier instance for OAuth JWT validation.
            store: KeyStore implementation (typically SqliteKeyStore) for
                   static bearer token fallback.
        """
        self._jwt = jwt_verifier
        self._store = store

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate a token via JWT first, then static bearer token fallback.

        Auth path (D-08):
          1. Try JWT validation (Auth0 RS256). On success, return AccessToken.
          2. If JWT fails, try static bearer token via KeyStore. On success,
             return AccessToken with client_id=key_name and empty scopes.
          3. If both fail, return None.

        Args:
            token: Raw bearer token string from the Authorization header.

        Returns:
            AccessToken if either verification path succeeds, None otherwise.
        """
        # Path 1: JWT validation (Auth0)
        result = await self._jwt.verify_token(token)
        if result is not None:
            return result

        # Path 2: Static bearer token fallback (Phase 14 SqliteKeyStore)
        key_name = self._store.verify_token(token)
        if key_name is not None:
            return AccessToken(token=token, client_id=key_name, scopes=[])

        return None
