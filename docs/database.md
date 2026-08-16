# Database

PostgreSQL 16 via Docker. Managed exclusively with Alembic migrations; the
schema is never hand-edited.

## Connection

`DATABASE_URL` (asyncpg driver), configured in `app/core/config.py`. The
engine/session setup lives in `app/database/session.py`.

## Schema

Five tables: `tenants`, `tenant_credentials`, `users`, `identities`,
`password_credentials`.

### tenants

Root of the tenancy hierarchy. Not tenant-owned.

| Column      | Type                       | Notes                |
| ----------- | -------------------------- | -------------------- |
| `id`        | `uuid` PK                  | `gen_random_uuid()`  |
| `name`      | `varchar(255)` NOT NULL    |                      |
| `slug`      | `varchar(120)` NOT NULL    | unique index         |
| `created_at`| `timestamptz` NOT NULL     | `now()` default      |
| `updated_at`| `timestamptz` NOT NULL     | `now()` default      |

### tenant_credentials

Development-only credentials used to authenticate a **tenant** (not a user).
One row per tenant; passwords are stored as Argon2id hashes — plaintext
never touches the database.

| Column          | Type                       | Notes                               |
| --------------- | -------------------------- | ----------------------------------- |
| `id`            | `uuid` PK                  | `gen_random_uuid()`                 |
| `tenant_id`     | `uuid` NOT NULL            | FK → `tenants.id`, indexed, CASCADE, UNIQUE |
| `email`         | `varchar(320)` NOT NULL    | unique index (login by email)       |
| `password_hash` | `varchar(255)` NOT NULL    | Argon2id hash                       |
| `created_at`    | `timestamptz` NOT NULL     |                                     |
| `updated_at`    | `timestamptz` NOT NULL     |                                     |

Constraints:

- `uq_tenant_credentials_tenant_id` — `UNIQUE (tenant_id)` (one credential per tenant).
- Unique index `ix_tenant_credentials_email` — tenant login is by email alone.

> Seeded only in development (`APP_ENV=development`) from
> `DEV_TENANT_CREDENTIALS`; never seeded in production.

### users

Belongs to exactly one tenant. Emails are **tenant-scoped**, not global.

| Column          | Type                       | Notes                          |
| --------------- | -------------------------- | ------------------------------ |
| `id`            | `uuid` PK                  | `gen_random_uuid()`            |
| `tenant_id`     | `uuid` NOT NULL            | FK → `tenants.id`, indexed, CASCADE |
| `email`         | `varchar(320)` NOT NULL    | stored lowercase               |
| `name`          | `varchar(255)` NOT NULL    |                                |
| `avatar_url`    | `varchar(2048)` NULL       |                                |
| `email_verified`| `boolean` NOT NULL         | default `false`                |
| `created_at`    | `timestamptz` NOT NULL     |                                |
| `updated_at`    | `timestamptz` NOT NULL     |                                |

Constraints:

- `uq_users_tenant_id_email` — `UNIQUE (tenant_id, email)` (tenant-scoped email uniqueness).
- `uq_users_tenant_id_id` — `UNIQUE (tenant_id, id)` (required to back the composite FK from `identities`; also accelerates tenant-scoped lookups).

### identities

A provider-specific identity linked to exactly one user **within one tenant**.

| Column            | Type                       | Notes                          |
| ----------------- | -------------------------- | ------------------------------ |
| `id`              | `uuid` PK                  | `gen_random_uuid()`            |
| `tenant_id`       | `uuid` NOT NULL            | FK → `tenants.id`, indexed, CASCADE |
| `user_id`         | `uuid` NOT NULL            | indexed                        |
| `provider`        | `varchar(64)` NOT NULL     | e.g. `password`, `google`      |
| `provider_user_id`| `varchar(512)` NOT NULL    |                                |
| `provider_email`  | `varchar(320)` NULL        |                                |
| `created_at`      | `timestamptz` NOT NULL     |                                |
| `updated_at`      | `timestamptz` NOT NULL     |                                |

Constraints:

- `uq_identities_tenant_provider_provider_user_id` — `UNIQUE (tenant_id, provider, provider_user_id)`.
- `fk_identities_tenant_user_users` — composite FK `(tenant_id, user_id) -> users(tenant_id, id)`. This is the database-level guarantee that an identity can never reference a user in a different tenant.
- `fk_identities_tenant_id_tenants` — FK `tenant_id -> tenants.id ON DELETE CASCADE`.

### password_credentials

Real, database-backed password credentials for **users** (one per user per
tenant). Plaintext passwords never touch the database — only the Argon2id
`password_hash` is stored.

| Column               | Type                       | Notes                                |
| -------------------- | -------------------------- | ------------------------------------ |
| `id`                 | `uuid` PK                  | `gen_random_uuid()`                  |
| `tenant_id`          | `uuid` NOT NULL            | FK → `tenants.id`, indexed, CASCADE  |
| `user_id`            | `uuid` NOT NULL            | indexed                              |
| `password_hash`      | `varchar(255)` NOT NULL    | Argon2id hash                        |
| `password_changed_at`| `timestamptz` NOT NULL     | `now()` default                      |
| `created_at`         | `timestamptz` NOT NULL     |                                      |
| `updated_at`         | `timestamptz` NOT NULL     |                                      |

Constraints:

- `uq_password_credentials_tenant_id_user_id` — `UNIQUE (tenant_id, user_id)` (one credential per user per tenant).
- `fk_password_credentials_tenant_user_users` — composite FK `(tenant_id, user_id) -> users(tenant_id, id)`. Database-level guarantee that a credential can never reference a user in a different tenant.
- `fk_password_credentials_tenant_id_tenants` — FK `tenant_id -> tenants.id ON DELETE CASCADE`.

## Identifier strategy

All primary keys are UUIDs (`uuid` type):

- Python default: `uuid.uuid4()` (`UuidPkMixin` in `app/models/mixins.py`).
- Server default: `gen_random_uuid()` (built into PostgreSQL 13+, no extension).

## Tenant isolation guarantees

1. Every tenant-owned table indexes `tenant_id`.
2. Every tenant-scoped query flows through `TenantScopedRepository`, which
   requires a `tenant_id` and filters by it.
3. Emails and `(provider, provider_user_id)` are unique **within a tenant**,
   never globally.
4. The composite FK on `identities` and `password_credentials` makes
   cross-tenant identity↔user and credential↔user links a database constraint
   violation.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe change"   # create
uv run alembic upgrade head                                   # apply
uv run alembic downgrade -1                                   # roll back
uv run alembic check                                          # detect model/migration drift
uv run alembic history                                        # revision list
```

### Current revisions

| Revision     | Description                  |
| ------------ | ---------------------------- |
| `e13bba67ccf8` | initial empty (baseline)     |
| `a2585b458e1d` | add tenants, users, identities |
| `95ab5b81e296` | add tenant credentials       |
| `07b6bb28ab24` | add password credentials (head) |

Alembic's `env.py` (`alembic/env.py`) imports the application settings to
derive the connection URL and imports `app.models` so autogenerate sees every
table.

## Testing against a database

`tests/conftest.py` provisions an isolated `authx_test` database (created on
the fly if missing) and builds the schema per test via
`Base.metadata.create_all`, then drops it. Integration tests are marked
`integration` and are skipped automatically when PostgreSQL is unreachable.

```bash
uv run pytest                 # unit + integration
uv run pytest -m integration  # integration only
```