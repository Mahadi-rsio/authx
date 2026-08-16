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

## Tenant authentication (Host + API Key)

**Phase 1 — Development-only mock tenant authentication via hostname + API key.**

Each tenant is addressed via a dedicated authentication hostname:

```
auth.<tenant-slug>.example.com
```

**Both** the hostname and the API key must be supplied and must identify the
**same tenant**. Neither can override the other.

```
Request
   │
   ├── Host: auth.tenant-a.example.com
   │        ↓
   │   Tenant Host Resolver  →  Tenant A
   │
   └── X-AuthX-API-Key: ax_test_tenant_a_mock_key
            ↓
       API Key Validator     →  Tenant A
            │
            └── compare ──────┐
                               ↓
                         TenantContext (Tenant A)
                               ↓
                       Tenant-scoped APIs
```

### Key points

- **Host identifies WHICH tenant** is being accessed.
- **API key proves the caller is authorized** for that tenant.
- Both MUST match. A Tenant B key sent to a Tenant A host returns `401`.
- A Tenant API Key is **NOT** a user access token. User Access Tokens are
  issued only after a real user email/password login and contain
  `user_id` + `tenant_id`.
- The trusted tenant identity comes **only** from `get_authenticated_tenant`
  (a FastAPI dependency). `tenant_id` in the request body, query params, or
  arbitrary headers is **never** trusted.
- Development-only; mock keys are active only when `APP_ENV=development`.

### Local development (/etc/hosts)

Add these entries to `/etc/hosts` so the tenant hostnames resolve to localhost:

```
127.0.0.1  auth.tenant-a.example.com
127.0.0.1  auth.tenant-b.example.com
```

### Mock tenant credentials (development only)

| Tenant   | Slug       | Auth Hostname                         | Mock API Key                  |
| -------- | ---------- | ------------------------------------- | ----------------------------- |
| Tenant A | `tenant-a` | `auth.tenant-a.example.com`           | `ax_test_tenant_a_mock_key`   |
| Tenant B | `tenant-b` | `auth.tenant-b.example.com`           | `ax_test_tenant_b_mock_key`   |

### Example curl commands

**Tenant A:**
```bash
curl -X POST \
  "http://auth.tenant-a.example.com:8000/api/v1/auth/users/register" \
  -H "X-AuthX-API-Key: ax_test_tenant_a_mock_key" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"}'
```

**Tenant B:**
```bash
curl -X POST \
  "http://auth.tenant-b.example.com:8000/api/v1/auth/users/register" \
  -H "X-AuthX-API-Key: ax_test_tenant_b_mock_key" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice B", "password": "AlicePassword123!"}'
```

**Cross-tenant mismatch (returns 401):**
```bash
curl -X POST \
  "http://auth.tenant-a.example.com:8000/api/v1/auth/users/register" \
  -H "X-AuthX-API-Key: ax_test_tenant_b_mock_key" \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"}'
```

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

> **Note:** Credentials are configurable through `DEV_TENANT_CREDENTIALS` (JSON array
> of `{email, password, name, slug, api_key}`). Plaintext passwords never touch
> the database. Mock credentials and keys are **never active in production**.