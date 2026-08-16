# authx

Multi-tenant authentication service for PageX.

A production-oriented foundation built with Python, FastAPI, PostgreSQL,
SQLAlchemy 2.x (async), Alembic, Pydantic v2, Redis, and asyncpg.

> **Status:** Phase 2 — multi-tenant foundation. OAuth, magic links, password
> authentication, and advanced sessions are **not** implemented yet.

## Quick start

```bash
docker compose up -d            # PostgreSQL 16 + Redis 7
uv sync                         # install dependencies (Python >= 3.12)
uv run alembic upgrade head     # apply migrations
uv run uvicorn app.main:app --reload
```

Open <http://localhost:8000/health> and <http://localhost:8000/docs>.

## Common commands

```bash
uv run pytest                          # run tests (26 passing)
uv run pytest -m integration           # integration tests only
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run alembic revision --autogenerate -m "describe change"   # new migration
uv run alembic upgrade head            # apply migrations
uv run alembic check                   # verify models match migrations
```

## Project layout

```
app/
  api/          FastAPI routers and request dependencies
  auth/         (Phase 3) authentication
  tenants/      TenantContext, tenant resolution
  providers/    (Phase 3) OAuth / identity providers
  models/       SQLAlchemy ORM models and mixins
  repositories/ Data access layer (tenant-scoped)
  services/     Business logic (transaction boundary)
  core/         Settings, Redis client
  database/     Async engine, session management, declarative base
  workers/      (future) background workers
alembic/        Database migrations
tests/          Unit and integration tests
docs/           Project documentation
```

## Documentation

- [project.md](docs/project.md) — overview, tech stack, phases, status
- [architecture.md](docs/architecture.md) — layering, multi-tenancy, decisions
- [database.md](docs/database.md) — schema, constraints, migration workflow
- [api.md](docs/api.md) — HTTP API surface
- [agent.md](docs/agent.md) — contributor / AI agent guide

## Tenant isolation

Every tenant-owned entity carries `tenant_id`, and every tenant-scoped
database operation filters by it. Cross-tenant identity↔user links are
rejected at the database level by a composite foreign key. See
[architecture.md](docs/architecture.md) and [database.md](docs/database.md).