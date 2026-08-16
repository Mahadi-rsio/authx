import uuid

from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mixins import Model, TenantOwnedMixin, UuidPkMixin


class Identity(UuidPkMixin, TenantOwnedMixin, Model):
    """Links a user to a provider-specific identity within one tenant.

    ``(tenant_id, provider, provider_user_id)`` is unique per tenant.

    ``tenant_id``/``user_id`` are constrained by a composite foreign key to
    ``users(tenant_id, id)``, so a row can never reference a user that does
    not belong to the same tenant (prevents cross-tenant relationships at
    the database level).
    """

    __tablename__ = "identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_identities_tenant_user_users",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "provider_user_id",
            name="uq_identities_tenant_provider_provider_user_id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(512), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
