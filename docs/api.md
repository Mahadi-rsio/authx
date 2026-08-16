# API

Base URL: `http://localhost:8000` in development.
Interactive docs: <http://localhost:8000/docs> (OpenAPI at `/openapi.json`).

> **Status:** Phase 3. Development tenant authentication plus real user
> registration, user email/password login, and user access tokens are
> implemented under `API_V1_PREFIX` (`/api/v1`).

## GET /health

Liveness check reporting connectivity to backing services. Returns HTTP 200
even when a dependency is down (reported as `error`); a strict readiness
endpoint is planned for Phase 3.

Response model: `HealthResponse`

| Field     | Type                       | Description                          |
| --------- | -------------------------- | ------------------------------------ |
| `status`  | `"ok"` \| `"error"`        | `ok` when every check passes         |
| `version` | `string`                   | Application version                  |
| `checks`  | `object`                   | Per-service check results            |

`checks` keys: `database`, `redis`. Each value is `"ok"` or `"error"`.

### Example

```http
GET /health
```

```json
{
  "status": "ok",
  "version": "0.1.0",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

### 200 responses

```json
{ "status": "error", "version": "0.1.0", "checks": { "database": "error", "redis": "ok" } }
```

## Tenant identification (development)

Protected endpoints (Phase 3) will resolve the current tenant via the
`get_tenant_context` dependency. In development the tenant is resolved from the
`X-Tenant-Id` header and validated against the database.

```http
X-Tenant-Id: <tenant-uuid>
```

This is a **development bootstrap only** and is replaced by authenticated
resolution in Phase 3 — client-supplied tenant ids are never trusted blindly.

## Tenant API Token (development only)

Authenticates a **tenant** (not a user) and is required for tenant-level
operations such as user registration. This is a development-only
mechanism; nothing is seeded in production.

### POST /api/v1/auth/tenant/login

Authenticates a development tenant by email + password and returns a
**Tenant API Token**.

Request body: `TenantLoginRequest`

| Field      | Type     | Description                     |
| ---------- | -------- | ------------------------------- |
| `email`    | `string` | Tenant login email              |
| `password` | `string` | Tenant login password           |

Response: `TokenResponse`

| Field          | Type     | Description             |
| -------------- | -------- | ----------------------- |
| `access_token` | `string` | Signed Tenant API Token |
| `token_type`   | `"bearer"` | Always `bearer`       |

```http
POST /api/v1/auth/tenant/login
Content-Type: application/json

{ "email": "tenant-a@example.com", "password": "TenantA123!" }
```

```json
{ "access_token": "eyJhbGciOiJIUzI1NiIs...", "token_type": "bearer" }
```

#### Errors

| Status | Body detail               | Condition                        |
| ------ | ------------------------- | -------------------------------- |
| `401`  | `"Invalid email or password"` | Unknown tenant or wrong password |

Both failures return the same body to avoid tenant enumeration.

### Using a Tenant API Token

Protected tenant endpoints use the `get_authenticated_tenant` dependency,
which validates the token signature and expiration, requires
`principal_type == "tenant"`, and loads the tenant before returning a
`TenantContext`.

```http
Authorization: Bearer <tenant-api-token>
```

The trusted tenant identity comes **only** from the token. `X-Tenant-Id` is
never trusted as the authenticated identity — sending a different
`X-Tenant-Id` does not change the tenant in a valid token.

### Token claims

| Claim            | Type     | Description                                  |
| ---------------- | -------- | -------------------------------------------- |
| `sub`            | `string` | Tenant principal id (same as `tenant_id`)    |
| `principal_type` | `"tenant"` | Marks this as a tenant token             |
| `tenant_id`      | `string` | Trusted tenant UUID                          |
| `iat`            | `number` | Issued-at unix timestamp                     |
| `exp`            | `number` | Expiration unix timestamp                    |
| `jti`            | `string` | Token/session identifier (random UUID)       |

### Mock credentials (development)

| Tenant   | Email                  | Password      |
| -------- | ---------------------- | ------------- |
| Tenant A | `tenant-a@example.com` | `TenantA123!` |
| Tenant B | `tenant-b@example.com` | `TenantB123!` |

Passwords are stored as Argon2id hashes only; configurable via
`DEV_TENANT_CREDENTIALS`.

## User authentication (real credentials)

Users authenticate with a real email + password stored as an Argon2id hash
in `password_credentials`. There are two strictly separated token types:

- **Tenant API Token** (`principal_type="tenant"`) — authenticates a tenant;
  required for tenant-level operations including user registration and user
  login.
- **User Access Token** (`principal_type="user"`) — authenticates an
  individual user; required for user-protected endpoints.

A Tenant API Token is **never** accepted by user-protected endpoints and a
User Access Token is **never** accepted by tenant-level endpoints.

### POST /api/v1/auth/users/register

Registers a user **inside the authenticated tenant**. Requires a valid
**Tenant API Token** — the tenant comes ONLY from the token; a `tenant_id`
in the request body is ignored.

Request body: `UserRegisterRequest`

| Field      | Type     | Description                 |
| ---------- | -------- | --------------------------- |
| `email`    | `string` | User email (stored lowercase, unique per tenant) |
| `name`     | `string` | Display name                |
| `password` | `string` | Plaintext password (hashed with Argon2id; never stored) |

```http
POST /api/v1/auth/users/register
Authorization: Bearer <tenant-api-token>
Content-Type: application/json

{ "email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!" }
```

Response `201`: `UserResponse`

| Field            | Type      | Description                   |
| ---------------- | --------- | ----------------------------- |
| `id`             | `string`  | User UUID                     |
| `tenant_id`      | `string`  | Owning tenant UUID (from the token) |
| `email`          | `string`  | Normalized lowercase email    |
| `name`           | `string`  | Display name                  |
| `email_verified` | `boolean` | Always `false` at registration |

#### Errors

| Status | Detail                                     | Condition                              |
| ------ | ------------------------------------------ | -------------------------------------- |
| `401`  | `"Invalid token"` / `"Token has expired"`  | Missing/invalid/expired Tenant API Token |
| `409`  | `"A user with this email already exists in this tenant"` | Duplicate email in the same tenant |

### POST /api/v1/auth/users/login

Authenticates a user **within the authenticated tenant** and issues a
**User Access Token**. Requires a valid **Tenant API Token** so the email
lookup is scoped to one tenant (the same email can exist independently in
different tenants).

Request body: `UserLoginRequest`

| Field      | Type     | Description                 |
| ---------- | -------- | --------------------------- |
| `email`    | `string` | User email                  |
| `password` | `string` | Plaintext password          |

```http
POST /api/v1/auth/users/login
Authorization: Bearer <tenant-api-token>
Content-Type: application/json

{ "email": "alice@example.com", "password": "AlicePassword123!" }
```

Response: `TokenResponse`

| Field          | Type      | Description                |
| -------------- | --------- | -------------------------- |
| `access_token` | `string`  | Signed User Access Token   |
| `token_type`   | `"bearer"`| Always `bearer`            |

#### Errors

| Status | Body detail               | Condition                        |
| ------ | ------------------------- | -------------------------------- |
| `401`  | `"Invalid email or password"` | Unknown user (in this tenant) or wrong password |
| `401`  | `"Invalid token"` | Missing/invalid Tenant API Token |

### User Access Token claims

| Claim            | Type     | Description                                  |
| ---------------- | -------- | -------------------------------------------- |
| `sub`            | `string` | User principal id (same as `user_id`)        |
| `principal_type` | `"user"` | Marks this as a user token                   |
| `user_id`        | `string` | User UUID                                    |
| `tenant_id`      | `string` | Owning tenant UUID                           |
| `iat`            | `number` | Issued-at unix timestamp                     |
| `exp`            | `number` | Expiration unix timestamp                    |
| `jti`            | `string` | Token/session identifier (random UUID)       |

### GET /api/v1/auth/users/me

Returns the authenticated user. Requires a valid **User Access Token** (a
Tenant API Token is rejected).

```http
GET /api/v1/auth/users/me
Authorization: Bearer <user-access-token>
```

Response `200`: `UserResponse`

```json
{
  "id": "…",
  "tenant_id": "…",
  "email": "alice@example.com",
  "name": "Alice",
  "email_verified": false
}
```

#### Errors

| Status | Detail                  | Condition                              |
| ------ | ----------------------- | -------------------------------------- |
| `401`  | `"Invalid token"` / `"Token has expired"` | Missing/invalid/expired User Access Token, wrong `principal_type`, or the user no longer belongs to the claimed tenant |

## Example: end-to-end

1. `POST /api/v1/auth/tenant/login` with `tenant-a@example.com` /
   `TenantA123!` → **Tenant API Token**.
2. `POST /api/v1/auth/users/register` (Bearer tenant token) → creates
   `alice@example.com` under Tenant A with a hashed password.
3. `POST /api/v1/auth/users/login` (Bearer tenant token) → **User Access
   Token**.
4. `GET /api/v1/auth/users/me` (Bearer user token) → Alice's profile.

## Planned routes (Phase 4+)

- Password reset and email verification.
- OAuth providers, magic links, API keys, refresh tokens, advanced sessions.