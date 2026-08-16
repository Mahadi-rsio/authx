"""Development-only seed/bootstrap for mock tenant credentials.

Creates the two mock tenants (and their hashed credentials) when they do not
exist. This MUST never run against a production environment.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.repositories.tenant import TenantRepository
from app.repositories.tenant_credential import TenantCredentialRepository
from app.services.tenant_auth_service import TenantAuthService


async def seed_dev_tenants(session: AsyncSession, settings: Settings | None = None) -> None:
    """Idempotently create development mock tenants and their credentials.

    Only allowed when ``settings.is_development`` is true, so mock
    credentials can never be seeded into production.
    """
    settings = settings or get_settings()
    if not settings.is_development:
        raise RuntimeError("Refusing to seed development mock tenants outside development")

    tenant_repository = TenantRepository(session)
    credential_repository = TenantCredentialRepository(session)
    auth_service = TenantAuthService(session, settings)

    for dev in settings.dev_tenant_credentials:
        tenant = await tenant_repository.get_by_slug(dev.slug)
        if tenant is None:
            tenant = await tenant_repository.create(name=dev.name, slug=dev.slug)
        if await credential_repository.get_by_email(dev.email) is None:
            await auth_service.create_credential(
                tenant_id=tenant.id, email=dev.email, password=dev.password
            )

    await session.commit()
