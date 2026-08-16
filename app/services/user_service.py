from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.tenants.context import TenantContext


class UserService:
    """Tenant-scoped user operations.

    Every method requires a resolved ``TenantContext``; the raw ``tenant_id``
    is never taken from untrusted request input.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = UserRepository(session)

    async def get_user_by_email(self, context: TenantContext, email: str) -> User | None:
        return await self._repository.get_by_email(context.tenant_id, email)

    async def get_user(self, context: TenantContext, user_id) -> User | None:
        return await self._repository.get_by_id(context.tenant_id, user_id)

    async def create_user(
        self,
        context: TenantContext,
        *,
        email: str,
        name: str,
        avatar_url: str | None = None,
        email_verified: bool = False,
    ) -> User:
        user = await self._repository.create(
            tenant_id=context.tenant_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            email_verified=email_verified,
        )
        await self._session.commit()
        return user
