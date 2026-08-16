from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_credential import TenantCredential


class TenantCredentialRepository:
    """Repository for tenant credentials.

    Credentials are one-to-one with tenants (the root of the hierarchy), so
    this repository is not tenant-scoped: the login lookup is by email, and
    the row's ``tenant_id`` is derived from the authenticated tenant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> TenantCredential | None:
        stmt = select(TenantCredential).where(TenantCredential.email == email.strip().lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tenant_id(self, tenant_id: UUID) -> TenantCredential | None:
        result = await self._session.execute(
            select(TenantCredential).where(TenantCredential.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def create(self, *, tenant_id: UUID, email: str, password_hash: str) -> TenantCredential:
        credential = TenantCredential(
            tenant_id=tenant_id,
            email=email.strip().lower(),
            password_hash=password_hash,
        )
        self._session.add(credential)
        await self._session.flush()
        return credential
