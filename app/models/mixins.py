import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UuidPkMixin:
    """Provides a non-sequential UUID primary key.

    ``default`` supplies the value in Python; ``server_default`` uses
    PostgreSQL's ``gen_random_uuid()`` when no value is provided.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` columns maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantOwnedMixin:
    """Enforces tenant isolation.

    Every tenant-owned entity MUST inherit from this mixin so that a
    ``tenant_id`` column with a foreign key to ``tenants.id`` exists.
    All tenant-scoped database operations MUST filter by ``tenant_id``;
    never access tenant data without it.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class Model(TimestampMixin, Base):
    """Base class combining declarative base with audit timestamps."""

    __abstract__ = True
