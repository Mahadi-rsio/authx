from uuid import UUID

from sqlalchemy import func

from app.models.user import User
from app.repositories.base import TenantScopedRepository


class UserRepository(TenantScopedRepository):
    """Tenant-scoped repository for users.

    Emails are stored lower-cased and all lookups are case-insensitive.
    """

    model = User

    async def get_by_id(self, tenant_id: UUID, user_id: UUID) -> User | None:
        result = await self._session.execute(self._scoped_get(tenant_id, user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, tenant_id: UUID, email: str) -> User | None:
        stmt = self._scoped_select(tenant_id).where(func.lower(User.email) == email.strip().lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: UUID,
        email: str,
        name: str,
        avatar_url: str | None = None,
        email_verified: bool = False,
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            email=email.strip().lower(),
            name=name.strip(),
            avatar_url=avatar_url,
            email_verified=email_verified,
        )
        self._session.add(user)
        await self._session.flush()
        return user
