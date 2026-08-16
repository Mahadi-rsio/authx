from uuid import UUID

from app.models.identity import Identity
from app.repositories.base import TenantScopedRepository


class IdentityRepository(TenantScopedRepository):
    """Tenant-scoped repository for identities."""

    model = Identity

    async def get_by_id(self, tenant_id: UUID, identity_id: UUID) -> Identity | None:
        result = await self._session.execute(self._scoped_get(tenant_id, identity_id))
        return result.scalar_one_or_none()

    async def get_by_provider(
        self, tenant_id: UUID, provider: str, provider_user_id: str
    ) -> Identity | None:
        stmt = self._scoped_select(tenant_id).where(
            Identity.provider == provider,
            Identity.provider_user_id == provider_user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(self, tenant_id: UUID, user_id: UUID) -> list[Identity]:
        stmt = self._scoped_select(tenant_id).where(Identity.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        provider_email: str | None = None,
    ) -> Identity:
        identity = Identity(
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
        )
        self._session.add(identity)
        await self._session.flush()
        return identity
