import hashlib
from base64 import urlsafe_b64encode
from urllib.parse import urlparse, parse_qs

import pytest

import app as app_module
from app import app


def _pkce_pair():
    """Return a (code_verifier, S256 code_challenge) pair."""
    verifier = "verifier-" + "a" * 43
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def session_client():
    """Create a test client with session support"""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"
    with app.test_client() as client:
        yield client


class TestHealthEndpoint:
    """Test the health check endpoint"""

    def test_health_endpoint_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json == {"status": "ok"}


class TestOpenIDConfiguration:
    """Test OpenID Connect discovery endpoint"""

    def test_openid_configuration_returns_correct_structure(self, client):
        response = client.get("/.well-known/openid-configuration")
        assert response.status_code == 200
        data = response.json

        assert "issuer" in data
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "userinfo_endpoint" in data
        assert "code" in data["response_types_supported"]
        assert "token" in data["response_types_supported"]


class TestAuthorizeEndpoint:
    """Test the OAuth2 authorization endpoint"""

    def test_authorize_requires_client_id(self, client):
        response = client.get("/authorize?redirect_uri=http://localhost/callback")
        assert response.status_code == 400
        assert b"Missing required parameters" in response.data

    def test_authorize_requires_redirect_uri(self, client):
        response = client.get("/authorize?client_id=test-client")
        assert response.status_code == 400
        assert b"Missing required parameters" in response.data

    def test_authorize_displays_login_page(self, client):
        response = client.get(
            "/authorize?client_id=test-client&redirect_uri=http://localhost/callback"
        )
        assert response.status_code == 200
        assert b"Mock OAuth2 Server" in response.data
        assert b"test-client" in response.data
        assert b"http://localhost/callback" in response.data

    def test_authorize_shows_scope_when_provided(self, client):
        response = client.get(
            "/authorize?client_id=test&redirect_uri=http://localhost/callback&scope=read%20write"
        )
        assert response.status_code == 200
        assert b"read write" in response.data


class TestLoginEndpoint:
    """Test the login form submission"""

    def test_login_requires_email(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        response = session_client.post("/login", data={"name": "John Doe"})
        assert response.status_code == 400
        assert b"Email and name are required" in response.data

    def test_login_requires_name(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        response = session_client.post("/login", data={"email": "test@example.com"})
        assert response.status_code == 400
        assert b"Email and name are required" in response.data

    def test_login_requires_session(self, client):
        response = client.post(
            "/login", data={"email": "test@example.com", "name": "John Doe"}
        )
        assert response.status_code == 400
        assert b"Session expired" in response.data

    def test_login_with_authorization_code_flow(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "read",
                "state": "random-state",
            }

        response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers["Location"]
        assert location.startswith("http://localhost/callback?")

        # Parse redirect URL
        parsed = urlparse(location)
        params = parse_qs(parsed.query)

        assert "code" in params
        assert params["state"][0] == "random-state"

    def test_login_with_implicit_flow(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "token",
                "scope": "read",
                "state": "random-state",
            }

        response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers["Location"]
        assert location.startswith("http://localhost/callback#")

        # Parse redirect URL fragment
        parsed = urlparse(location)
        params = parse_qs(parsed.fragment)

        assert "access_token" in params
        assert params["token_type"][0] == "Bearer"
        assert params["state"][0] == "random-state"

    def test_login_with_implicit_flow_omits_state_when_absent(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "token",
                "scope": "read",
                "state": "",
            }

        response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers["Location"]
        assert location.startswith("http://localhost/callback#")

        # Parse redirect URL fragment
        parsed = urlparse(location)
        params = parse_qs(parsed.fragment)

        assert "access_token" in params
        assert "state" not in params

    def test_login_rejects_unsupported_response_type(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "id_token",
                "scope": "",
                "state": "",
            }

        response = session_client.post(
            "/login", data={"email": "test@example.com", "name": "John Doe"}
        )
        assert response.status_code == 400
        assert b"Unsupported response_type" in response.data


class TestTokenEndpoint:
    """Test the OAuth2 token endpoint"""

    def test_token_requires_authorization_code_grant_type(self, client):
        response = client.post(
            "/token", data={"grant_type": "password", "code": "test-code"}
        )
        assert response.status_code == 400
        assert response.json["error"] == "unsupported_grant_type"

    def test_token_requires_code(self, client):
        response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert response.status_code == 400
        assert response.json["error"] == "invalid_request"

    def test_token_rejects_invalid_code(self, client):
        response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": "invalid-code",
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert response.status_code == 400
        assert response.json["error"] == "invalid_grant"

    def test_token_exchange_success(self, session_client):
        # First, get an authorization code
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        # Extract code from redirect
        location = login_response.headers["Location"]
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        code = params["code"][0]

        # Exchange code for token
        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
                "client_id": "test",
            },
        )

        assert token_response.status_code == 200
        data = token_response.json
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

    def test_token_code_can_only_be_used_once(self, session_client):
        # Get authorization code
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        location = login_response.headers["Location"]
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        code = params["code"][0]

        # First exchange - should succeed
        token_response1 = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert token_response1.status_code == 200

        # Second exchange - should fail
        token_response2 = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert token_response2.status_code == 400
        assert token_response2.json["error"] == "invalid_grant"

    def test_token_rejects_expired_code(self, session_client):
        # Seed an authorization code that expired in the past.
        app_module.authorization_codes["expired-code"] = {
            "user_info": {"email": "a@b.com", "name": "A B", "sub": "a@b.com"},
            "client_id": "test",
            "redirect_uri": "http://localhost/callback",
            "expires_at": 0,  # 1970 — long expired
            "code_challenge": None,
            "code_challenge_method": "plain",
        }

        response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": "expired-code",
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert response.status_code == 400
        assert response.json["error"] == "invalid_grant"
        # Expired code is purged on use.
        assert "expired-code" not in app_module.authorization_codes

    def test_token_rejects_redirect_uri_mismatch(self, session_client):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(login_response.headers["Location"]).query)["code"][0]

        response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/DIFFERENT",
            },
        )
        assert response.status_code == 400
        assert response.json["error"] == "invalid_grant"


class TestUserInfoEndpoint:
    """Test the OAuth2 userinfo endpoint"""

    def test_userinfo_requires_authorization_header(self, client):
        response = client.get("/userinfo")
        assert response.status_code == 401
        assert response.json["error"] == "invalid_token"

    def test_userinfo_requires_bearer_token(self, client):
        response = client.get("/userinfo", headers={"Authorization": "Basic test"})
        assert response.status_code == 401
        assert response.json["error"] == "invalid_token"

    def test_userinfo_rejects_invalid_token(self, client):
        response = client.get(
            "/userinfo", headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401
        assert response.json["error"] == "invalid_token"

    def test_userinfo_returns_user_data(self, session_client):
        # Get authorization code and exchange for token
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )

        location = login_response.headers["Location"]
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        code = params["code"][0]

        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
            },
        )
        access_token = token_response.json["access_token"]

        # Get user info
        userinfo_response = session_client.get(
            "/userinfo", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert userinfo_response.status_code == 200
        data = userinfo_response.json
        assert data["email"] == "test@example.com"
        assert data["name"] == "John Doe"
        assert data["sub"] == "test@example.com"

    def test_userinfo_rejects_expired_token(self, client):
        # Seed an access token that expired in the past.
        app_module.access_tokens["expired-token"] = {
            "user_info": {"email": "a@b.com", "name": "A B", "sub": "a@b.com"},
            "expires_at": 0,  # 1970 — long expired
        }

        response = client.get(
            "/userinfo", headers={"Authorization": "Bearer expired-token"}
        )
        assert response.status_code == 401
        assert response.json["error"] == "invalid_token"
        # Expired token is purged on use.
        assert "expired-token" not in app_module.access_tokens


class TestPKCE:
    """Test PKCE (RFC 7636) support in the auth-code flow"""

    def test_authorize_rejects_bad_challenge_method(self, client):
        response = client.get(
            "/authorize?client_id=test&redirect_uri=http://localhost/callback"
            "&code_challenge=abc&code_challenge_method=bogus"
        )
        assert response.status_code == 400
        assert b"Unsupported code_challenge_method" in response.data

    def test_authorize_accepts_valid_challenge_method(self, client):
        _, challenge = _pkce_pair()
        response = client.get(
            "/authorize?client_id=test-client&redirect_uri=http://localhost/callback"
            f"&code_challenge={challenge}&code_challenge_method=S256"
        )
        assert response.status_code == 200
        assert b"Mock OAuth2 Server" in response.data

    def test_token_exchange_succeeds_with_valid_verifier(self, session_client):
        verifier, challenge = _pkce_pair()
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(login_response.headers["Location"]).query)["code"][0]

        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
                "code_verifier": verifier,
            },
        )
        assert token_response.status_code == 200
        assert "access_token" in token_response.json

    def test_token_exchange_requires_verifier_when_challenge_present(
        self, session_client
    ):
        _, challenge = _pkce_pair()
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(login_response.headers["Location"]).query)["code"][0]

        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
            },
        )
        assert token_response.status_code == 400
        assert token_response.json["error"] == "invalid_grant"

    def test_token_exchange_rejects_wrong_verifier(self, session_client):
        _, challenge = _pkce_pair()
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(login_response.headers["Location"]).query)["code"][0]

        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
                "code_verifier": "the-wrong-verifier",
            },
        )
        assert token_response.status_code == 400
        assert token_response.json["error"] == "invalid_grant"

    def test_token_exchange_succeeds_with_plain_method(self, session_client):
        verifier = "plain-verifier-" + "z" * 43
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://localhost/callback",
                "response_type": "code",
                "scope": "",
                "state": "",
                "code_challenge": verifier,  # plain: challenge == verifier
                "code_challenge_method": "plain",
            }

        login_response = session_client.post(
            "/login",
            data={"email": "test@example.com", "name": "John Doe"},
            follow_redirects=False,
        )
        code = parse_qs(urlparse(login_response.headers["Location"]).query)["code"][0]

        token_response = session_client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://localhost/callback",
                "code_verifier": verifier,
            },
        )
        assert token_response.status_code == 200
        assert "access_token" in token_response.json


class TestAllowlistHelpers:
    """Unit tests for the allowlist parsing/matching helpers"""

    @pytest.mark.parametrize("raw", [None, "", "   ", "*", "localhost,*", ",,"])
    def test_parse_returns_none_for_allow_all(self, raw):
        assert app_module._parse_allowed_domains(raw) is None

    def test_parse_normalizes_list(self):
        assert app_module._parse_allowed_domains(" LocalHost , App.Example.com ") == [
            "localhost",
            "app.example.com",
        ]

    def test_is_domain_allowed_defaults_to_true(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", None)
        assert app_module.is_domain_allowed("http://anything.example.com/cb") is True

    def test_is_domain_allowed_matches_case_insensitively(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", ["localhost"])
        assert app_module.is_domain_allowed("http://LOCALHOST:8080/cb") is True
        assert app_module.is_domain_allowed("http://evil.example.com/cb") is False

    def test_is_domain_allowed_rejects_backslash_authority_confusion(self, monkeypatch):
        # urlparse().hostname reports "allowed.com", but a browser treats "\" as
        # "/" and navigates to evil.com. Must be rejected.
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", ["allowed.com"])
        assert (
            app_module.is_domain_allowed("https://evil.com\\@allowed.com/cb") is False
        )
        assert (
            app_module.is_domain_allowed("https://allowed.com\\.evil.com/cb") is False
        )

    def test_is_domain_allowed_rejects_non_http_schemes(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", ["allowed.com"])
        assert (
            app_module.is_domain_allowed("javascript://allowed.com/%0aalert(1)")
            is False
        )
        assert app_module.is_domain_allowed("data://allowed.com/x") is False
        assert app_module.is_domain_allowed("https://allowed.com/cb") is True

    def test_cors_origins_star_when_unrestricted(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", None)
        assert app_module._cors_origins() == "*"

    def test_cors_origins_regex_per_domain(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", ["localhost"])
        patterns = app_module._cors_origins()
        assert patterns[0].match("http://localhost:8080")
        assert patterns[0].match("https://localhost")
        assert not patterns[0].match("http://evil.com")


class TestHostDefault:
    """The bind host must default to loopback so the mock IdP is not reachable
    from other machines out of the box."""

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_defaults_to_loopback(self, raw):
        assert app_module._resolve_host(raw) == "127.0.0.1"

    def test_respects_explicit_host(self):
        assert app_module._resolve_host("0.0.0.0") == "0.0.0.0"
        assert app_module._resolve_host(" 192.168.1.10 ") == "192.168.1.10"


class TestDomainAllowlist:
    """Test the AWTH_ALLOWED_DOMAINS redirect_uri allowlist"""

    @pytest.fixture
    def allowlist(self, monkeypatch):
        monkeypatch.setattr(app_module, "ALLOWED_DOMAINS", ["localhost"])

    def test_default_allows_any_redirect_uri(self, client):
        # No allowlist configured (ALLOWED_DOMAINS is None by default)
        response = client.get(
            "/authorize?client_id=test&redirect_uri=http://evil.example.com/cb"
        )
        assert response.status_code == 200

    def test_allowed_domain_passes(self, client, allowlist):
        response = client.get(
            "/authorize?client_id=test&redirect_uri=http://localhost:8080/cb"
        )
        assert response.status_code == 200

    def test_disallowed_domain_rejected(self, client, allowlist):
        response = client.get(
            "/authorize?client_id=test&redirect_uri=http://evil.example.com/cb"
        )
        assert response.status_code == 400
        assert b"redirect_uri not allowed" in response.data

    def test_disallowed_domain_rejected_at_login(self, session_client, allowlist):
        with session_client.session_transaction() as sess:
            sess["oauth_params"] = {
                "client_id": "test",
                "redirect_uri": "http://evil.example.com/cb",
                "response_type": "code",
                "scope": "",
                "state": "",
            }
        response = session_client.post(
            "/login", data={"email": "a@b.com", "name": "A B"}
        )
        assert response.status_code == 400
        assert b"redirect_uri not allowed" in response.data
