from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
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
    TenantNotFoundError,
    TenantResolutionError,
)

_api_key_resolver = ApiKeyTenantResolver()

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
    x_authx_api_key: Annotated[str | None, Header(alias="X-AuthX-API-Key")] = None,
) -> TenantContext:
    """Resolve the current tenant for a request via X-AuthX-API-Key."""
    return await get_authenticated_tenant(db=db, x_authx_api_key=x_authx_api_key)


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
    x_authx_api_key: Annotated[str | None, Header(alias="X-AuthX-API-Key")] = None,
) -> TenantContext:
    """Authenticate a Tenant API Key and return its ``TenantContext``.

    The trusted tenant identity comes ONLY from the resolved API key;
    client-supplied parameters or tenant_ids from body/query/arbitrary headers
    are never trusted.
    """
    if not x_authx_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    try:
        return await _api_key_resolver.resolve(db, x_authx_api_key)
    except MissingApiKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        ) from exc
    except (InvalidApiKeyError, TenantNotFoundError, TenantResolutionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        ) from exc


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
