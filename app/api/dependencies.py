from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import UserContext
from app.auth.tokens import (
    ExpiredTokenError,
    InvalidPrincipalTypeError,
    InvalidTokenError,
    decode_user_access_token,
)
from app.core.config import get_settings
from app.database.session import get_db_session
from app.repositories.user import UserRepository
from app.tenants.context import TenantContext
from app.tenants.resolver import (
    ApiKeyTenantResolver,
    InvalidApiKeyError,
    MissingApiKeyError,
    MissingTenantError,
    MockApiKeyTenantResolver,
    TenantHostResolver,
    TenantMismatchError,
    TenantNotFoundError,
    TenantResolutionError,
)

_api_key_resolver = ApiKeyTenantResolver()
_host_resolver = TenantHostResolver()

# Declared security schemes so Swagger UI shows an Authorize button and
# sends the respective credentials. The actual validation lives in
# ``get_authenticated_tenant`` / ``get_authenticated_user``; these
# dependencies only advertise the schemes in OpenAPI (auto_error=False so
# they never short-circuit the dedicated auth dependencies).
tenant_api_key_header = APIKeyHeader(
    name="X-AuthX-API-Key",
    scheme_name="TenantAPIKey",
    description="Tenant API Key (e.g. ax_test_tenant_a_mock_key).",
    auto_error=False,
)
tenant_bearer = tenant_api_key_header

user_bearer = HTTPBearer(
    scheme_name="UserAccessToken",
    description="Bearer User Access Token (from POST /api/v1/auth/users/login).",
    auto_error=False,
)


async def get_tenant_context(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    x_authx_api_key: Annotated[str | None, Header(alias="X-AuthX-API-Key")] = None,
) -> TenantContext:
    """Resolve the current tenant for a request via Host + X-AuthX-API-Key."""
    return await get_authenticated_tenant(
        db=db, request=request, x_authx_api_key=x_authx_api_key
    )


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_authenticated_tenant(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    request: Request,
    x_authx_api_key: Annotated[str | None, Header(alias="X-AuthX-API-Key")] = None,
) -> TenantContext:
    """Authenticate a tenant using both the ``Host`` header and ``X-AuthX-API-Key``.

    Resolution pipeline:
    1. Extract the tenant slug from ``Host: auth.<slug>.example.com``.
    2. Look up the tenant in the database (→ host ``TenantContext``).
    3. Resolve the tenant for the supplied API key (→ key ``TenantContext``).
    4. Assert both tenant IDs match.

    Both steps must succeed and agree on the same tenant.  Neither can
    override the other.  The trusted tenant identity flows from this
    dependency as a single ``TenantContext``; routes must never re-derive
    the tenant from request body, query params, or arbitrary headers.
    """
    if not x_authx_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    host = request.headers.get("host")

    # --- Step 1 & 2: resolve tenant from Host header ---
    try:
        host_context = await _host_resolver.resolve(db, host)
    except MissingTenantError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    except TenantNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # --- Step 3: resolve tenant from API key ---
    try:
        key_context = await _api_key_resolver.resolve(db, x_authx_api_key)
    except MissingApiKeyError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    except (InvalidApiKeyError, TenantNotFoundError, TenantResolutionError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # --- Step 4: both sources must agree on the same tenant ---
    if host_context.tenant_id != key_context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return host_context


async def get_authenticated_user(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> UserContext:
    """Authenticate a User Access Token and return its ``UserContext``.

    The trusted user and tenant identity comes ONLY from the token
    (``user_id``/``tenant_id`` claims); ``X-Tenant-Id`` is never consulted.
    The token signature, expiration, and ``principal_type == "user"`` are
    validated, and the user must still exist and belong to the claimed
    tenant in the database.
    """
    token = _bearer_token(authorization)
    settings = get_settings()
    try:
        claims = decode_user_access_token(
            token,
            secret=settings.user_access_token_secret,
            algorithm=settings.user_access_token_algorithm,
        )
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (InvalidTokenError, InvalidPrincipalTypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await UserRepository(db).get_by_id(claims.tenant_id, claims.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserContext.from_user(user)
