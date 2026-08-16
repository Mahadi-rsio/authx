# Agent / Contributor Guide

Guidance for humans and AI agents working in this repository. Follow the
existing patterns; do not rewrite working code without reason.

## Environment

- Python >= 3.12, managed with **uv**. Do not use `pip install` directly.
- PostgreSQL and Redis run in Docker (`docker compose up -d`).
- Linux/macOS assumed; commands below use bash.

## Core commands

```bash
uv sync                          # install all deps (incl. dev group)
uv sync --dev                    # explicit dev-group sync
uv run uvicorn app.main:app --reload   # run the dev server
uv run pytest                    # full test suite
uv run pytest -m integration     # integration tests only
uv run ruff check .              # lint
uv run ruff format .             # format (then format --check)
uv run alembic upgrade head      # apply migrations
uv run alembic revision --autogenerate -m "message"
uv run alembic check             # ensure models == migrations
```

After any change: run `ruff format`, `ruff check`, and `pytest`.

## Code conventions

- **Python 3.12**, type hints everywhere, `from __future__` not needed.
- **Async only** in the data path: `async def`, `AsyncSession`, `redis.asyncio`.
- Use `Annotated[X, Depends(...)]` for FastAPI dependency injection (avoids
  `B008`). Do not use `Depends(...)` as a default value.
- Use `StrEnum` instead of `str, Enum`.
- Line length 100. Ruff enforces `E F W I UP B ASYNC`.

## Tenant isolation rules (non-negotiable)

1. Every tenant-owned model inherits `TenantOwnedMixin` (adds `tenant_id`,
   FK to `tenants.id`, indexed).
2. Every tenant-scoped query goes through `TenantScopedRepository`
   (`_scoped_select` / `_scoped_get`) and **always** filters by `tenant_id`.
   There is no unscoped "get by pk" for tenant-owned data.
3. Services receive a `TenantContext`, never a raw `tenant_id` from request
   input. Resolve tenants only via a `TenantResolver`.
4. Emails and `(provider, provider_user_id)` uniqueness must be tenant-scoped
   — never add a global unique constraint on tenant-owned data.
5. New tenant-owned tables must carry a composite FK where cross-tenant links
   are possible (see `identities`).

## Layering

- `api/` → `services/` → `repositories/` → `models/` → `database/`. No
  backwards imports (e.g. repositories must not import services).
- **Repositories** do not commit; **services** are the transaction boundary.
- Repositories receive an `AsyncSession` in their constructor.

## Testing conventions

- Tests live in `tests/`. Async tests are auto-detected
  (`asyncio_mode = "auto"` in `pyproject.toml`).
- **Integration tests** require PostgreSQL and are marked
  `pytest.mark.integration`. They use the `db_session` fixture (isolated
  `authx_test` database, schema created/dropped per test). They are skipped
  automatically when Postgres is unreachable.
- Prove tenant isolation explicitly: create the same data in two tenants and
  assert cross-tenant lookups return nothing; assert cross-tenant writes raise
  `IntegrityError`.

## Gotchas

- `Session.rollback()` **expires all loaded objects**. After an
  `IntegrityError` + rollback, do not access attributes on previously created
  ORM instances (reloading triggers a sync reconnect). Capture ids before the
  failing operation.
- `Session.commit()` inside services uses `expire_on_commit=False`.
- `authx_test` is created automatically by `tests/conftest.py`; it is a test
  artifact and can be dropped and recreated freely.
- Alembic-generated files under `alembic/versions/` use legacy typing; lint
  ignores are configured for them. Do not hand-edit generated revisions.
- Constraint names are deterministic (naming convention in
  `app/database/base.py`). Name compound constraints explicitly to avoid
  collisions (e.g. two uniques on `users`).

## Model changes checklist

1. Edit the model in `app/models/`.
2. `uv run alembic revision --autogenerate -m "..."` and review the diff.
3. `uv run alembic upgrade head`.
4. `uv run alembic check` must report no drift.
5. Add/update tests (integration for DB behavior).
6. Run `uv run ruff format . && uv run ruff check . && uv run pytest`.