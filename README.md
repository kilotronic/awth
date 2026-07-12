# awth — Mock OAuth2 / OIDC server for local testing

![Build Status](https://github.com/kilotronic/awth/actions/workflows/ci.yml/badge.svg)

A tiny Flask-based OAuth2 / OpenID Connect server for local development and
testing. It accepts **any** email/name combination and issues tokens **without
real authentication** — point your app's OIDC discovery at it and you have a
working identity provider on `localhost` in seconds.

> ⚠️ **This is a mock server. It is intentionally insecure and must never be
> exposed publicly or used in production.**
>
> - It performs **no real authentication** — it accepts any email and name and
>   trusts them.
> - Tokens are **opaque and unsigned** — there is no `id_token`, no JWT, and no
>   JWKS to verify against.
> - CORS on `/token` and `/userinfo` is **wide open (`*`) by default** so
>   browser-based SPAs can complete the flow (configurable — see
>   [Configuration](#configuration)).
> - State is held **in memory** and resets on restart.
>
> Use it only on a machine you control, for development and automated testing.

## Features

- **Authorization Code Flow** - Standard OAuth2 flow with code exchange
- **Implicit Flow** - Direct token issuance (less secure, for SPAs)
- **No Client Validation** - Accepts any client_id for easy testing
- **Simple Login** - Just enter email and name, no passwords
- **Standard Endpoints** - /authorize, /token, /userinfo
- **OpenID Discovery** - /.well-known/openid-configuration

## Quick Start

### Using Pre-built Image from GitHub Container Registry

```bash
docker run -p 4999:4999 ghcr.io/kilotronic/awth:latest
```

### Using Docker Compose (Recommended)

```bash
docker-compose up --build
```

The server will be available at `http://localhost:4999`

### Using Docker

```bash
# Build the image locally
docker build -t awth .

# Run the container
docker run -p 4999:4999 awth
```

### Running Locally (without Docker)

```bash
pip install ".[server]"
python app.py
```

### Using as a Library

The `awth` package can be installed as a dependency in other projects to get OIDC
configuration without running the server or pulling in Flask:

```bash
pip install git+https://github.com/kilotronic/awth.git
```

```python
from awth import oidc_config

config = oidc_config("http://localhost:4999")
# Returns the full OIDC discovery document as a dict
```

To add it as a dependency in your project's `pyproject.toml`:

```toml
dependencies = [
    "awth @ git+https://github.com/kilotronic/awth.git",
]
```

## Usage

### Authorization Code Flow

1. Redirect user to:

```
http://localhost:4999/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_CALLBACK&response_type=code&state=RANDOM_STATE
```

1. User enters email and name on the login page

2. User is redirected back with authorization code:

```
YOUR_CALLBACK?code=AUTHORIZATION_CODE&state=RANDOM_STATE
```

1. Exchange code for access token:

```bash
curl -X POST http://localhost:4999/token \
  -d "grant_type=authorization_code" \
  -d "code=AUTHORIZATION_CODE" \
  -d "redirect_uri=YOUR_CALLBACK" \
  -d "client_id=YOUR_CLIENT_ID"
```

Response:

```json
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

### Implicit Flow

1. Redirect user to:

```
http://localhost:4999/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_CALLBACK&response_type=token&state=RANDOM_STATE
```

1. User is redirected back with token in URL fragment:

```
YOUR_CALLBACK#access_token=ACCESS_TOKEN&token_type=Bearer&expires_in=3600&state=RANDOM_STATE
```

### Get User Info

```bash
curl http://localhost:4999/userinfo \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Response:

```json
{
  "email": "user@example.com",
  "name": "John Doe",
  "sub": "user@example.com"
}
```

## Endpoints

- `GET /authorize` - OAuth2 authorization endpoint
- `POST /token` - Token exchange endpoint
- `GET /userinfo` - User information endpoint
- `GET /.well-known/openid-configuration` - OpenID Connect discovery
- `GET /health` - Health check

## Configuration

Out of the box no configuration is needed — the server accepts any `client_id`,
stores tokens in memory (reset on restart), runs on port 4999, and expires
authorization codes after 10 minutes and access tokens after 1 hour.

Behavior can be tuned with environment variables:

| Variable               | Default     | Purpose                                                                                                                                                     |
| ---------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AWTH_ALLOWED_DOMAINS` | `*`         | Comma-separated hostnames allowed as `redirect_uri` and CORS origins (e.g. `localhost,app.example.com`). `*`/unset allows any.                              |
| `AWTH_DEBUG`           | _off_       | Set to `1` to enable Flask's reloader/debugger. **Leave off** unless developing — the debugger allows arbitrary code execution.                             |
| `AWTH_HOST`            | `127.0.0.1` | Interface to bind. Defaults to loopback so the server is unreachable from other machines. Set to `0.0.0.0` to expose it — pair with `AWTH_ALLOWED_DOMAINS`. |
| `AWTH_PORT` / `PORT`   | `4999`      | Port to listen on.                                                                                                                                          |

The **domain allowlist** is the one real security control: with it set,
`/authorize` rejects any `redirect_uri` whose host isn't listed (closing the
open-redirect surface), and CORS is limited to those hosts. Left at the default
`*`, any redirect and any origin is accepted — convenient locally, but another
reason never to expose this server.

## Example: watch the full flow in a browser

[`examples/spa/`](examples/spa/) is a zero-dependency single-page app that runs
the complete Authorization Code + PKCE flow against a local `awth` server and
shows every step (authorize redirect → code → token exchange → userinfo). See
[`examples/spa/README.md`](examples/spa/README.md) to run it.

## Notes

This is a mock server for local development:

- No real authentication
- Accepts any user input
- Stores tokens in memory
- No rate limiting

## Development

The docker-compose.yml includes volume mounts for live reload during development. Just edit the files and the changes will be reflected immediately.

### Running Tests

This project uses pytest with TDD approach. All tests are in the `tests/` directory.

```bash
# Install dependencies including dev tools
uv sync --extra dev

# Run all tests with coverage
pytest

# Run tests in verbose mode
pytest -v

# Run specific test class
pytest tests/test_oauth_server.py::TestAuthorizeEndpoint -v

# Run tests with coverage report
pytest --cov=. --cov-report=html
```

Test coverage: 100% (gated via `--cov-fail-under=100`)

## Testing with curl

Complete flow example:

```bash
# 1. Get authorization code (open in browser)
open "http://localhost:4999/authorize?client_id=test&redirect_uri=http://localhost:3000/callback&response_type=code&state=xyz"

# 2. After login, you'll be redirected with a code. Use it to get a token:
curl -X POST http://localhost:4999/token \
  -d "grant_type=authorization_code" \
  -d "code=YOUR_CODE_HERE" \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "client_id=test"

# 3. Use the token to get user info:
curl http://localhost:4999/userinfo \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up, run the tests, and the
lint/format expectations.

## License

[MIT](LICENSE) © Kilotronic LLC — use freely for testing and development.
