from datetime import UTC, datetime
from uuid import UUID

from app.models.password_credential import PasswordCredential
from app.repositories.base import TenantScopedRepository


class PasswordCredentialRepository(TenantScopedRepository):
    """Tenant-scoped repository for user password credentials."""

    model = PasswordCredential

    async def get_by_user_id(self, tenant_id: UUID, user_id: UUID) -> PasswordCredential | None:
        stmt = self._scoped_select(tenant_id).where(PasswordCredential.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, *, tenant_id: UUID, user_id: UUID, password_hash: str
    ) -> PasswordCredential:
        credential = PasswordCredential(
            tenant_id=tenant_id,
            user_id=user_id,
            password_hash=password_hash,
            password_changed_at=datetime.now(UTC),
        )
        self._session.add(credential)
        await self._session.flush()
        return credential
