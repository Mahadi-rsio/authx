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


class TenantMismatchError(TenantResolutionError):
    """Raised when the hostname tenant and API-key tenant do not match.

    Both sources of tenant identity must agree; this error means neither
    one is allowed to override the other.
    """


class TenantResolver(Protocol):
    """Resolves the current ``TenantContext`` from a request.

    Implementations MUST validate any client-supplied tenant identifier
    against a trusted source before returning a context.
    """

    async def resolve(self, session: AsyncSession, identifier: str | None) -> TenantContext: ...


class TenantHostResolver:
    """Resolves a tenant from the request ``Host`` header.

    Expects hostnames in the form ``auth.<slug><suffix>``, e.g.
    ``auth.tenant-a.example.com``.  The slug is extracted, validated to be
    non-empty, and looked up in the database.  The generic hostname
    (``auth.example.com`` with no slug segment) is explicitly rejected.

    The prefix and suffix are read from ``settings.auth_host_prefix`` and
    ``settings.auth_host_suffix`` so they are configurable without code changes.
    """

    def __init__(
        self,
        tenant_repository: TenantRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._tenant_repository = tenant_repository
        self._settings = settings

    def extract_slug(self, host: str | None) -> str:
        """Extract the tenant slug from a hostname.

        Raises :class:`MissingTenantError` when *host* is absent.
        Raises :class:`TenantNotFoundError` when the pattern does not match
        or the slug segment is empty (e.g. ``auth.example.com``).
        """
        if not host:
            raise MissingTenantError("Host header is required for tenant resolution")

        # Strip optional port so ``auth.tenant-a.example.com:8000`` still works.
        hostname = host.split(":")[0].lower().strip()

        settings = self._settings or get_settings()
        prefix = settings.auth_host_prefix.lower()  # e.g. "auth."
        suffix = settings.auth_host_suffix.lower()  # e.g. ".example.com"

        if not hostname.startswith(prefix):
            raise TenantNotFoundError(
                f"Host '{host}' does not match the expected tenant hostname pattern"
            )

        after_prefix = hostname[len(prefix):]  # e.g. "tenant-a.example.com"

        if not after_prefix.endswith(suffix):
            raise TenantNotFoundError(
                f"Host '{host}' does not match the expected tenant hostname pattern"
            )

        slug = after_prefix[: len(after_prefix) - len(suffix)]  # e.g. "tenant-a"
        if not slug:
            raise TenantNotFoundError(
                f"Host '{host}' is missing the tenant slug segment"
            )

        return slug

    async def resolve(self, session: AsyncSession, host: str | None) -> TenantContext:
        """Resolve a ``TenantContext`` from the request ``Host`` header."""
        slug = self.extract_slug(host)

        repository = self._tenant_repository or TenantRepository(session)
        tenant = await repository.get_by_slug(slug)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{slug}' not found")

        return TenantContext.from_tenant(tenant)


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
