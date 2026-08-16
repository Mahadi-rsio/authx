from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mixins import Model, TenantOwnedMixin, UuidPkMixin


class User(UuidPkMixin, TenantOwnedMixin, Model):
    """A user belonging to exactly one tenant.

    ``(tenant_id, email)`` is unique: emails are tenant-scoped, never
    globally unique.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        # Backs the composite FK on ``identities`` and accelerates
        # tenant-scoped user lookups.
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
