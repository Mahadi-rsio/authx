# Project

## What this is

`authx` is the authentication service for PageX. It provides a multi-tenant
identity foundation: tenancy, users, and provider identities, with the
intention of growing into full authentication (password, OAuth, magic links,
sessions) in later phases.

## Goals

- Production-oriented, minimal, and maintainable.
- Strict multi-tenant isolation enforced at the database and application layers.
- Async end to end (asyncpg + SQLAlchemy async + Redis asyncio).
- Schema changes managed with Alembic migrations.

## Tech stack

| Concern            | Choice                              |
| ------------------ | ----------------------------------- |
| Language           | Python >= 3.12                      |
| Framework          | FastAPI                             |
| ORM                | SQLAlchemy 2.x (async)              |
| Driver             | asyncpg                             |
| Migrations         | Alembic                             |
| Validation         | Pydantic v2 + pydantic-settings     |
| Cache / sessions   | Redis (`redis.asyncio`)             |
| HTTP client        | httpx                               |
| Tests              | pytest, pytest-asyncio              |
| Lint / format      | ruff                                |
| Dependency mgmt    | uv (`pyproject.toml` + `uv.lock`)   |

## Phases

| Phase | Scope                                                            | Status        |
| ----- | ---------------------------------------------------------------- | ------------- |
| 1     | App entrypoint, config, async DB, Redis, health, migrations, CI  | Done          |
| 2     | Multi-tenant foundation: Tenant/User/Identity, TenantContext     | Done          |
| 3     | Password auth, sessions/JWT, authenticated tenant resolution     | Partial — tenant authentication (development mock API keys) plus real user registration, user email/password login, and User Access Tokens done; refresh tokens and Redis sessions pending |
| 4+    | OAuth providers, magic links, API keys, advanced sessions        | Not started   |

See the Phase 3 section in [architecture.md](architecture.md) for the planned
work.

## Package layout

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
```

## Running locally

See the README for quick start. Both PostgreSQL and Redis run via
`docker compose up -d`.

## Configuration

Settings live in `app/core/config.py` and are loaded from environment
variables (case-insensitive) or an `.env` / `.env.local` file. See
`.env.example` for the full list.

| Variable              | Default                                              |
| --------------------- | ---------------------------------------------------- |
| `APP_NAME`            | `authx`                                              |
| `APP_ENV`             | `development`                                        |
| `DEBUG`               | `false`                                              |
| `API_V1_PREFIX`       | `/api/v1`                                            |
| `DATABASE_URL`        | `postgresql+asyncpg://authx:authx@localhost:5432/authx` |
| `DATABASE_ECHO`       | `false`                                              |
| `DATABASE_POOL_SIZE`  | `5`                                                  |
| `DATABASE_MAX_OVERFLOW`| `10`                                                 |
| `REDIS_URL`           | `redis://localhost:6379/0`                           |
| `TENANT_API_TOKEN_SECRET` | `dev-tenant-api-token-secret-change-me` (HS256 key; override in prod) |
| `TENANT_API_TOKEN_ALGORITHM` | `HS256`                                       |
| `TENANT_API_TOKEN_EXPIRE_MINUTES` | `60`                                        |
| `USER_ACCESS_TOKEN_SECRET` | `dev-user-access-token-secret-change-me` (HS256 key; override in prod) |
| `USER_ACCESS_TOKEN_ALGORITHM` | `HS256`                                      |
| `USER_ACCESS_TOKEN_EXPIRE_MINUTES` | `60`                                      |
| `DEV_TENANT_CREDENTIALS` | two mock tenants with API keys (JSON array; development only) |