"""
Unit tests for auth.oauth — JWKSVerifier (kid-based JWT routing).

Covers:
  1.  test_verify_rs256_valid                          -- RS256 with kid routes to JWKS
  2.  test_verify_es256_valid                          -- ES256 with kid routes to JWKS
  3.  test_verify_none_rejected                        -- alg=none, no kid → /userinfo rejects
  4.  test_verify_unknown_alg_rejected                 -- alg=FAKE, no kid → /userinfo rejects
  5.  test_verify_expired_rejected                     -- RS256 with kid, expired → JWKS rejects
  6.  test_verify_wrong_audience_rejected              -- RS256 with kid, wrong aud → JWKS rejects
  7.  test_verify_wrong_issuer_rejected                -- RS256 with kid, wrong iss → JWKS rejects
  8.  test_verify_hs256_routes_to_userinfo             -- HS256, no kid → /userinfo validates
  9.  test_verify_hs256_no_userinfo_rejected           -- HS256, no kid → /userinfo rejects
  10. test_verify_jwe_routes_to_userinfo               -- JWE (4 dots) → /userinfo validates
  11. test_verify_jwe_userinfo_rejected                -- JWE (4 dots) → /userinfo rejects
  12. test_verify_jwe_userinfo_error                   -- JWE (4 dots) → /userinfo network error
  13. test_verify_rs256_without_kid_routes_to_userinfo -- RS256 without kid → /userinfo
  14. test_verify_hs256_with_kid_routes_to_jwks        -- HS256 with kid → JWKS path

All tests avoid real HTTP calls to Auth0. RSA/EC key generation uses the
cryptography library (already installed as a PyJWT[crypto] dependency).
"""
import base64
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


def _mock_userinfo_response(status_code: int, body: dict):
    """Return a mock httpx Response with given status code and JSON body."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = body
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_verify_rs256_valid(rsa_private_key):
    """RS256-signed JWT with kid routes to JWKS and returns the decoded payload."""
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
    """ES256-signed JWT with kid routes to JWKS and returns the decoded payload."""
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
    """JWT with alg=none and no kid routes to /userinfo; /userinfo rejects it."""
    verifier = _make_verifier()

    # PyJWT refuses to encode with alg=none by default; craft a raw token
    import base64, json as _json

    def _b64(data):
        return base64.urlsafe_b64encode(_json.dumps(data).encode()).rstrip(b"=").decode()

    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"sub": "bad", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER})
    token = f"{header}.{payload}."

    mock_resp = _mock_userinfo_response(401, {"error": "invalid_token"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is None


def test_verify_unknown_alg_rejected():
    """JWT with an unknown algorithm string and no kid routes to /userinfo; /userinfo rejects it."""
    verifier = _make_verifier()

    import base64, json as _json

    def _b64(data):
        return base64.urlsafe_b64encode(_json.dumps(data).encode()).rstrip(b"=").decode()

    header = _b64({"alg": "FAKE", "typ": "JWT"})
    payload = _b64({"sub": "bad"})
    token = f"{header}.{payload}.invalidsig"

    mock_resp = _mock_userinfo_response(401, {"error": "invalid_token"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is None


def test_verify_expired_rejected(rsa_private_key):
    """Expired JWT with kid routes to JWKS; JWKS rejects expired token."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user3", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) - 60},
        rsa_private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_wrong_audience_rejected(rsa_private_key):
    """JWT with kid but wrong audience routes to JWKS; JWKS rejects wrong aud."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user4", "aud": "https://wrong-audience.com", "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_wrong_issuer_rejected(rsa_private_key):
    """JWT with kid but wrong issuer routes to JWKS; JWKS rejects wrong iss."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user5", "aud": FAKE_AUDIENCE, "iss": "https://evil.example.com/", "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )

    verifier._jwks_client.get_signing_key_from_jwt.return_value = _mock_signing_key(
        rsa_private_key.public_key()
    )

    result = verifier.verify_token(token)
    assert result is None


def test_verify_hs256_routes_to_userinfo():
    """HS256 JWT without kid routes to /userinfo; /userinfo returns payload."""
    verifier = _make_verifier()

    token = jwt.encode(
        {"sub": "user6", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        "any-secret",
        algorithm="HS256",
    )

    mock_resp = _mock_userinfo_response(200, {"sub": "user6"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "user6"


def test_verify_hs256_no_userinfo_rejected():
    """HS256 JWT without kid routes to /userinfo; /userinfo rejects returns None."""
    verifier = _make_verifier(client_secret=None)

    token = jwt.encode(
        {"sub": "user7", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        "some-secret-key-for-testing-abcd",
        algorithm="HS256",
    )

    mock_resp = _mock_userinfo_response(401, {"error": "invalid_token"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is None


# ---------------------------------------------------------------------------
# JWE tests — all route to /userinfo (kid-based routing, JWE detection preserved)
# ---------------------------------------------------------------------------


def _make_jwe_token(inner_jwt: str, key_bytes: bytes) -> str:
    """Build a minimal JWE compact token (alg=dir, enc=A256GCM) for testing."""
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    header = base64.urlsafe_b64encode(
        b'{"alg":"dir","enc":"A256GCM"}'
    ).rstrip(b"=").decode()
    encrypted_key = ""  # empty for alg=dir
    iv = os.urandom(12)
    iv_b64 = base64.urlsafe_b64encode(iv).rstrip(b"=").decode()
    aad = header.encode("ascii")
    aesgcm = AESGCM(key_bytes)
    ct_and_tag = aesgcm.encrypt(iv, inner_jwt.encode(), aad)
    # cryptography returns ciphertext+tag concatenated; split off last 16 bytes as tag
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    ct_b64 = base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode()
    tag_b64 = base64.urlsafe_b64encode(tag).rstrip(b"=").decode()
    return f"{header}.{encrypted_key}.{iv_b64}.{ct_b64}.{tag_b64}"


def test_verify_jwe_routes_to_userinfo(rsa_private_key):
    """JWE token (4 dots) routes to /userinfo for server-side validation."""
    raw_key = b"testjwekey0123456789abcdefghijkl"  # exactly 32 bytes
    client_secret = base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode()
    verifier = _make_verifier(client_secret=client_secret)

    inner_jwt = jwt.encode(
        {"sub": "jwe-user", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
    )
    token = _make_jwe_token(inner_jwt, raw_key)

    mock_resp = _mock_userinfo_response(200, {"sub": "jwe-user"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "jwe-user"


def test_verify_jwe_userinfo_rejected(rsa_private_key):
    """JWE token routes to /userinfo; /userinfo rejects returns None."""
    raw_key = b"testjwekey0123456789abcdefghijkl"
    verifier = _make_verifier(client_secret=None)

    inner_jwt = jwt.encode(
        {"sub": "jwe-user2", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
    )
    token = _make_jwe_token(inner_jwt, raw_key)

    mock_resp = _mock_userinfo_response(401, {"error": "invalid_token"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is None


def test_verify_jwe_userinfo_error(rsa_private_key):
    """JWE token routes to /userinfo; network error returns None."""
    raw_key = b"wrongkey0123456789abcdefghijklmn"
    wrong_secret = base64.urlsafe_b64encode(raw_key).rstrip(b"=").decode()
    verifier = _make_verifier(client_secret=wrong_secret)

    inner_jwt = jwt.encode(
        {"sub": "jwe-user3", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
    )
    token = _make_jwe_token(inner_jwt, raw_key)

    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.side_effect = Exception("network error")
        result = verifier.verify_token(token)
    assert result is None


# ---------------------------------------------------------------------------
# New tests: explicit kid-routing coverage
# ---------------------------------------------------------------------------


def test_verify_rs256_without_kid_routes_to_userinfo(rsa_private_key):
    """RS256 token WITHOUT kid header routes to /userinfo (kid-based routing)."""
    verifier = _make_verifier()
    # Encode RS256 token without kid header
    token = jwt.encode(
        {"sub": "user-no-kid", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        rsa_private_key,
        algorithm="RS256",
        # Deliberately NO kid header
    )
    mock_resp = _mock_userinfo_response(200, {"sub": "user-no-kid"})
    with patch("auth.oauth.httpx.Client") as MockClient:
        MockClient.return_value.__enter__.return_value.get.return_value = mock_resp
        result = verifier.verify_token(token)
    assert result is not None
    assert result["sub"] == "user-no-kid"


def test_verify_hs256_with_kid_routes_to_jwks():
    """HS256 token WITH kid header routes to JWKS (kid-based routing)."""
    verifier = _make_verifier()
    # HS256 with kid — kid presence means JWKS path, which will fail
    # (no real JWKS endpoint) and return None
    token = jwt.encode(
        {"sub": "user-hs-kid", "aud": FAKE_AUDIENCE, "iss": FAKE_ISSUER, "exp": int(time.time()) + 300},
        "any-secret",
        algorithm="HS256",
        headers={"kid": "unexpected-kid"},
    )
    # JWKS lookup will fail (mock raises), so verify_token returns None
    verifier._jwks_client.get_signing_key_from_jwt.side_effect = Exception("key not found")
    result = verifier.verify_token(token)
    assert result is None
