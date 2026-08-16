import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mixins import Model, TenantOwnedMixin, UuidPkMixin


class PasswordCredential(UuidPkMixin, TenantOwnedMixin, Model):
    """A real, database-backed password credential for a user.

    Exactly one row per ``(tenant_id, user_id)``. Only the Argon2id
    ``password_hash`` is stored — plaintext passwords never touch the
    database. ``tenant_id``/``user_id`` are constrained by a composite
    foreign key to ``users(tenant_id, id)``, so a credential can never
    reference a user that does not belong to the same tenant.
    """

    __tablename__ = "password_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_password_credentials_tenant_user_users",
        ),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_password_credentials_tenant_id_user_id",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
