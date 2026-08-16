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

## Tenant authentication (Host + API Key)

Tenant authentication identifies and authenticates a **tenant** (not a user)
and is required for tenant-level operations such as user registration and user
login.

Each tenant is addressed via a dedicated **authentication hostname**:

```
auth.<tenant-slug>.example.com
```

Authentication requires **both**:
1. A matching `Host` header (`auth.<slug>.example.com`) — identifies *which* tenant.
2. A valid `X-AuthX-API-Key` header — proves the caller is authorized for that tenant.

**Both must agree on the same tenant.** A key from Tenant B sent to Tenant A's
hostname returns `401`. Neither can override the other.

### Local development

Add to `/etc/hosts`:

```
127.0.0.1  auth.tenant-a.example.com
127.0.0.1  auth.tenant-b.example.com
```

Then requests to `http://auth.tenant-a.example.com:8000/...` will route to the
locally running server with the correct `Host` header set automatically.

### Mock API keys (development only)

| Tenant   | Slug       | Auth Hostname                   | Mock API Key                  |
| -------- | ---------- | ------------------------------- | ----------------------------- |
| Tenant A | `tenant-a` | `auth.tenant-a.example.com`     | `ax_test_tenant_a_mock_key`   |
| Tenant B | `tenant-b` | `auth.tenant-b.example.com`     | `ax_test_tenant_b_mock_key`   |

Mock keys are active only when `APP_ENV=development` and are
**never active in production**.

### Using a Tenant API Key

Protected tenant endpoints use the `get_authenticated_tenant` dependency,
which validates both the `Host` header and the `X-AuthX-API-Key` header and
resolves the `TenantContext`.

```http
Host: auth.tenant-a.example.com
X-AuthX-API-Key: ax_test_tenant_a_mock_key
```

The trusted tenant identity comes **only** from the dual host+API-key
validation. `tenant_id` in the request body or query parameters is never
trusted.

### Error codes

| Status | Condition |
| ------ | --------- |
| `401`  | Missing `X-AuthX-API-Key` |
| `401`  | Invalid or unknown API key |
| `401`  | API key tenant does not match hostname tenant |
| `404`  | Hostname does not match `auth.<slug>.example.com` or tenant slug not found |



## User authentication (real credentials)

Users authenticate with a real email + password stored as an Argon2id hash
in `password_credentials`. There are two strictly separated authentication types:

- **Tenant API Key** (`X-AuthX-API-Key`) — authenticates a tenant;
  required for tenant-level operations including user registration and user
  login.
- **User Access Token** (`principal_type="user"`) — authenticates an
  individual user; required for user-protected endpoints.

### POST /api/v1/auth/users/register

Registers a user **inside the authenticated tenant**. Requires a valid
**Tenant API Key** via `X-AuthX-API-Key` — the tenant comes ONLY from the key;
a `tenant_id` in the request body is ignored.

Request body: `UserRegisterRequest`

| Field      | Type     | Description                 |
| ---------- | -------- | --------------------------- |
| `email`    | `string` | User email (stored lowercase, unique per tenant) |
| `name`     | `string` | Display name                |
| `password` | `string` | Plaintext password (hashed with Argon2id; never stored) |

```http
POST /api/v1/auth/users/register
Host: auth.tenant-a.example.com
X-AuthX-API-Key: ax_test_tenant_a_mock_key
Content-Type: application/json

{ "email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!" }
```


Response `201`: `UserResponse`

| Field            | Type      | Description                   |
| ---------------- | --------- | ----------------------------- |
| `id`             | `string`  | User UUID                     |
| `tenant_id`      | `string`  | Owning tenant UUID (from API key) |
| `email`          | `string`  | Normalized lowercase email    |
| `name`           | `string`  | Display name                  |
| `email_verified` | `boolean` | Always `false` at registration |

#### Errors

| Status | Detail                                     | Condition                              |
| ------ | ------------------------------------------ | -------------------------------------- |
| `401`  | `"Missing API key"` / `"Invalid API key"`  | Missing or invalid `X-AuthX-API-Key`   |
| `409`  | `"A user with this email already exists in this tenant"` | Duplicate email in the same tenant |

### POST /api/v1/auth/users/login

Authenticates a user **within the authenticated tenant** and issues a
**User Access Token**. Requires a valid **Tenant API Key** so the email
lookup is scoped to one tenant (the same email can exist independently in
different tenants).

Request body: `UserLoginRequest`

| Field      | Type     | Description                 |
| ---------- | -------- | --------------------------- |
| `email`    | `string` | User email                  |
| `password` | `string` | Plaintext password          |

```http
POST /api/v1/auth/users/login
X-AuthX-API-Key: ax_test_tenant_a_mock_key
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
| `401`  | `"Missing API key"` / `"Invalid API key"` | Missing or invalid `X-AuthX-API-Key` |

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

Returns the authenticated user. Requires a valid **User Access Token**.

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

1. `POST /api/v1/auth/users/register` (`X-AuthX-API-Key: ax_test_tenant_a_mock_key`)
   → creates `alice@example.com` under Tenant A with a hashed password.
2. `POST /api/v1/auth/users/login` (`X-AuthX-API-Key: ax_test_tenant_a_mock_key`)
   → **User Access Token**.
3. `GET /api/v1/auth/users/me` (`Authorization: Bearer <user-access-token>`)
   → Alice's profile.

## Planned routes (Phase 4+)

- Real tenant dashboard & API key creation/management.
- Password reset and email verification.
- OAuth providers, magic links, refresh tokens, advanced sessions.