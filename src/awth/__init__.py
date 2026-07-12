"""Awth — lightweight OIDC server for development and testing."""


def oidc_config(base_url: str) -> dict[str, str]:
    """Return an OIDC discovery document for the given base URL.

    This is the same data that ``/.well-known/openid-configuration``
    serves at runtime, but importable without a network round-trip.
    """
    base = base_url.rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "response_types_supported": ["code", "token"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["none"],
        "code_challenge_methods_supported": ["plain", "S256"],
    }
