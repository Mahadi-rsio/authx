from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.mixins import Model, UuidPkMixin


class Tenant(UuidPkMixin, Model):
    """Root entity of the multi-tenant hierarchy.

    Tenants are NOT tenant-owned; they are the anchor every other entity
    scopes against via ``tenant_id``.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
