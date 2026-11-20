"""Lifetimes, the bearer scheme, PKCE defaults, discovery values and the CORS/allowlist wiring."""

import importlib
import time
from urllib.parse import parse_qs, urlparse

import pytest

import app as app_module
from awth import oidc_config

CALLBACK = "http://localhost/callback"


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


def _code(client, **pkce):
    """Run /authorize and /login; return the authorization code."""
    query = {"client_id": "c", "redirect_uri": CALLBACK, **pkce}
    client.get("/authorize", query_string=query)
    resp = client.post("/login", data={"email": "ada@example.com", "name": "Ada"})
    return parse_qs(urlparse(resp.headers["Location"]).query)["code"][0]


def _token(client, code, **extra):
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": CALLBACK}
    return client.post("/token", data={**data, **extra})


def test_a_code_lives_ten_minutes(client, monkeypatch):
    start = time.time()
    code = _code(client)
    assert app_module.authorization_codes[code]["expires_at"] == pytest.approx(
        start + 600, abs=5
    )
    monkeypatch.setattr(app_module.time, "time", lambda: start + 601 + 5)
    assert _token(client, code).json["error_description"] == "Code expired"


def test_an_access_token_lives_one_hour(client, monkeypatch):
    start = time.time()
    access = _token(client, _code(client)).json["access_token"]
    assert app_module.access_tokens[access]["expires_at"] == pytest.approx(
        start + 3600, abs=5
    )
    headers = {"Authorization": f"Bearer {access}"}
    monkeypatch.setattr(app_module.time, "time", lambda: start + 3590 - 5)
    assert client.get("/userinfo", headers=headers).status_code == 200
    monkeypatch.setattr(app_module.time, "time", lambda: start + 3601 + 5)
    assert client.get("/userinfo", headers=headers).status_code == 401


@pytest.mark.parametrize("scheme", ["Token", "Basic", "MAC", ""])
def test_a_valid_token_under_another_scheme_is_refused(client, scheme):
    access = _token(client, _code(client)).json["access_token"]
    resp = client.get("/userinfo", headers={"Authorization": f"{scheme} {access}"})
    assert resp.status_code == 401


def test_userinfo_reports_a_verified_email(client):
    access = _token(client, _code(client)).json["access_token"]
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {access}"})
    assert resp.json == {
        "email": "ada@example.com",
        "email_verified": True,
        "name": "Ada",
        "sub": "ada@example.com",
    }


def test_a_challenge_without_a_method_is_plain(client):
    code = _code(client, code_challenge="the-verifier")
    assert _token(client, code, code_verifier="the-verifier").status_code == 200


def test_discovery_values_for_a_base_url_with_a_trailing_slash():
    assert oidc_config("http://localhost:4999/") == {
        "issuer": "http://localhost:4999",
        "authorization_endpoint": "http://localhost:4999/authorize",
        "token_endpoint": "http://localhost:4999/token",
        "userinfo_endpoint": "http://localhost:4999/userinfo",
        "response_types_supported": ["code", "token"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["none"],
        "code_challenge_methods_supported": ["plain", "S256"],
    }


def test_the_discovery_endpoint_serves_the_same_document(client):
    resp = client.get("/.well-known/openid-configuration", base_url="http://h:4999")
    assert resp.json == oidc_config("http://h:4999/")


# --- AWTH_ALLOWED_DOMAINS, read at import: reload the app with it set


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("AWTH_ALLOWED_DOMAINS", "localhost, app.example")
    module = importlib.reload(app_module)
    module.app.config["TESTING"] = True
    yield module
    monkeypatch.delenv("AWTH_ALLOWED_DOMAINS")
    importlib.reload(app_module)


def test_the_env_allowlist_refuses_other_redirects(locked):
    client = locked.app.test_client()
    query = {"client_id": "c", "redirect_uri": "http://evil.example/cb"}
    assert client.get("/authorize", query_string=query).status_code == 400
    query["redirect_uri"] = "http://app.example:8080/cb"
    assert client.get("/authorize", query_string=query).status_code == 200


@pytest.mark.parametrize("path", ["/token", "/userinfo"])
def test_cors_allows_only_the_allowlisted_origins(locked, path):
    client = locked.app.test_client()
    method = client.post if path == "/token" else client.get
    ok = method(path, headers={"Origin": "http://app.example:3000"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://app.example:3000"
    evil = method(path, headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in evil.headers


@pytest.mark.parametrize("path", ["/token", "/userinfo"])
def test_cors_is_open_without_an_allowlist(client, path):
    method = client.post if path == "/token" else client.get
    resp = method(path, headers={"Origin": "http://anything.example"})
    allowed = resp.headers.get("Access-Control-Allow-Origin")
    assert allowed in ("*", "http://anything.example")
