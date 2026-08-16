from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import app.models  # noqa: F401  (registers tables on Base.metadata)
import httpx
import pytest
from app.api.dependencies import get_authenticated_tenant, get_db_session
from app.auth.principal import TenantPrincipal
from app.auth.tokens import create_tenant_api_token, decode_tenant_api_token
from app.core.config import get_settings
from app.main import create_app
from app.models.tenant_credential import TenantCredential
from app.services.dev_seed import seed_dev_tenants
from app.services.tenant_auth_service import TenantAuthService
from app.services.tenant_service import TenantService
from app.tenants.context import TenantContext
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

pytestmark = pytest.mark.integration

LOGIN_URL = "/api/v1/auth/tenant/login"


@pytest.fixture()
async def seeded_session(db_session):
    await seed_dev_tenants(db_session)
    yield db_session


@pytest.fixture()
def test_app(seeded_session):
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: seeded_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
async def client(test_app):
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _tenants(session) -> tuple[TenantContext, TenantContext]:
    service = TenantService(session)
    tenant_a = await service.get_by_slug("tenant-a")
    tenant_b = await service.get_by_slug("tenant-b")
    assert tenant_a is not None
    assert tenant_b is not None
    return TenantContext.from_tenant(tenant_a), TenantContext.from_tenant(tenant_b)


def _settings():
    return get_settings()


async def _tenant_principal(session, tenant_id: UUID) -> TenantPrincipal:
    tenant = await TenantAuthService(session, _settings()).get_tenant(tenant_id)
    assert tenant is not None
    return TenantPrincipal(tenant_id=tenant.id, email=f"{tenant.slug}@example.com")


async def _token_for(session, tenant_id: UUID) -> str:
    principal = await _tenant_principal(session, tenant_id)
    return create_tenant_api_token(
        principal,
        secret=_settings().tenant_api_token_secret,
        algorithm=_settings().tenant_api_token_algorithm,
    )


class TestTenantLogin:
    async def test_tenant_a_login_succeeds(self, client) -> None:
        response = await client.post(
            LOGIN_URL, json={"email": "tenant-a@example.com", "password": "TenantA123!"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

    async def test_tenant_b_login_succeeds(self, client) -> None:
        response = await client.post(
            LOGIN_URL, json={"email": "tenant-b@example.com", "password": "TenantB123!"}
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_login_token_contains_tenant_identity(self, client, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        response = await client.post(
            LOGIN_URL, json={"email": "tenant-a@example.com", "password": "TenantA123!"}
        )
        assert response.status_code == 200
        claims = decode_tenant_api_token(
            response.json()["access_token"],
            secret=_settings().tenant_api_token_secret,
            algorithm=_settings().tenant_api_token_algorithm,
        )
        assert claims.principal_type == "tenant"
        assert claims.tenant_id == ctx_a.tenant_id
        assert claims.expires_at > claims.issued_at
        assert claims.token_id

    async def test_wrong_tenant_password_fails(self, client) -> None:
        response = await client.post(
            LOGIN_URL, json={"email": "tenant-a@example.com", "password": "wrong-password"}
        )
        assert response.status_code == 401
        assert "access_token" not in response.json()

    async def test_unknown_tenant_fails(self, client) -> None:
        response = await client.post(
            LOGIN_URL, json={"email": "nobody@example.com", "password": "whatever"}
        )
        assert response.status_code == 401
        assert "access_token" not in response.json()


class TestGetAuthenticatedTenant:
    async def test_tenant_a_token_produces_tenant_a_context(self, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        token = await _token_for(seeded_session, ctx_a.tenant_id)
        context = await get_authenticated_tenant(db=seeded_session, authorization=f"Bearer {token}")
        assert context.tenant_id == ctx_a.tenant_id
        assert context.slug == "tenant-a"

    async def test_tenant_b_token_produces_tenant_b_context(self, seeded_session) -> None:
        _, ctx_b = await _tenants(seeded_session)
        token = await _token_for(seeded_session, ctx_b.tenant_id)
        context = await get_authenticated_tenant(db=seeded_session, authorization=f"Bearer {token}")
        assert context.tenant_id == ctx_b.tenant_id

    async def test_invalid_token_fails(self, seeded_session) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_tenant(db=seeded_session, authorization="Bearer not-a-jwt")
        assert exc_info.value.status_code == 401

    async def test_malformed_token_fails(self, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        token = await _token_for(seeded_session, ctx_a.tenant_id)
        tampered = token[:-4] + "XXXX"
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_tenant(db=seeded_session, authorization=f"Bearer {tampered}")
        assert exc_info.value.status_code == 401

    async def test_expired_token_fails(self, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        principal = await _tenant_principal(seeded_session, ctx_a.tenant_id)
        expired = create_tenant_api_token(
            principal,
            secret=_settings().tenant_api_token_secret,
            algorithm=_settings().tenant_api_token_algorithm,
            issued_at=datetime.now(UTC) - timedelta(hours=2),
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_tenant(db=seeded_session, authorization=f"Bearer {expired}")
        assert exc_info.value.status_code == 401

    async def test_missing_authorization_fails(self, seeded_session) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_tenant(db=seeded_session, authorization=None)
        assert exc_info.value.status_code == 401


class TestTenantIsolation:
    async def test_x_tenant_id_cannot_switch_authenticated_tenant(
        self, client, test_app, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        token = await _token_for(seeded_session, ctx_a.tenant_id)

        @test_app.get("/test/whoami")
        async def whoami(
            tenant: Annotated[TenantContext, Depends(get_authenticated_tenant)],
            x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        ):
            return {
                "tenant_id": str(tenant.tenant_id),
                "slug": tenant.slug,
                "x_tenant_id": x_tenant_id,
            }

        response = await client.get(
            "/test/whoami",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(ctx_b.tenant_id),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == str(ctx_a.tenant_id)
        assert body["slug"] == "tenant-a"
        assert body["x_tenant_id"] == str(ctx_b.tenant_id)


class TestCredentialStorage:
    async def test_plaintext_password_never_stored(self, seeded_session) -> None:
        rows = (await seeded_session.execute(select(TenantCredential))).scalars().all()
        assert len(rows) == 2
        for row in rows:
            assert row.password_hash.startswith("$argon2id$")
            assert "TenantA123!" not in row.password_hash
            assert "TenantB123!" not in row.password_hash
