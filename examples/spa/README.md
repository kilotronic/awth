# SPA demo — Authorization Code + PKCE

A zero-dependency, single-file single-page app that runs the **full** OAuth2
Authorization Code + PKCE flow against a local `awth` server, entirely in the
browser, and shows you every step: the `/authorize` redirect, the returned code,
the `/token` exchange, and the `/userinfo` response.

Because the SPA exchanges the code from JavaScript (`fetch`) on a _different_
origin than the server, it exercises the CORS + PKCE path that `awth`'s `/token`
and `/userinfo` endpoints are built for.

## Run it with Docker Compose (one command)

The quickest way — brings up both `awth` and a static server for this page:

```bash
cd examples/spa
docker compose up --build
```

Then open **<http://localhost:8080>** and click **“Log in with awth”**.

## Run it manually

You need two things running: the `awth` server and a static file server for this
page (they must be on different origins).

**Terminal 1 — start awth** (from the repo root):

```bash
pip install ".[server]"
python app.py            # serves on http://localhost:4999
```

…or with Docker: `docker run -p 4999:4999 ghcr.io/kilotronic/awth:latest`

**Terminal 2 — serve this page:**

```bash
cd examples/spa
python -m http.server 8080
```

Then open **<http://localhost:8080>** and click **“Log in with awth”**. Enter any
email and name on the awth login page — you'll be redirected back here and see the
code, token, and userinfo populate step by step.

> `localhost` is a [secure context], so the Web Crypto API used for the S256 PKCE
> challenge works without HTTPS.

[secure context]: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts

## Locking down the allowlist

By default `awth` accepts any `redirect_uri` (`AWTH_ALLOWED_DOMAINS` unset ⇒ `*`).
To see the allowlist in action, restart the server restricted to `localhost`:

```bash
AWTH_ALLOWED_DOMAINS=localhost python app.py
```

The demo (served from `localhost:8080`) still works. Point the base URL or
`redirect_uri` at any other host and `/authorize` returns **400 redirect_uri not
allowed**.
