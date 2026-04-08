"""
Algorithm-agnostic JWT verification via PyJWT + Auth0 JWKS.

Inspects the JWT header to determine the signing algorithm, then verifies
using the appropriate key material:
  - Asymmetric (RS256/RS384/RS512/PS256/PS384/PS512/ES256/ES384/ES512):
    Fetch public key from Auth0 JWKS endpoint via PyJWKClient.
  - Symmetric (HS256/HS384/HS512): Verify with AUTH0_CLIENT_SECRET env var.
  - none / unknown: Reject with 401.

Design decisions:
  D-01: Auth0 is the Authorization Server.
  D-02: MCP server is a pure Resource Server.
  D-08: Static bearer token auth dropped -- Auth0 JWT only.
"""
import logging

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


class JWKSVerifier:
    """Algorithm-agnostic JWT verifier using PyJWT and Auth0 JWKS.

    Inspects the JWT header to select the verification algorithm, then
    verifies using either the Auth0 JWKS public key (asymmetric) or the
    client secret (symmetric HMAC). Rejects alg=none and unknown algorithms.
    """

    ASYMMETRIC_ALGORITHMS = [
        "RS256", "RS384", "RS512",
        "PS256", "PS384", "PS512",
        "ES256", "ES384", "ES512",
    ]
    SYMMETRIC_ALGORITHMS = ["HS256", "HS384", "HS512"]

    def __init__(
        self,
        domain: str,
        audience: str,
        client_secret: str | None = None,
    ) -> None:
        """Initialize the verifier.

        Args:
            domain: Auth0 tenant domain, e.g. "my-tenant.auth0.com".
            audience: Expected JWT audience (the MCP server's public URL).
            client_secret: Optional client secret for HMAC (HS*) token
                verification. If None, HS* tokens are rejected.
        """
        self._issuer = f"https://{domain}/"
        self._audience = audience
        self._client_secret = client_secret
        jwks_uri = f"https://{domain}/.well-known/jwks.json"
        # PyJWKClient caches keys with a 300 s TTL and auto-refreshes on
        # unknown kid — no per-request network call in the common case.
        self._jwks_client = PyJWKClient(jwks_uri)

    def verify_token(self, token: str) -> dict | None:
        """Verify a JWT and return its decoded payload, or None on failure.

        Steps:
          1. Inspect the unverified header to read the algorithm.
          2. Route to asymmetric (JWKS) or symmetric (client secret) path.
          3. Return the decoded payload on success, None on any error.

        Returns:
            Decoded payload dict on success, None on invalid/expired/unknown.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            logger.warning("JWT header decode failed: %s", exc)
            return None

        alg = header.get("alg", "")

        if alg in self.ASYMMETRIC_ALGORITHMS:
            return self._verify_asymmetric(token, alg)
        elif alg in self.SYMMETRIC_ALGORITHMS:
            return self._verify_symmetric(token, alg)
        else:
            # Reject alg=none and all unknown algorithms
            logger.warning("JWT rejected: unsupported algorithm %r", alg)
            return None

    def _verify_asymmetric(self, token: str, alg: str) -> dict | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
            )
            return payload
        except jwt.PyJWTError as exc:
            logger.warning("JWT asymmetric verification failed: %s", exc)
            return None

    def _verify_symmetric(self, token: str, alg: str) -> dict | None:
        if self._client_secret is None:
            logger.warning(
                "JWT rejected: HMAC algorithm %r but no client_secret configured",
                alg,
            )
            return None
        try:
            payload = jwt.decode(
                token,
                self._client_secret,
                algorithms=[alg],
                audience=self._audience,
                issuer=self._issuer,
            )
            return payload
        except jwt.PyJWTError as exc:
            logger.warning("JWT symmetric verification failed: %s", exc)
            return None
