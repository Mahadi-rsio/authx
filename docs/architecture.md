# Architecture

## Layering

Dependencies point inward; every layer only imports from layers below it.

```
api ──> services ──> repositories ──> models ──> database
  │         │              │
  └─────────┴──────────────┴──────> core (config, redis)
```

- **api** (`app/api/`): routers and FastAPI request dependencies. Translates
  HTTP into service calls. No SQL.
- **services** (`app/services/`): business logic and the **transaction
  boundary** (each service method commits). Receive a resolved
  `TenantContext`, never raw client input.
- **repositories** (`app/repositories/`): data access. Tenant-scoped by
  construction. No business rules.
- **models** (`app/models/`): SQLAlchemy ORM models + mixins.
- **database** (`app/database/`): async engine, session factory, declarative
  base with a deterministic naming convention.
- **core** (`app/core/`): settings (`pydantic-settings`) and the Redis client.

## Multi-tenancy

Two layers of enforcement, defense in depth:

1. **Database layer.** Every tenant-owned table has a `tenant_id` column with
   a foreign key to `tenants.id`. `Identity` additionally carries a composite
   foreign key `(tenant_id, user_id) -> users(tenant_id, id)`, so a cross-tenant
   identity↔user link is impossible at the database level.
2. **Application layer.** `TenantScopedRepository` only exposes tenant-scoped
   queries (`_scoped_select` / `_scoped_get`); there is deliberately no
   unscoped "get by primary key". Services always receive a `TenantContext`.

### TenantContext

`TenantContext` (`app/tenants/context.py`) is a frozen value object holding
the resolved `tenant_id` (and optional slug). It is **never constructed from
raw client input**; it is produced by a `TenantResolver`.

`MockApiKeyTenantResolver` (`app/tenants/resolver.py`) resolves the tenant from
the `X-AuthX-API-Key` header, matches it against development mock tenant
credentials in settings, and validates against the database before returning
a `TenantContext`.

## Tenant authentication (development mock API keys)

A **development-only** tenant authentication system validates **Tenant API
Keys** via `X-AuthX-API-Key`. An API key represents an authenticated *tenant*
and is required for tenant-level operations such as user registration and
login.

### Flow

```
X-AuthX-API-Key
        ↓
MockApiKeyTenantResolver.resolve(api_key)   (matches dev mock credentials)
        ↓
TenantRepository.get_by_slug(...)            (database load)
        ↓
get_authenticated_tenant() dependency        (returns TenantContext)
        ↓
TenantContext
```

### Components

- `app/tenants/resolver.py` — `MockApiKeyTenantResolver` (resolves mock API keys
  in development, disabled in production).
- `app/tenants/context.py` — `TenantContext`, the frozen tenant context.
- `app/core/config.py` — `DevTenantCredential` (with `api_key`) and
  `dev_tenant_credentials`.
- `app/services/dev_seed.py` — idempotent development seed of mock tenants
  and credentials; refuses to run when not in development.
- `app/api/dependencies.py` — `get_authenticated_tenant` (uses `X-AuthX-API-Key`).
- `app/api/auth.py` — `POST /api/v1/auth/users/register`,
  `POST /api/v1/auth/users/login`.

### Trust boundary

The trusted tenant identity comes **only** from the resolved API key
and flows to `TenantContext`. Client-supplied `tenant_id` from request body,
query params, or arbitrary headers is never trusted.

### User authentication (real credentials)

Users authenticate with a real email + password stored as an Argon2id hash.
A **User Access Token** (signed JWT) represents an authenticated *user within a tenant*
and is required for user-protected endpoints such as `/users/me`.

### Flow

```
Tenant API Key (X-AuthX-API-Key)
        ↓
UserAuthService.register_user(context, email, name, password)  (Argon2id hash)
        ↓
User + PasswordCredential                                        (per-tenant)
        ↓
UserAuthService.authenticate_user(context, email, password)     (tenant-scoped lookup + Argon2id verify)
        ↓
UserPrincipal
        ↓
UserAuthService.issue_user_token(...)                           (signed User Access Token)
        ↓
get_authenticated_user() dependency                             (validate token)
        ↓
UserContext
```

### Components

- `app/auth/principal.py` — `UserPrincipal` (token principal) and
  `UserContext` (authenticated request context).
- `app/auth/tokens.py` — `create_user_access_token` /
  `decode_user_access_token` (HS256 JWT). Claims: `sub`, `principal_type="user"`,
  `user_id`, `tenant_id`, `iat`, `exp`, `jti`. `principal_type` is validated
  strictly.
- `app/models/password_credential.py` — `password_credentials` table
  (one per user per tenant, Argon2id `password_hash` only, composite FK
  `(tenant_id, user_id) -> users(tenant_id, id)`).
- `app/repositories/password_credential.py` — tenant-scoped credential
  lookup by user.
- `app/services/user_auth_service.py` — register, authenticate, issue user
  tokens (transaction boundary); rejects duplicate emails per tenant.
- `app/api/auth.py` — `POST /api/v1/auth/users/register`,
  `POST /api/v1/auth/users/login`, `GET /api/v1/auth/users/me`.
- `app/api/dependencies.py` — `get_authenticated_user`.

### Trust boundary

The trusted user and tenant identity comes **only** from the User Access
Token (`user_id`/`tenant_id` claims) and is verified against the database:
the user must still exist and belong to the claimed tenant. Registration and
login derive the tenant ONLY from the authenticated Tenant API Key; a
`tenant_id` in the request body is ignored.

## Development seeding

On startup, when `APP_ENV=development`, `app/main.py` calls
`seed_dev_tenants`, creating the two mock tenants and their hashed
credentials if they do not exist. Credentials come from
`settings.dev_tenant_credentials` (`DEV_TENANT_CREDENTIALS`) and are never
seeded in production.

## Request flow (target)

```
HTTP request
  └─ get_db_session (app/database/session.py)
  └─ get_authenticated_tenant (from X-AuthX-API-Key)
       └─ Service method receives TenantContext
            └─ Repository filters by context.tenant_id
                 └─ AsyncSession -> PostgreSQL
```

## Health endpoint

`GET /health` is a **liveness** check: it reports `database` and `redis`
connectivity but returns HTTP 200 even when a dependency is down (marked
`status: "error"`). A strict readiness endpoint (`/ready`, 503 on failure) is
planned for Phase 3.

## Async session management

`app/database/session.py` creates a single `AsyncEngine` (from settings) and
an `async_sessionmaker` with `expire_on_commit=False`. `get_db_session`
yields one session per request. The engine and Redis client are disposed in the
FastAPI lifespan on shutdown.

## Key decisions

- **Async everywhere** — asyncpg, SQLAlchemy async, `redis.asyncio`, async
  pytest (`asyncio_mode = "auto"`).
- **UUID primary keys** — `gen_random_uuid()` server default, `uuid4` Python
  default. Non-sequential, collision-resistant.
- **Composite FK for identity ownership** — the strongest possible guarantee
  against cross-tenant relationships.
- **Repos are per-session and stateless; services own transactions.**
- **Emails normalized and stored lowercase; lookups case-insensitive.**
- **Deterministic constraint naming** via `MetaData.naming_convention` so
  autogenerated migrations stay stable.

## Phase 3 (planned / partial)

1. ✅ Tenant authentication (development mock API keys) — `X-AuthX-API-Key`
   header lookup, `MockApiKeyTenantResolver`, and authenticated tenant
   resolution via `get_authenticated_tenant`.
2. ✅ User registration and user email/password login — real
   `password_credentials` (Argon2id), User Access Tokens, and
   `get_authenticated_user`.
3. Refresh tokens, sessions backed by Redis, and `GET /ready` readiness
   endpoint.