from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import (
    ExpiredTokenError,
    InvalidPrincipalTypeError,
    InvalidTokenError,
    decode_tenant_api_token,
)
from app.core.config import get_settings
from app.database.session import get_db_session
from app.repositories.tenant import TenantRepository
from app.tenants.context import TenantContext
from app.tenants.resolver import HeaderTenantResolver

_tenant_resolver = HeaderTenantResolver()


async def get_tenant_context(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
) -> TenantContext:
    """Resolve the current tenant for a request.

    Development bootstrap: reads ``X-Tenant-Id`` and validates it against
    the database. Phase 3 replaces this with resolution from the
    authenticated principal so client-supplied tenant ids are never trusted.
    """
    return await _tenant_resolver.resolve(db, x_tenant_id)


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
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> TenantContext:
    """Authenticate a Tenant API Token and return its ``TenantContext``.

    The trusted tenant identity comes ONLY from the token (``tenant_id``
    claim); ``X-Tenant-Id`` is never consulted here. The token signature and
    expiration are validated, the principal type must be ``tenant``, and the
    tenant must still exist in the database.
    """
    token = _bearer_token(authorization)
    settings = get_settings()
    try:
        claims = decode_tenant_api_token(
            token,
            secret=settings.tenant_api_token_secret,
            algorithm=settings.tenant_api_token_algorithm,
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

    tenant = await TenantRepository(db).get_by_id(claims.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TenantContext.from_tenant(tenant)
