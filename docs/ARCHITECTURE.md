# Architecture

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│ Presentation   app/api  ·  app/cli   — REST + CLI              │
├──────────────────────────────────────────────────────────────┤
│ Services       auth · workflow engine · workflow service ·     │
│                scheduler                                       │
├──────────────────────────────────────────────────────────────┤
│ Domain         plugin contract · workflow model · conditions   │
├──────────────────────────────────────────────────────────────┤
│ Plugins        self-registering automation adapters            │
├──────────────────────────────────────────────────────────────┤
│ Repositories   SQLAlchemy data access                          │
├──────────────────────────────────────────────────────────────┤
│ Infrastructure db · cache · resilience · metrics               │
└──────────────────────────────────────────────────────────────┘
   Cross-cutting: config · security · logging · rate limit · DI
```

Outer layers depend on inner layers only through interfaces. The composition
root (`app/container.py`) is the single place that constructs infrastructure and
injects it, so nothing else is coupled to a vendor library or the database.

## The plugin system

A **plugin** implements `app.domain.plugins.Plugin`: it declares a Pydantic
`params_model`, a `run()` coroutine, and an optional `compensate()` for
rollback. Plugins self-register with the module-level registry via the
`@register` decorator; importing `app.plugins` discovers them all. Adding a new
capability is a new module — the core never changes (Open/Closed).

Design patterns in use: **Plugin/Strategy** (interchangeable plugins),
**Command** (`compensate` for rollback), **Repository**, **Service Layer**,
**Dependency Injection**, and **Factory** (the composition root).

## Workflow execution

```
WorkflowDefinition (validated: structure + plugins exist + unique ids)
        │
        ▼
For each step:
  when? ─ evaluate restricted condition ─ false ─▶ SKIPPED
  │ true
  ▼
  resolve ${step.field} templates ─▶ validate params (Pydantic)
  ▼
  run with retry(backoff) + timeout
  ├─ success ─▶ output merged into context.variables[step.id]; pushed for rollback
  └─ failure ─▶ on_error:
                 stop      → mark run FAILED, stop
                 continue  → record failure, keep going
                 rollback  → compensate completed steps in reverse, stop
```

Data flows between steps through `context.variables`: a step's output is stored
under its id, and later steps reference it with `${id.field}` templates that the
engine substitutes before validation.

## Security model

| Control | Where |
| ------- | ----- |
| Argon2id password hashing | `core/security.py` |
| JWT access/refresh + `jti` revocation | `core/security.py`, `services/token_blocklist.py` |
| RBAC | `api/deps.py` |
| Rate limiting | `core/rate_limit.py` |
| Hardened headers, CORS | `core/middleware.py`, `main.py` |
| Input validation (Pydantic) + RFC 7807 errors | schemas, `core/errors.py` |
| **Filesystem sandbox** (path-traversal proof) | `domain/plugins.py::PluginContext.safe_path` |
| **No `eval`** — restricted condition parser | `domain/workflow.py` |
| Audit log | `db/models.py::AuditLog` |
| Secret guard (reject default in prod) | `core/config.py` |

## Data model

- **User** 1─N **Workflow** 1─N **WorkflowRun** 1─N **StepRun**
- **AuditLog** — append-only security events
- Workflow definitions and step outputs are stored as JSON columns.
