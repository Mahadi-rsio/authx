from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession


class TenantScopedRepository:
    """Base class for repositories whose rows are tenant-owned.

    Every query that touches tenant-owned data MUST be built through
    ``_scoped_select`` / ``_scoped_get`` so that ``tenant_id`` is always
    enforced. There is deliberately no unscoped "get by primary key".
    """

    model: type[Any]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped_select(self, tenant_id: UUID) -> Select[tuple[Any]]:
        return select(self.model).where(self.model.tenant_id == tenant_id)

    def _scoped_get(self, tenant_id: UUID, pk: UUID) -> Select[tuple[Any]]:
        return select(self.model).where(self.model.tenant_id == tenant_id, self.model.id == pk)
