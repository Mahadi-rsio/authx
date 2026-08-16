from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Identity
from app.repositories.identity import IdentityRepository
from app.tenants.context import TenantContext


class IdentityService:
    """Tenant-scoped identity operations.

    Every method requires a resolved ``TenantContext`` so identities can
    never be read or written outside their tenant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = IdentityRepository(session)

    async def get_identity(
        self, context: TenantContext, provider: str, provider_user_id: str
    ) -> Identity | None:
        return await self._repository.get_by_provider(context.tenant_id, provider, provider_user_id)

    async def get_identity_by_id(
        self, context: TenantContext, identity_id: UUID
    ) -> Identity | None:
        return await self._repository.get_by_id(context.tenant_id, identity_id)

    async def create_identity(
        self,
        context: TenantContext,
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        provider_email: str | None = None,
    ) -> Identity:
        identity = await self._repository.create(
            tenant_id=context.tenant_id,
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
        )
        await self._session.commit()
        return identity
