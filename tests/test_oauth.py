"""
Unit tests for auth.oauth — Auth0JWTVerifier and DualTokenVerifier.

Covers:
  - Test 1: Auth0JWTVerifier.verify_token returns AccessToken for valid RS256 JWT
  - Test 2: Auth0JWTVerifier.verify_token returns None for expired JWT
  - Test 3: Auth0JWTVerifier.verify_token returns None for JWT with wrong audience
  - Test 4: Auth0JWTVerifier.verify_token returns None for JWT with wrong issuer
  - Test 5: Auth0JWTVerifier.verify_token returns None for malformed token string
  - Test 6: DualTokenVerifier.verify_token returns AccessToken when JWT is valid
  - Test 7: DualTokenVerifier.verify_token falls back to static token on JWT failure
  - Test 8: DualTokenVerifier.verify_token returns None when both JWT and static token fail
  - Test 9: Auth0JWTVerifier.__init__ constructs PyJWKClient with correct JWKS URL and cache settings

All tests use mocks — no real HTTP calls to Auth0.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from auth.oauth import Auth0JWTVerifier, DualTokenVerifier
from auth.store import SqliteKeyStore
from mcp.server.auth.provider import AccessToken


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_DOMAIN = "test-tenant.auth0.com"
FAKE_AUDIENCE = "https://mcp.example.com"
FAKE_ISSUER = f"https://{FAKE_DOMAIN}/"
FAKE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.fake.token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def verifier():
    """Auth0JWTVerifier with mocked PyJWKClient."""
    with patch("auth.oauth.PyJWKClient") as mock_jwks_cls:
        mock_jwks_client = MagicMock()
        mock_jwks_cls.return_value = mock_jwks_client
        v = Auth0JWTVerifier(domain=FAKE_DOMAIN, audience=FAKE_AUDIENCE)
        v._jwks_client = mock_jwks_client
        yield v, mock_jwks_client


# ---------------------------------------------------------------------------
# Test 1: Valid RS256 JWT returns AccessToken
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_valid_jwt(verifier):
    """verify_token returns AccessToken with correct client_id and scopes for a valid JWT."""
    v, mock_jwks_client = verifier

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-public-key"
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    payload = {
        "sub": "auth0|user123",
        "scope": "read write",
        "aud": FAKE_AUDIENCE,
        "iss": FAKE_ISSUER,
    }

    with patch("auth.oauth.jwt.decode", return_value=payload):
        result = await v.verify_token(FAKE_TOKEN)

    assert result is not None
    assert isinstance(result, AccessToken)
    assert result.token == FAKE_TOKEN
    assert result.client_id == "auth0|user123"
    assert result.scopes == ["read", "write"]


# ---------------------------------------------------------------------------
# Test 2: Expired JWT returns None
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_expired_jwt(verifier):
    """verify_token returns None for an expired JWT (ExpiredSignatureError)."""
    import jwt as pyjwt

    v, mock_jwks_client = verifier

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-public-key"
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch("auth.oauth.jwt.decode", side_effect=pyjwt.exceptions.ExpiredSignatureError("expired")):
        result = await v.verify_token(FAKE_TOKEN)

    assert result is None


# ---------------------------------------------------------------------------
# Test 3: Wrong audience returns None
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_wrong_audience(verifier):
    """verify_token returns None for a JWT with wrong audience (InvalidAudienceError)."""
    import jwt as pyjwt

    v, mock_jwks_client = verifier

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-public-key"
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch("auth.oauth.jwt.decode", side_effect=pyjwt.exceptions.InvalidAudienceError("wrong audience")):
        result = await v.verify_token(FAKE_TOKEN)

    assert result is None


# ---------------------------------------------------------------------------
# Test 4: Wrong issuer returns None
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_wrong_issuer(verifier):
    """verify_token returns None for a JWT with wrong issuer (InvalidIssuerError)."""
    import jwt as pyjwt

    v, mock_jwks_client = verifier

    mock_signing_key = MagicMock()
    mock_signing_key.key = "fake-public-key"
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    with patch("auth.oauth.jwt.decode", side_effect=pyjwt.exceptions.InvalidIssuerError("wrong issuer")):
        result = await v.verify_token(FAKE_TOKEN)

    assert result is None


# ---------------------------------------------------------------------------
# Test 5: Malformed token returns None
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_malformed_token(verifier):
    """verify_token returns None for a malformed token string (DecodeError)."""
    import jwt as pyjwt

    v, mock_jwks_client = verifier

    mock_jwks_client.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.DecodeError("malformed")

    result = await v.verify_token("not.a.valid.jwt.at.all")

    assert result is None


# ---------------------------------------------------------------------------
# Test 6: DualTokenVerifier — JWT path (store not called)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_dual_jwt_path(tmp_path):
    """DualTokenVerifier returns AccessToken when JWT is valid; SqliteKeyStore not called."""
    db_path = str(tmp_path / "auth.db")
    store = SqliteKeyStore(db_path)

    mock_jwt_verifier = MagicMock(spec=Auth0JWTVerifier)
    expected_token = AccessToken(token=FAKE_TOKEN, client_id="auth0|user123", scopes=["read"])
    mock_jwt_verifier.verify_token = AsyncMock(return_value=expected_token)

    dual = DualTokenVerifier(jwt_verifier=mock_jwt_verifier, store=store)
    result = await dual.verify_token(FAKE_TOKEN)

    assert result is not None
    assert result.client_id == "auth0|user123"
    assert result.scopes == ["read"]
    mock_jwt_verifier.verify_token.assert_called_once_with(FAKE_TOKEN)


# ---------------------------------------------------------------------------
# Test 7: DualTokenVerifier — static token fallback when JWT fails
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_dual_static_fallback(tmp_path):
    """DualTokenVerifier falls back to SqliteKeyStore when JWT verification fails."""
    db_path = str(tmp_path / "auth.db")
    store = SqliteKeyStore(db_path)
    raw_token = store.create_key("test-key")

    mock_jwt_verifier = MagicMock(spec=Auth0JWTVerifier)
    mock_jwt_verifier.verify_token = AsyncMock(return_value=None)

    dual = DualTokenVerifier(jwt_verifier=mock_jwt_verifier, store=store)
    result = await dual.verify_token(raw_token)

    assert result is not None
    assert isinstance(result, AccessToken)
    assert result.client_id == "test-key"
    assert result.scopes == []


# ---------------------------------------------------------------------------
# Test 8: DualTokenVerifier — both fail returns None
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_dual_both_fail(tmp_path):
    """DualTokenVerifier returns None when both JWT and static token fail."""
    db_path = str(tmp_path / "auth.db")
    store = SqliteKeyStore(db_path)

    mock_jwt_verifier = MagicMock(spec=Auth0JWTVerifier)
    mock_jwt_verifier.verify_token = AsyncMock(return_value=None)

    dual = DualTokenVerifier(jwt_verifier=mock_jwt_verifier, store=store)
    result = await dual.verify_token("completely-invalid-token")

    assert result is None


# ---------------------------------------------------------------------------
# Test 9: Auth0JWTVerifier.__init__ builds PyJWKClient with correct params
# ---------------------------------------------------------------------------


def test_jwks_client_init():
    """Auth0JWTVerifier.__init__ constructs PyJWKClient with correct JWKS URL and cache settings."""
    with patch("auth.oauth.PyJWKClient") as mock_jwks_cls:
        mock_jwks_cls.return_value = MagicMock()
        v = Auth0JWTVerifier(domain=FAKE_DOMAIN, audience=FAKE_AUDIENCE)

    # Check the JWKS URL contains the domain and .well-known path
    call_args = mock_jwks_cls.call_args
    assert call_args is not None
    url_arg = call_args[0][0] if call_args[0] else call_args[1].get("uri", call_args[1].get("url", ""))
    # PyJWKClient positional first arg is the JWKS URI
    expected_url = f"https://{FAKE_DOMAIN}/.well-known/jwks.json"
    assert expected_url in str(call_args), f"Expected JWKS URL {expected_url!r} in call args {call_args}"

    # Check cache settings
    kwargs = call_args[1]
    assert kwargs.get("cache_jwk_set") is True, f"Expected cache_jwk_set=True, got {kwargs}"
    assert kwargs.get("lifespan") == 300, f"Expected lifespan=300, got {kwargs}"

    # Check issuer is set with trailing slash
    assert v._issuer == FAKE_ISSUER
    assert v._issuer.endswith("/")
