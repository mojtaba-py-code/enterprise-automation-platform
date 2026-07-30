# Contributing

How I work on this project locally.

## Setup

```bash
make install          # creates .venv and installs the project + dev tools
cp .env.example .env   # then set EAP_SECRET_KEY
```

Generate a signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Before you push

Everything below runs in CI, so run it locally first:

```bash
make lint    # ruff check + ruff format --check
make type    # mypy
make test    # pytest with the 90% coverage gate
```

## Writing a new plugin

1. Add a module in `app/plugins/` with a class extending `Plugin`.
2. Declare a Pydantic `Params` model and set `params_model`.
3. Implement `async def run(self, params, context)`; add `compensate()` if the
   action can be undone (set `supports_rollback = True`).
4. Decorate the class with `@register` and import the module in
   `app/plugins/__init__.py`.
5. File plugins must resolve user paths through `context.safe_path(...)`.
6. Add tests. That's it — no core changes required.

## Conventions

- Keep the layer boundaries (see `docs/ARCHITECTURE.md`); only adapters touch a
  vendor library or the database.
- Everything in `app/` is fully typed; mypy runs in strict-ish mode.
- Raise an `AppError` subclass for expected failures — it becomes an RFC 7807
  response with a `trace_id`.
- Short imperative commit subjects, a body explaining the *why*.
