# authx

Multi-tenant authentication service for PageX.

A production-oriented foundation built with Python, FastAPI, PostgreSQL,
SQLAlchemy 2.x (async), Alembic, Pydantic v2, Redis, and asyncpg.

> **Status:** Phase 3 (partial) — multi-tenant foundation plus a
> **development-only** tenant authentication system issuing Tenant API
> Tokens. OAuth, magic links, user email/password login, and advanced
> sessions are **not** implemented yet.

## Quick start

```bash
docker compose up -d            # PostgreSQL 16 + Redis 7
uv sync                         # install dependencies (Python >= 3.12)
uv run alembic upgrade head     # apply migrations
uv run uvicorn app.main:app --reload
```

Open <http://localhost:8000/health> and <http://localhost:8000/docs>.

On startup in `development` (`APP_ENV=development`, the default) the app
bootstraps two mock tenants with hashed credentials (see
[Tenant API Token](#tenant-api-token)). Nothing is seeded in production.

## Common commands

```bash
uv run pytest                          # run tests (53 passing)
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

## Tenant API Token

**Development-only tenant authentication.**

A **Tenant API Token** represents an authenticated *tenant* (not a user). It
is required for tenant-level operations — most importantly **user
registration** — and is issued by:

```
POST /api/v1/auth/tenant/login
```

```http
POST /api/v1/auth/tenant/login
Content-Type: application/json

{ "email": "tenant-a@example.com", "password": "TenantA123!" }
```

```json
{ "access_token": "...", "token_type": "bearer" }
```

### Key points

- A Tenant API Token is **NOT** a user access token. User access tokens are
  issued only after a real user email/password login (not implemented yet)
  and contain `user_id` + `tenant_id`.
- The trusted tenant identity comes **only** from the token. Protected
  tenant endpoints must use `get_authenticated_tenant` (a FastAPI
  dependency) — `X-Tenant-Id` is never trusted as the authenticated
  identity, and supplying a different `X-Tenant-Id` cannot change the
  tenant in a valid token.
- Tokens are signed JWTs (`HS256`) with claims `sub`, `principal_type:
  "tenant"`, `tenant_id`, `iat`, `exp`, and `jti`. See
  [docs/architecture.md](docs/architecture.md) for details.
- Development-only; mock tenants are seeded only when `APP_ENV=development`.

### Mock tenant credentials (development only)

| Tenant   | Email                    | Password      | Slug      |
| -------- | ------------------------ | ------------- | --------- |
| Tenant A | `tenant-a@example.com`   | `TenantA123!` | `tenant-a`|
| Tenant B | `tenant-b@example.com`   | `TenantB123!` | `tenant-b`|

Credentials are configurable through `DEV_TENANT_CREDENTIALS` (JSON array
of `{email, password, name, slug}`) and passwords are stored only as
Argon2id hashes — plaintext never touches the database. These credentials
are **never seeded in production**.