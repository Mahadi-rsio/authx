from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.principal import TenantPrincipal
from app.auth.tokens import create_tenant_api_token
from app.core.config import Settings, get_settings
from app.models.tenant import Tenant
from app.models.tenant_credential import TenantCredential
from app.repositories.tenant import TenantRepository
from app.repositories.tenant_credential import TenantCredentialRepository


class TenantAuthService:
    """Tenant authentication: credential lookup, password verification,
    and Tenant API Token issuance.

    Plaintext passwords are never exposed or stored; only Argon2id hashes
    are persisted.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._credential_repository = TenantCredentialRepository(session)
        self._tenant_repository = TenantRepository(session)

    async def authenticate(self, email: str, password: str) -> TenantPrincipal | None:
        """Authenticate a tenant by email + password.

        Returns an authenticated :class:`TenantPrincipal` on success or
        ``None`` when the tenant is unknown or the password is wrong
        (callers treat both identically to avoid user enumeration).
        """
        credential = await self._credential_repository.get_by_email(email)
        if credential is None:
            return None
        if not verify_password(password, credential.password_hash):
            return None
        tenant = await self._tenant_repository.get_by_id(credential.tenant_id)
        if tenant is None:
            return None
        return TenantPrincipal.from_tenant(tenant, email=credential.email)

    def issue_api_token(self, principal: TenantPrincipal) -> str:
        """Mint a Tenant API Token for an authenticated tenant principal."""
        settings = self._settings
        return create_tenant_api_token(
            principal,
            secret=settings.tenant_api_token_secret,
            algorithm=settings.tenant_api_token_algorithm,
            expires_in=timedelta(minutes=settings.tenant_api_token_expire_minutes),
        )

    async def create_credential(
        self, *, tenant_id: UUID, email: str, password: str
    ) -> TenantCredential:
        """Store a hashed credential for a tenant (used by seed logic)."""
        return await self._credential_repository.create(
            tenant_id=tenant_id,
            email=email,
            password_hash=hash_password(password),
        )

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        return await self._tenant_repository.get_by_id(tenant_id)
