# authx

Multi-tenant authentication service for PageX.

A production-oriented foundation built with Python, FastAPI, PostgreSQL,
SQLAlchemy 2.x (async), Alembic, Pydantic v2, Redis, and asyncpg.

> **Status:** Phase 3 — multi-tenant foundation, a **development-only**
> tenant authentication system issuing Tenant API Tokens, and **real user
> email/password authentication** with User Access Tokens. OAuth, magic
> links, refresh tokens, and advanced sessions are **not** implemented yet.

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
uv run pytest                          # run tests
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

## Tenant authentication (Development API Keys)

**Development-only mock tenant authentication.**

Tenant authentication represents an authenticated *tenant* (not a user) and is
required for tenant-level operations — most importantly **user registration** and
**user login**. In development, tenant authentication is performed using a mock
API key sent via the `X-AuthX-API-Key` header:

```http
X-AuthX-API-Key: ax_test_tenant_a_mock_key
```

### Key points

- A Tenant API Key is **NOT** a user access token. User Access Tokens are
  issued only after a real user email/password login and contain
  `user_id` + `tenant_id`.
- The trusted tenant identity comes **only** from the API key resolved via
  `get_authenticated_tenant` (a FastAPI dependency). `X-Tenant-Id` or
  body `tenant_id` fields are never trusted.
- Development-only; mock tenant credentials and API keys are enabled only when
  `APP_ENV=development`. Nothing is seeded or accepted in production.

## User email/password authentication

Users register and log in with a real email + password stored as an
Argon2id hash (plaintext never touches the database). Both registration and
login require a Tenant API Key so the tenant comes **only** from the
API key.

```
POST /api/v1/auth/users/register      # X-AuthX-API-Key: <api-key>
POST /api/v1/auth/users/login         # X-AuthX-API-Key: <api-key> -> User Access Token
GET  /api/v1/auth/users/me            # Authorization: Bearer <user-access-token>
```

### Example

```http
POST /api/v1/auth/users/register
X-AuthX-API-Key: ax_test_tenant_a_mock_key
Content-Type: application/json

{ "email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!" }
```

```http
POST /api/v1/auth/users/login
X-AuthX-API-Key: ax_test_tenant_a_mock_key
Content-Type: application/json

{ "email": "alice@example.com", "password": "AlicePassword123!" }
```

```json
{ "access_token": "...", "token_type": "bearer" }
```

The returned token is a **User Access Token** (`principal_type: "user"`) —
use it for user-protected endpoints such as `GET /api/v1/auth/users/me`:

```http
GET /api/v1/auth/users/me
Authorization: Bearer <user-access-token>
```

See [docs/api.md](docs/api.md) for the full reference.

### Mock tenant credentials (development only)

| Tenant   | Email                    | Password      | Slug      | Mock API Key                  |
| -------- | ------------------------ | ------------- | --------- | ----------------------------- |
| Tenant A | `tenant-a@example.com`   | `TenantA123!` | `tenant-a`| `ax_test_tenant_a_mock_key`   |
| Tenant B | `tenant-b@example.com`   | `TenantB123!` | `tenant-b`| `ax_test_tenant_b_mock_key`   |

Credentials are configurable through `DEV_TENANT_CREDENTIALS` (JSON array
of `{email, password, name, slug, api_key}`). Plaintext passwords never touch
the database. These mock credentials and keys are **never active in production**.