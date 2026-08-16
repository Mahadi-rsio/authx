import uuid
from unittest.mock import AsyncMock

import pytest
from app.core.config import DevTenantCredential, Settings
from app.models.tenant import Tenant
from app.tenants.context import TenantContext
from app.tenants.resolver import (
    HeaderTenantResolver,
    InvalidApiKeyError,
    MissingApiKeyError,
    MissingTenantError,
    MockApiKeyTenantResolver,
    TenantNotFoundError,
)


class FakeTenantRepository:
    def __init__(self, tenant: Tenant | None) -> None:
        self.get_by_id = AsyncMock(return_value=tenant)
        self.get_by_slug = AsyncMock(return_value=tenant)


def _tenant() -> Tenant:
    return Tenant(id=uuid.uuid4(), name="Acme", slug="acme")


def _resolver(tenant: Tenant | None) -> HeaderTenantResolver:
    return HeaderTenantResolver(tenant_repository=FakeTenantRepository(tenant))


def _mock_settings(is_development: bool = True) -> Settings:
    return Settings(
        app_env="development" if is_development else "production",
        dev_tenant_credentials=[
            DevTenantCredential(
                email="tenant-a@example.com",
                password="TenantA123!",
                name="Tenant A",
                slug="tenant-a",
                api_key="ax_test_tenant_a_mock_key",
            ),
        ],
        _env_file=None,
    )


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


class TestMockApiKeyTenantResolver:
    async def test_resolve_valid_mock_api_key(self) -> None:
        tenant = Tenant(id=uuid.uuid4(), name="Tenant A", slug="tenant-a")
        resolver = MockApiKeyTenantResolver(
            tenant_repository=FakeTenantRepository(tenant),
            settings=_mock_settings(is_development=True),
        )
        context = await resolver.resolve(session=None, api_key="ax_test_tenant_a_mock_key")
        assert context.tenant_id == tenant.id
        assert context.slug == "tenant-a"

    async def test_resolve_missing_api_key_raises(self) -> None:
        resolver = MockApiKeyTenantResolver(settings=_mock_settings(is_development=True))
        with pytest.raises(MissingApiKeyError):
            await resolver.resolve(session=None, api_key=None)
        with pytest.raises(MissingApiKeyError):
            await resolver.resolve(session=None, api_key="")

    async def test_resolve_invalid_api_key_raises(self) -> None:
        resolver = MockApiKeyTenantResolver(settings=_mock_settings(is_development=True))
        with pytest.raises(InvalidApiKeyError):
            await resolver.resolve(session=None, api_key="invalid_api_key_xxx")

    async def test_mock_api_key_disabled_in_production(self) -> None:
        tenant = Tenant(id=uuid.uuid4(), name="Tenant A", slug="tenant-a")
        resolver = MockApiKeyTenantResolver(
            tenant_repository=FakeTenantRepository(tenant),
            settings=_mock_settings(is_development=False),
        )
        with pytest.raises(InvalidApiKeyError):
            await resolver.resolve(session=None, api_key="ax_test_tenant_a_mock_key")

    async def test_resolve_tenant_not_in_db_raises(self) -> None:
        resolver = MockApiKeyTenantResolver(
            tenant_repository=FakeTenantRepository(None),
            settings=_mock_settings(is_development=True),
        )
        with pytest.raises(TenantNotFoundError):
            await resolver.resolve(session=None, api_key="ax_test_tenant_a_mock_key")
