"""Authenticated tenant and user principals."""

from dataclasses import dataclass
from uuid import UUID

from app.models.tenant import Tenant
from app.models.user import User


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


@dataclass(frozen=True, slots=True)
class UserPrincipal:
    """An authenticated user principal.

    Returned by the user authentication service after a successful
    email/password login within a tenant and used to mint a User Access
    Token. Carries the ``tenant_id`` the user belongs to so tokens are
    always tenant-aware.
    """

    user_id: UUID
    tenant_id: UUID
    email: str
    name: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserPrincipal":
        return cls(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            name=user.name,
        )


@dataclass(frozen=True, slots=True)
class UserContext:
    """An authenticated user context for a request.

    Returned by ``get_authenticated_user``. ``user_id``/``tenant_id`` come
    ONLY from the validated User Access Token and are verified against the
    database, so the user always belongs to the claimed tenant.
    """

    user_id: UUID
    tenant_id: UUID
    email: str
    name: str
    email_verified: bool

    @classmethod
    def from_user(cls, user: User) -> "UserContext":
        return cls(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified,
        )
