import uuid
from unittest.mock import AsyncMock

import pytest
from app.models.tenant import Tenant
from app.tenants.context import TenantContext
from app.tenants.resolver import HeaderTenantResolver, MissingTenantError, TenantNotFoundError


class FakeTenantRepository:
    def __init__(self, tenant: Tenant | None) -> None:
        self.get_by_id = AsyncMock(return_value=tenant)


def _tenant() -> Tenant:
    return Tenant(id=uuid.uuid4(), name="Acme", slug="acme")


def _resolver(tenant: Tenant | None) -> HeaderTenantResolver:
    return HeaderTenantResolver(tenant_repository=FakeTenantRepository(tenant))


async def test_context_from_tenant() -> None:
    tenant = _tenant()
    context = TenantContext.from_tenant(tenant)
    assert context.tenant_id == tenant.id
    assert context.slug == "acme"


async def test_resolve_valid_tenant() -> None:
    tenant = _tenant()
    context = await _resolver(tenant).resolve(session=None, tenant_id_header=str(tenant.id))
    assert isinstance(context, TenantContext)
    assert context.tenant_id == tenant.id


async def test_resolve_missing_header_raises() -> None:
    with pytest.raises(MissingTenantError):
        await _resolver(None).resolve(session=None, tenant_id_header=None)
    with pytest.raises(MissingTenantError):
        await _resolver(None).resolve(session=None, tenant_id_header="")


async def test_resolve_invalid_header_raises() -> None:
    with pytest.raises(TenantNotFoundError):
        await _resolver(None).resolve(session=None, tenant_id_header="not-a-uuid")


async def test_resolve_unknown_tenant_raises() -> None:
    with pytest.raises(TenantNotFoundError):
        await _resolver(None).resolve(session=None, tenant_id_header=str(uuid.uuid4()))
