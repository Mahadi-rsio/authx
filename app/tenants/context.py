from dataclasses import dataclass
from uuid import UUID

from app.models.tenant import Tenant


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The resolved current tenant for a request.

    NEVER constructed from raw client input. Always derived from a trusted
    source (e.g. the authenticated principal in Phase 3) and validated
    against the database before being passed into services.
    """

    tenant_id: UUID
    slug: str | None = None

    @classmethod
    def from_tenant(cls, tenant: Tenant) -> "TenantContext":
        return cls(tenant_id=tenant.id, slug=tenant.slug)
