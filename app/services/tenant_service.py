from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.repositories.tenant import TenantRepository


class TenantService:
    """Operations for tenant management and lookup."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = TenantRepository(session)

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        return await self._repository.get_by_id(tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return await self._repository.get_by_slug(slug.strip().lower())

    async def create_tenant(self, *, name: str, slug: str) -> Tenant:
        tenant = await self._repository.create(name=name.strip(), slug=slug.strip().lower())
        await self._session.commit()
        return tenant
