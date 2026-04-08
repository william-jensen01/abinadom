"""
Unit tests for auth.oauth — JWKSVerifier (algorithm-agnostic JWT verification).

Covers:
  1. test_verify_rs256_valid        -- RS256 signed JWT returns decoded payload
  2. test_verify_es256_valid        -- ES256 signed JWT returns decoded payload
  3. test_verify_none_rejected      -- JWT with alg=none returns None
  4. test_verify_unknown_alg_rejected -- JWT with alg="FAKE" returns None
  5. test_verify_expired_rejected   -- Expired JWT returns None
  6. test_verify_wrong_audience_rejected -- Wrong aud returns None
  7. test_verify_wrong_issuer_rejected   -- Wrong iss returns None
  8. test_verify_hs256_with_secret  -- HS256 JWT with correct secret returns payload
  9. test_verify_hs256_without_secret_rejected -- HS256 with no client_secret returns None

All tests avoid real HTTP calls to Auth0. RSA/EC key generation uses the
cryptography library (already installed as a PyJWT[crypto] dependency).
"""
import time
import pytest
from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend

from auth.oauth import JWKSVerifier


FAKE_DOMAIN = "test-tenant.auth0.com"
FAKE_AUDIENCE = "https://mcp.example.com"
FAKE_ISSUER = f"https://{FAKE_DOMAIN}/"


# ---------------------------------------------------------------------------
# Key fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_private_key():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )


@pytest.fixture(scope="module")
def ec_private_key():
    return ec.generate_private_key(ec.SECP256R1(), default_backend())


def _make_verifier(client_secret=None):
    """Build a JWKSVerifier with JWKS fetching disabled (mocked at the class level)."""
    with patch("auth.oauth.PyJWKClient"):
        verifier = JWKSVerifier(
            domain=FAKE_DOMAIN,
            audience=FAKE_AUDIENCE,
            client_secret=client_secret,
        )
    return verifier


def _mock_signing_key(public_key):
    """Return a mock signing key object with .key = public_key."""
    mock_key = MagicMock()
    mock_key.key = public_key
    return mock_key


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_verify_rs256_valid(rsa_private_key):
    """RS256-signed JWT with correct aud/iss returns the decoded payload."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user1", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "user1"


def test_verify_es256_valid(ec_private_key):
    """ES256-signed JWT with correct aud/iss returns the decoded payload."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user2", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        ec_private_key,
        algorithm="ES256",
        headers={"kid": "test-ec-key"},
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        ec_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "user2"


def test_verify_none_rejected():
    """JWT with alg=none must be rejected (returns None)."""
    verifier = _make_verifier()

    # PyJWT refuses to encode with alg=none by default; craft a raw token
    import base64, json as _json

    def _b64(data):
        return base64.urlsafe_b64encode(_json.dumps(data).encode()).rstrip(b"=").decode()

    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"sub": "bad", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER})
    token = f"{header}.{payload}."

    result = verifier.verify_token(token)
    assert result is None


def test_verify_unknown_alg_rejected():
    """JWT with an unknown algorithm string returns None."""
    verifier = _make_verifier()

    import base64, json as _json

    def _b64(data):
        return base64.urlsafe_b64encode(_json.dumps(data).encode()).rstrip(b"=").decode()

    header = _b64({"alg": "FAKE", "typ": "JWT"})
    payload = _b64({"sub": "bad"})
    token = f"{header}.{payload}.invalidsig"

    result = verifier.verify_token(token)
    assert result is None


def test_verify_expired_rejected(rsa_private_key):
    """Expired JWT returns None."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user3", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) - 60},
        rsa_private_key,
        algorithm="RS256",
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_wrong_audience_rejected(rsa_private_key):
    """JWT with wrong audience returns None."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user4", "aud": "https://wrong-audience.com", "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_wrong_issuer_rejected(rsa_private_key):
    """JWT with wrong issuer returns None."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user5", "aud": FAKE_AUDIENCE, "iss": "https://evil.example.com/", "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_hs256_with_secret():
    """HS256 JWT with correct client_secret returns decoded payload."""
    secret = "super-secret-key-for-testing-abc"  # 32 bytes
    verifier = _make_verifier(client_secret=secret)

    token = jwt.encode(
        {"sub": "user6", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        secret,
        algorithm="HS256",
    )

    result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "user6"


def test_verify_hs256_without_secret_rejected():
    """HS256 JWT when no client_secret configured returns None."""
    verifier = _make_verifier(client_secret=None)

    secret = "some-secret-key-for-testing-abcd"  # 32 bytes
    token = jwt.encode(
        {"sub": "user7", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        secret,
        algorithm="HS256",
    )

    result = verifier.verify_token(token)
    assert result is None
