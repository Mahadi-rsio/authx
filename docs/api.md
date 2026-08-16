# API

Base URL: `http://localhost:8000` in development.
Interactive docs: <http://localhost:8000/docs> (OpenAPI at `/openapi.json`).

> **Status:** Phase 3 (partial). Health plus a development-only tenant
> authentication endpoint (`POST /api/v1/auth/tenant/login`) exist. User
> registration and user login arrive later under `API_V1_PREFIX`
> (`/api/v1`).

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

## Planned routes (Phase 3)

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- Session/JWT issuance backed by Redis
- User password hashing and credential storage