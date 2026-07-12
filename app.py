import hashlib
import os
import re
import secrets
import time
from base64 import urlsafe_b64encode
from urllib.parse import urlencode, urlsplit

from flask import Flask, jsonify, redirect, render_template, request, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_NAME"] = "awth_session"


def _parse_allowed_domains(raw):
    """Parse AWTH_ALLOWED_DOMAINS into a list of hostnames, or None for 'allow all'.

    Empty, unset, or a value containing '*' means no restriction (returns None).
    Otherwise returns a lowercased list of allowed hostnames.
    """
    if not raw:
        return None
    domains = [d.strip().lower() for d in raw.split(",") if d.strip()]
    if not domains or "*" in domains:
        return None
    return domains


# Domain allowlist for redirect URIs and CORS origins. Defaults to "allow any"
# so the tool works out of the box; set AWTH_ALLOWED_DOMAINS to a comma-separated
# list of hostnames (e.g. "localhost,app.example.com") to lock it down.
ALLOWED_DOMAINS = _parse_allowed_domains(os.environ.get("AWTH_ALLOWED_DOMAINS"))


def is_domain_allowed(uri):
    """Return True if the host of `uri` is permitted by the allowlist.

    Rejects backslashes outright: browsers treat "\\" as "/" in http(s)
    authorities, so a URI like "https://evil.com\\@allowed.com/cb" parses to
    host "allowed.com" here but navigates to evil.com in a browser. Only
    http/https schemes are accepted.
    """
    if ALLOWED_DOMAINS is None:
        return True
    if not uri or "\\" in uri:
        return False
    parts = urlsplit(uri)
    if parts.scheme not in ("http", "https"):
        return False
    return (parts.hostname or "").lower() in ALLOWED_DOMAINS


def _resolve_host(raw):
    """Interface to bind, defaulting to loopback.

    There is no safe default allowlist for redirect URIs / CORS, so the server
    ships wide open. Binding to 127.0.0.1 by default keeps that openness
    contained to the local machine — nothing else can reach it. Set AWTH_HOST
    explicitly (e.g. "0.0.0.0") to expose it, and pair that with
    AWTH_ALLOWED_DOMAINS.
    """
    host = (raw or "").strip()
    return host or "127.0.0.1"


def _cors_origins():
    """CORS origins for flask-cors: '*' when unrestricted, else one regex per domain.

    A browser Origin header carries a scheme and often a port
    ("http://localhost:8080"), so a bare hostname would never match. Each allowed
    domain becomes a regex accepting either scheme and any port.
    """
    if ALLOWED_DOMAINS is None:
        return "*"
    return [re.compile(rf"^https?://{re.escape(d)}(:\d+)?\Z") for d in ALLOWED_DOMAINS]


# PKCE browser-side exchange: the token and userinfo endpoints are called
# via fetch() from a remote origin, so they need CORS. Origins are limited to
# the domain allowlist (wide-open "*" only when no allowlist is configured).
_cors_config = {"origins": _cors_origins()}
CORS(app, resources={r"/token": _cors_config, r"/userinfo": _cors_config})

# In-memory storage for tokens and user info
authorization_codes = {}  # code -> {user_info, client_id, redirect_uri, expires_at}
access_tokens = {}  # token -> {user_info, expires_at}


@app.route("/authorize")
def authorize():
    """OAuth2 authorization endpoint"""
    client_id = request.args.get("client_id")
    redirect_uri = request.args.get("redirect_uri")
    response_type = request.args.get("response_type", "code")
    scope = request.args.get("scope", "")
    state = request.args.get("state", "")

    if not client_id or not redirect_uri:
        return "Missing required parameters: client_id and redirect_uri", 400

    if not is_domain_allowed(redirect_uri):
        return "redirect_uri not allowed", 400

    # PKCE (RFC 7636): only process challenge_method when a challenge is present
    code_challenge = request.args.get("code_challenge")
    code_challenge_method = None
    if code_challenge:
        code_challenge_method = request.args.get("code_challenge_method", "plain")
        if code_challenge_method not in ("plain", "S256"):
            return f"Unsupported code_challenge_method: {code_challenge_method}", 400

    # Store params in session for later use
    session["oauth_params"] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }

    return render_template(
        "login.html", client_id=client_id, redirect_uri=redirect_uri, scope=scope
    )


@app.route("/login", methods=["POST"])
def login():
    """Handle the login form submission"""
    email = request.form.get("email")
    name = request.form.get("name")

    if not email or not name:
        return "Email and name are required", 400

    oauth_params = session.get("oauth_params")
    if not oauth_params:
        return "Session expired. Please try again.", 400

    if not is_domain_allowed(oauth_params.get("redirect_uri")):
        return "redirect_uri not allowed", 400

    user_info = {
        "email": email,
        "email_verified": True,
        "name": name,
        "sub": email,  # Subject identifier
    }

    response_type = oauth_params["response_type"]
    redirect_uri = oauth_params["redirect_uri"]
    state = oauth_params["state"]

    if response_type == "code":
        # Authorization Code Flow
        code = secrets.token_urlsafe(32)
        authorization_codes[code] = {
            "user_info": user_info,
            "client_id": oauth_params["client_id"],
            "redirect_uri": redirect_uri,
            "expires_at": time.time() + 600,  # 10 minutes
            "code_challenge": oauth_params.get("code_challenge"),
            "code_challenge_method": oauth_params.get("code_challenge_method", "plain"),
        }

        params = {"code": code}
        if state:
            params["state"] = state

        return redirect(f"{redirect_uri}?{urlencode(params)}")

    elif response_type == "token":
        # Implicit Flow
        access_token = secrets.token_urlsafe(32)
        access_tokens[access_token] = {
            "user_info": user_info,
            "expires_at": time.time() + 3600,  # 1 hour
        }

        params = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        if state:
            params["state"] = state

        # Implicit flow returns token in URL fragment
        return redirect(f"{redirect_uri}#{urlencode(params)}")

    else:
        return f"Unsupported response_type: {response_type}", 400


@app.route("/token", methods=["POST"])
def token():
    """OAuth2 token endpoint - exchanges authorization code for access token"""
    grant_type = request.form.get("grant_type")
    code = request.form.get("code")
    redirect_uri = request.form.get("redirect_uri")

    if grant_type != "authorization_code":
        return jsonify({"error": "unsupported_grant_type"}), 400

    if not code:
        return jsonify(
            {"error": "invalid_request", "error_description": "Missing code"}
        ), 400

    # Validate authorization code
    auth_data = authorization_codes.get(code)
    if not auth_data:
        return jsonify(
            {"error": "invalid_grant", "error_description": "Invalid or expired code"}
        ), 400

    # Check if code is expired
    if time.time() > auth_data["expires_at"]:
        del authorization_codes[code]
        return jsonify(
            {"error": "invalid_grant", "error_description": "Code expired"}
        ), 400

    # Validate redirect_uri matches
    if redirect_uri and redirect_uri != auth_data["redirect_uri"]:
        return jsonify(
            {"error": "invalid_grant", "error_description": "Redirect URI mismatch"}
        ), 400

    # PKCE verification
    code_challenge = auth_data.get("code_challenge")
    code_verifier = request.form.get("code_verifier")
    if code_challenge:
        if not code_verifier:
            return jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": "code_verifier required",
                }
            ), 400
        method = auth_data.get("code_challenge_method") or "plain"
        if method == "S256":
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            computed = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        else:
            computed = code_verifier
        if computed != code_challenge:
            return jsonify(
                {
                    "error": "invalid_grant",
                    "error_description": "PKCE verification failed",
                }
            ), 400

    # Generate access token
    access_token = secrets.token_urlsafe(32)
    access_tokens[access_token] = {
        "user_info": auth_data["user_info"],
        "expires_at": time.time() + 3600,  # 1 hour
    }

    # Delete used authorization code
    del authorization_codes[code]

    return jsonify(
        {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}
    )


@app.route("/userinfo")
def userinfo():
    """OAuth2 userinfo endpoint - returns user information"""
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "invalid_token"}), 401

    access_token = auth_header.split(" ")[1]
    token_data = access_tokens.get(access_token)

    if not token_data:
        return jsonify({"error": "invalid_token"}), 401

    # Check if token is expired
    if time.time() > token_data["expires_at"]:
        del access_tokens[access_token]
        return jsonify({"error": "invalid_token"}), 401

    return jsonify(token_data["user_info"])


@app.route("/.well-known/openid-configuration")
def openid_configuration():
    """OpenID Connect discovery endpoint"""
    from awth import oidc_config

    return jsonify(oidc_config(request.host_url))


@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"})


if __name__ == "__main__":  # pragma: no cover
    # debug is OFF by default: the Werkzeug debugger allows arbitrary code
    # execution, so it must be opted into (AWTH_DEBUG=1) for local hacking.
    debug = os.environ.get("AWTH_DEBUG", "").lower() in ("1", "true", "yes")
    host = _resolve_host(os.environ.get("AWTH_HOST"))
    port = int(os.environ.get("AWTH_PORT") or os.environ.get("PORT") or 4999)
    app.run(host=host, port=port, debug=debug)
