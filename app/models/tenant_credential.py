from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mixins import Model, TenantOwnedMixin, UuidPkMixin


class TenantCredential(UuidPkMixin, TenantOwnedMixin, Model):
    """Credentials used to authenticate a tenant (development-only).

    One credential row per tenant (``tenant_id`` is unique). Only the
    Argon2id ``password_hash`` is stored — plaintext passwords never touch
    the database. ``email`` is globally unique because tenant login is by
    email alone.
    """

    __tablename__ = "tenant_credentials"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_credentials_tenant_id"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
