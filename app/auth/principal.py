"""Authenticated tenant principals."""

from dataclasses import dataclass
from uuid import UUID

from app.models.tenant import Tenant


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    """An authenticated tenant principal.

    Returned by the tenant authentication service after a successful
    email/password login and used to mint a Tenant API Token.
    """

    tenant_id: UUID
    email: str
    name: str | None = None
    slug: str | None = None

    @classmethod
    def from_tenant(cls, tenant: Tenant, email: str) -> "TenantPrincipal":
        return cls(tenant_id=tenant.id, email=email, name=tenant.name, slug=tenant.slug)
