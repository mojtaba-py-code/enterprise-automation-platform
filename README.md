# Enterprise Automation Platform

[![CI](https://github.com/mojtaba-py-code/enterprise-automation-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/mojtaba-py-code/enterprise-automation-platform/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](#testing--quality)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A modular, **plugin-driven** platform for automating business processes. Users
compose automation **workflows** from reusable steps (file, Excel, PDF, HTTP,
transform, email …); the engine runs them with conditional branching, retries,
timeouts and compensating **rollback**, and everything is exposed through a
secure **REST API** and a **CLI**.

> Built with FastAPI + async SQLAlchemy 2.x on a clean, layered architecture.
> Security, testing and observability are first-class, not afterthoughts.

---

## Why it's interesting

- **Plugin architecture** — every capability is a self-registering plugin behind
  one interface. Adding a new automation is a new file, not a core change.
- **Workflow engine** — sequential steps with `${step.field}` data-flow between
  them, `when` conditions, per-step retries/timeouts, and **rollback** via a
  Command-pattern `compensate` hook.
- **Security-first** — Argon2id hashing, JWT access/refresh with revocation,
  RBAC, rate limiting, hardened headers, audit log, RFC 7807 errors, and a
  **filesystem sandbox** that blocks path traversal for every file plugin.
- **Safe by design** — workflow conditions are evaluated by a restricted parser,
  never `eval`; parameters are validated with Pydantic before a plugin runs.
- **Observability** — structured JSON logs with a correlation id, plus a
  Prometheus `/metrics` endpoint (HTTP RED signals + workflow/step counters).
- **Tested** — 81 tests, **92% coverage**, enforced in CI alongside ruff, mypy,
  bandit and pip-audit.

## Architecture

```
app/
  api/v1/         presentation — routers, request/response wiring
  services/       use-cases — auth, workflow engine & service, scheduler
  domain/         plugin contract, workflow model, safe condition evaluator
  plugins/        self-registering automation plugins + registry
  repositories/   data access (SQLAlchemy)
  resilience/     retry, circuit breaker, cache
  core/           config, security, logging, errors, middleware, metrics
  db/             engine, session, ORM models
  container.py    composition root (dependency injection)
  main.py         FastAPI app factory   ·   cli.py  Typer CLI
```

Dependencies point inward through interfaces; only adapters touch a vendor
library or the database. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Built-in plugins

| Plugin | Category | What it does |
| ------ | -------- | ------------ |
| `file.write` / `file.read` / `file.move` / `file.delete` | file | sandboxed filesystem ops (write & move support rollback) |
| `excel.write` / `excel.read` | excel | read/write `.xlsx` workbooks |
| `pdf.report` | pdf | render a titled PDF report |
| `http.request` | api | call an HTTP/JSON API |
| `transform.set` / `transform.validate` / `transform.template` | transform | set variables, validate, render templates |
| `email.send` | notification | send/record an email |

## Example workflow

```json
{
  "name": "greet",
  "steps": [
    { "id": "vars",  "plugin": "transform.set", "params": { "values": { "who": "World" } } },
    { "id": "write", "plugin": "file.write",    "params": { "path": "greet.txt", "content": "Hello ${vars.who}" } },
    { "id": "read",  "plugin": "file.read",     "params": { "path": "greet.txt" } },
    { "id": "check", "plugin": "transform.validate", "params": { "value": "${read.content}", "min_length": 3 } }
  ]
}
```

Run it from the CLI:

```bash
eap run examples/greet.json
```

## API

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/api/v1/auth/register` · `/login` · `/refresh` · `/logout` | authentication |
| GET | `/api/v1/plugins` | list plugins (admin can `/{name}/enable` · `/disable`) |
| POST/GET/DELETE | `/api/v1/workflows` | manage workflows |
| POST | `/api/v1/workflows/{id}/run` | run a workflow, get per-step results |
| GET | `/api/v1/workflows/{id}/runs` | run history |
| GET | `/api/v1/admin/dashboard` | metrics + system health (admin) |
| GET | `/api/v1/health/live` · `/ready` · `/metrics` | probes & Prometheus |

Interactive docs at `/docs` (Swagger) and `/redoc` when the app is running.

## Quick start

```bash
make install               # create .venv and install the project + dev tools
cp .env.example .env        # then set EAP_SECRET_KEY
make test                   # run the suite with the coverage gate
make run                    # start the API on :8000
make cli ARGS="plugins"     # list plugins via the CLI
```

Out of the box it uses SQLite and an in-memory cache — no external services
required. Point `EAP_DATABASE_URL`/`EAP_REDIS_URL` at Postgres/Redis for a
production-like setup, or run everything with `docker compose up --build`.

## Testing & quality

```bash
make lint      # ruff check + ruff format --check
make type      # mypy (strict-ish)
make test      # pytest + coverage (fails under 90%)
```

## License

MIT
