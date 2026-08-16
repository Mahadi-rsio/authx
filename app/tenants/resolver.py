from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.repositories.tenant import TenantRepository
from app.tenants.context import TenantContext


class TenantResolutionError(Exception):
    """Base error for tenant resolution failures."""


class MissingTenantError(TenantResolutionError):
    """Raised when no tenant identifier is supplied with a request."""


class TenantNotFoundError(TenantResolutionError):
    """Raised when the supplied tenant cannot be found/validated."""


class MissingApiKeyError(TenantResolutionError):
    """Raised when no API key is supplied with a request."""


class InvalidApiKeyError(TenantResolutionError):
    """Raised when the supplied API key is invalid or unknown."""


class TenantResolver(Protocol):
    """Resolves the current ``TenantContext`` from a request.

    Implementations MUST validate any client-supplied tenant identifier
    against a trusted source before returning a context.
    """

    async def resolve(self, session: AsyncSession, identifier: str | None) -> TenantContext: ...


class MockApiKeyTenantResolver:
    """Resolves a tenant from a development-only mock API key.

    In development, matches the provided ``X-AuthX-API-Key`` against
    ``settings.dev_tenant_credentials`` and loads the corresponding
    tenant from the database to produce a validated ``TenantContext``.

    In non-development environments (e.g. production), mock API keys are
    disabled and will always raise ``InvalidApiKeyError``.
    """

    def __init__(
        self,
        tenant_repository: TenantRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._tenant_repository = tenant_repository
        self._settings = settings

    async def resolve(self, session: AsyncSession, api_key: str | None) -> TenantContext:
        if not api_key:
            raise MissingApiKeyError("X-AuthX-API-Key header is required")

        settings = self._settings or get_settings()
        if not settings.is_development:
            raise InvalidApiKeyError("Mock API keys are disabled outside development")

        matched = next(
            (cred for cred in settings.dev_tenant_credentials if cred.api_key == api_key),
            None,
        )
        if matched is None:
            raise InvalidApiKeyError("Invalid API key")

        repository = self._tenant_repository or TenantRepository(session)
        tenant = await repository.get_by_slug(matched.slug)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant for mock key '{matched.slug}' not found")

        return TenantContext.from_tenant(tenant)


ApiKeyTenantResolver = MockApiKeyTenantResolver


class HeaderTenantResolver:
    """Resolves the tenant from the ``X-Tenant-Id`` header.

    Development bootstrap only: the header value is parsed and validated
    against the database, never trusted blindly.
    """

    def __init__(self, tenant_repository: TenantRepository | None = None) -> None:
        self._tenant_repository = tenant_repository

    async def resolve(self, session: AsyncSession, tenant_id_header: str | None) -> TenantContext:
        if not tenant_id_header:
            raise MissingTenantError("X-Tenant-Id header is required")
        try:
            tenant_id = UUID(tenant_id_header)
        except ValueError as exc:
            raise TenantNotFoundError("Supplied tenant identifier is not a valid UUID") from exc

        repository = self._tenant_repository or TenantRepository(session)
        tenant = await repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError("Tenant not found")
        return TenantContext.from_tenant(tenant)
