# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Multi-architecture image**: the published `ghcr.io/kilotronic/awth` image now
  ships both `linux/amd64` and `linux/arm64`, so it runs natively on Apple Silicon
  and other arm64 hosts instead of under emulation. CI builds both platforms via
  QEMU + Buildx.
- **Configurable domain allowlist** (`AWTH_ALLOWED_DOMAINS`): a comma-separated
  list of hostnames allowed as `redirect_uri` and CORS origins. Defaults to `*`
  (allow any) so the tool still works out of the box; when set, `/authorize`
  rejects disallowed redirect URIs and CORS is limited to the listed hosts.
- Environment-based configuration for `AWTH_DEBUG`, `AWTH_HOST`, and
  `AWTH_PORT` / `PORT`.

### Security

- Hardened the `redirect_uri` allowlist against backslash authority-confusion
  (`https://evil.com\@allowed.com`) and non-`http(s)` schemes, so it can't be
  bypassed to leak authorization codes to an attacker origin.
- `examples/spa/` — a zero-dependency single-page app that walks through the full
  Authorization Code + PKCE flow in the browser and visualizes each step.
- `LICENSE` (MIT), license/classifier metadata in `pyproject.toml`,
  `CONTRIBUTING.md`, and this changelog.
- Tests for PKCE (S256) and the domain allowlist.

### Changed

- `AWTH_HOST` now defaults to **`127.0.0.1`** (loopback) instead of `0.0.0.0`.
  Because there is no safe default `redirect_uri`/CORS allowlist, binding to
  loopback keeps the intentionally-open server unreachable from other machines
  out of the box. Set `AWTH_HOST=0.0.0.0` to expose it (and pair with
  `AWTH_ALLOWED_DOMAINS`). The `0.0.0.0` bind in the Docker images is unchanged —
  containers need it to accept forwarded connections.
- `AWTH_DEBUG` now defaults to **off**. Previously the server always ran with
  Flask's debugger enabled; it is now opt-in. The development `docker-compose.yml`
  sets `AWTH_DEBUG=1` to preserve live reload.
- Documentation: prominent security/scope banner, environment-variable reference,
  and product-neutral integration examples.

## [2.1.1]

- PKCE (RFC 7636) support in the authorization code flow, with CORS on `/token`
  and `/userinfo` for browser-side code exchange.
- Importable `awth.oidc_config()` helper (zero runtime dependencies) shared with
  the `/.well-known/openid-configuration` endpoint.
- Authorization Code and Implicit flows, `/userinfo`, `/health`, and OIDC
  discovery.
