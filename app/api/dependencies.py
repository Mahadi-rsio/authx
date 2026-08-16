from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
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
