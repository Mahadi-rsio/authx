from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


class TenantRepository:
    """Repository for tenants (the root of the tenancy hierarchy).

    Tenants are NOT tenant-owned, so this repository is not tenant-scoped.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return await self._session.get(Tenant, tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self._session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, *, name: str, slug: str) -> Tenant:
        tenant = Tenant(name=name, slug=slug)
        self._session.add(tenant)
        await self._session.flush()
        return tenant
