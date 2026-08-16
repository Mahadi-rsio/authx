from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tenant import TenantRepository
from app.tenants.context import TenantContext


class TenantResolutionError(Exception):
    """Base error for tenant resolution failures."""


class MissingTenantError(TenantResolutionError):
    """Raised when no tenant identifier is supplied with a request."""


class TenantNotFoundError(TenantResolutionError):
    """Raised when the supplied tenant cannot be found/validated."""


class TenantResolver(Protocol):
    """Resolves the current ``TenantContext`` from a request.

    Implementations MUST validate any client-supplied tenant identifier
    against a trusted source before returning a context.
    """

    async def resolve(
        self, session: AsyncSession, tenant_id_header: str | None
    ) -> TenantContext: ...


class HeaderTenantResolver:
    """Resolves the tenant from the ``X-Tenant-Id`` header.

    Development bootstrap only: the header value is parsed and validated
    against the database, never trusted blindly. Phase 3 will replace this
    with resolution from the authenticated principal.
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
