# Contributing to awth

Thanks for your interest! awth is a small, deliberately simple mock OAuth2 / OIDC
server. Contributions that keep it small and easy to run are very welcome.

## Setup

```bash
uv sync --extra dev          # server deps + pytest, coverage, ruff, pre-commit
uv run pre-commit install    # run the hooks on every commit
```

## Running the tests

```bash
./run-tests.sh               # pytest with coverage + HTML report (htmlcov/)
# or
pytest                       # coverage settings come from pyproject.toml
pytest tests/test_oauth_server.py::TestPKCE -v   # a single class
```

Coverage is gated at 100% (`--cov-fail-under=100` in `pyproject.toml`); add tests
for any new behavior. The project follows a test-driven approach — write the test
first.

## Linting and formatting

```bash
ruff check .                 # lint
ruff format .                # format
```

`pre-commit` runs `ruff`, `ruff-format`, and `pytest` automatically, plus a
local-image build hook. You can run the full set at any time with:

```bash
pre-commit run --all-files
```

## Pull requests

- Keep changes focused and the server dependency-light (the core library has zero
  runtime dependencies; the server extra is just Flask + flask-cors).
- Make sure tests and linters pass before opening the PR.
- Remember this is a **mock** server — features that add real authentication,
  persistence, or production hardening are out of scope by design.
