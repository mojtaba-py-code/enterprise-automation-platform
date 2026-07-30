# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-07-30

### Added
- Plugin system with a self-registering registry and runtime enable/disable.
- Workflow engine: `${step.field}` data-flow, `when` conditions, per-step
  retries with backoff, timeouts, and compensating rollback (Command pattern).
- Built-in plugins: file (write/read/move/delete), Excel (read/write),
  PDF report, HTTP request, transforms (set/validate/template), email.
- Filesystem sandbox with path-traversal protection for every file plugin.
- Restricted (no-`eval`) condition evaluator for workflow branching.
- Auth: registration, login, JWT access/refresh, and logout via a cache-backed
  token denylist; Argon2id hashing; RBAC; rate limiting; audit log.
- REST API (auth, plugins, workflows, runs, admin dashboard, health) and a
  Typer CLI (`eap plugins`, `eap run <file>`).
- Observability: structured logs with a correlation id and Prometheus /metrics.
- PostgreSQL models with Alembic migrations; Redis-backed cache & rate limiter.
- Docker + Docker Compose and a GitHub Actions pipeline (ruff, mypy, pytest with
  a 90% coverage gate, bandit, pip-audit, image build).
