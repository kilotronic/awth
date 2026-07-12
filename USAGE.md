# Using awth locally

## Building the local image

```bash
make build-local
```

This creates the `awth:local` image that other projects can reference.

## Using it in your own project

Add awth as a service in your project's `docker-compose.yml` (or `compose.yml`)
so it comes up alongside the rest of your stack:

```yaml
services:
  awth:
    image: awth:local # podman users: use localhost/awth:local
    ports:
      - "4999:4999"
    environment:
      # Optional: restrict redirect URIs / CORS to your app's host(s).
      - AWTH_ALLOWED_DOMAINS=localhost
```

Prefer not to build locally? Reference the published image instead:

```yaml
services:
  awth:
    image: ghcr.io/kilotronic/awth:latest
    ports:
      - "4999:4999"
```

Point your application's OIDC discovery at
`http://localhost:4999/.well-known/openid-configuration` and it will find the
`/authorize`, `/token`, and `/userinfo` endpoints.

## Rebuilding after changes

Whenever you change awth, rebuild the local image and restart the containers
that use it:

```bash
cd /path/to/awth
make build-local

# then, in the project that consumes it:
docker compose down
docker compose up -d
```

## Available compose files

- `docker-compose.yml` — Local development with live reload (builds from source)
- `docker-compose.local.yml` — Uses the pre-built `awth:local` image
- `docker-compose.registry.yml` — Uses the remote `ghcr.io` registry image
