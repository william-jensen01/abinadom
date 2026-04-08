"""
Algorithm-agnostic JWT verification via PyJWT + Auth0 JWKS.

Inspects the JWT header to determine the signing algorithm, then verifies
using the appropriate key material:
  - JWE (4 dots, alg=dir, enc=A256GCM): decrypt with AUTH0_CLIENT_SECRET,
    then verify the inner signed JWT.
  - Asymmetric (RS256/RS384/RS512/PS256/PS384/PS512/ES256/ES384/ES512):
    Fetch public key from Auth0 JWKS endpoint via PyJWKClient.
  - Symmetric (HS256/HS384/HS512): Verify with AUTH0_CLIENT_SECRET env var.
  - none / unknown: Reject with 401.

Design decisions:
  D-01: Auth0 is the Authorization Server.
  D-02: MCP server is a pure Resource Server.
  D-08: Static bearer token auth dropped -- Auth0 JWT only.
"""
import base64
import json
import logging

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


def _b64d(s: str) -> bytes:
    """Base64url-decode a string, adding padding as needed."""
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class JWKSVerifier:
    """Algorithm-agnostic JWT verifier using PyJWT and Auth0 JWKS.

    Transparently handles JWE (encrypted) tokens by decrypting them first,
    then verifies the inner signed JWT via JWKS or HMAC.
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
            client_secret: Optional client secret. Used for HMAC (HS*) token
                verification and for decrypting JWE tokens (alg=dir).
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
          1. Detect JWE (4 dots) and decrypt to a signed inner JWT.
          2. Inspect the (inner) JWT header to read the signing algorithm.
          3. Route to asymmetric (JWKS) or symmetric (client secret) path.
          4. Return the decoded payload on success, None on any error.

        Returns:
            Decoded payload dict on success, None on invalid/expired/unknown.
        """
        # JWE compact has 5 segments (4 dots); JWS compact has 3 segments (2 dots).
        if token.count(".") == 4:
            token = self._decrypt_jwe(token)
            if token is None:
                return None

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
            logger.warning("JWT rejected: unsupported algorithm %r", alg)
            return None

    def _decrypt_jwe(self, token: str) -> str | None:
        """Decrypt a JWE compact token (alg=dir, enc=A256GCM).

        Auth0 DCR-registered clients receive tokens encrypted with the
        client secret as the direct content encryption key (CEK).

        RFC 7516 compact serialization:
          BASE64URL(header) . BASE64URL(encrypted_key) . BASE64URL(iv)
              . BASE64URL(ciphertext) . BASE64URL(tag)

        For alg=dir, encrypted_key is empty and the CEK is
        base64url_decode(client_secret).

        Returns the decrypted plaintext (a signed JWT string), or None.
        """
        if not self._client_secret:
            logger.warning("JWE token received but AUTH0_CLIENT_SECRET not configured")
            return None

        try:
            parts = token.split(".")
            if len(parts) != 5:
                logger.warning("JWE: expected 5 segments, got %d", len(parts))
                return None

            protected_b64, _encrypted_key, iv_b64, ciphertext_b64, tag_b64 = parts

            header = json.loads(_b64d(protected_b64))
            alg = header.get("alg")
            enc = header.get("enc")

            if alg != "dir":
                logger.warning("JWE: unsupported alg %r (only 'dir' supported)", alg)
                return None
            if enc != "A256GCM":
                logger.warning("JWE: unsupported enc %r (only 'A256GCM' supported)", enc)
                return None

            iv = _b64d(iv_b64)
            ciphertext = _b64d(ciphertext_b64)
            tag = _b64d(tag_b64)

            # CEK = base64url-decoded client secret (must be 32 bytes for A256GCM)
            key = _b64d(self._client_secret)
            if len(key) != 32:
                import hashlib
                logger.warning(
                    "JWE: client_secret decodes to %d bytes (expected 32); "
                    "falling back to SHA-256 hash",
                    len(key),
                )
                key = hashlib.sha256(self._client_secret.encode()).digest()

            # AAD for AES-GCM in JWE = ASCII bytes of the protected header b64url string
            aad = protected_b64.encode("ascii")

            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            aesgcm = AESGCM(key)
            # cryptography's AESGCM.decrypt expects ciphertext + tag concatenated
            plaintext = aesgcm.decrypt(iv, ciphertext + tag, aad)
            inner_token = plaintext.decode("utf-8")
            logger.debug("JWE decrypted successfully (enc=A256GCM), inner token len=%d", len(inner_token))
            return inner_token

        except Exception as exc:
            logger.warning("JWE decryption failed: %s", exc)
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
