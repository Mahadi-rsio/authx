# API

Base URL: `http://localhost:8000` in development.
Interactive docs: <http://localhost:8000/docs> (OpenAPI at `/openapi.json`).

> **Status:** Phase 2. Only the health endpoint exists. Authentication,
> session, and v1 resource endpoints arrive in Phase 3 under `API_V1_PREFIX`
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

## Planned routes (Phase 3)

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- Session/JWT issuance backed by Redis
- Password hashing and credential storage