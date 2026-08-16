from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.principal import UserPrincipal
from app.auth.tokens import create_user_access_token
from app.core.config import Settings, get_settings
from app.models.user import User
from app.repositories.password_credential import PasswordCredentialRepository
from app.repositories.user import UserRepository
from app.tenants.context import TenantContext


class UserAuthError(Exception):
    """Base error for user authentication operations."""


class DuplicateEmailError(UserAuthError):
    """Raised when registering an email that already exists in the tenant."""


class UserAuthService:
    """Real user email/password authentication.

    Registration requires an authenticated :class:`TenantContext`; the raw
    ``tenant_id`` is never taken from request input. Passwords are hashed
    with Argon2id and only the hash is persisted. Login is tenant-scoped: the
    email is looked up ONLY inside the authenticated tenant, and a successful
    login issues a User Access Token.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._user_repository = UserRepository(session)
        self._credential_repository = PasswordCredentialRepository(session)

    async def register_user(
        self,
        context: TenantContext,
        *,
        email: str,
        name: str,
        password: str,
    ) -> User:
        """Create a user and its password credential within one tenant.

        Emails are unique per tenant; a duplicate email inside the same
        tenant raises :class:`DuplicateEmailError`.
        """
        existing = await self._user_repository.get_by_email(context.tenant_id, email)
        if existing is not None:
            raise DuplicateEmailError("A user with this email already exists in this tenant")

        user = await self._user_repository.create(
            tenant_id=context.tenant_id,
            email=email,
            name=name,
            email_verified=False,
        )
        await self._credential_repository.create(
            tenant_id=context.tenant_id,
            user_id=user.id,
            password_hash=hash_password(password),
        )
        await self._session.commit()
        return user

    async def authenticate_user(
        self, context: TenantContext, *, email: str, password: str
    ) -> UserPrincipal | None:
        """Authenticate a user by email + password within a tenant.

        Returns an authenticated :class:`UserPrincipal` on success or
        ``None`` when the user is unknown or the password is wrong (callers
        treat both identically to avoid user enumeration).
        """
        user = await self._user_repository.get_by_email(context.tenant_id, email)
        if user is None:
            return None
        credential = await self._credential_repository.get_by_user_id(context.tenant_id, user.id)
        if credential is None:
            return None
        if not verify_password(password, credential.password_hash):
            return None
        return UserPrincipal.from_user(user)

    def issue_user_token(self, principal: UserPrincipal) -> str:
        """Mint a User Access Token for an authenticated user principal."""
        settings = self._settings
        return create_user_access_token(
            principal,
            secret=settings.user_access_token_secret,
            algorithm=settings.user_access_token_algorithm,
            expires_in=timedelta(minutes=settings.user_access_token_expire_minutes),
        )

    async def get_user(self, tenant_id: UUID, user_id: UUID) -> User | None:
        return await self._user_repository.get_by_id(tenant_id, user_id)
