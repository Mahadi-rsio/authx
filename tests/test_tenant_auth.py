from typing import Annotated
from uuid import UUID

import app.models  # noqa: F401  (registers tables on Base.metadata)
import httpx
import pytest
from app.api.dependencies import get_authenticated_tenant, get_db_session
from app.auth.tokens import decode_user_access_token
from app.core.config import get_settings
from app.main import create_app
from app.services.dev_seed import seed_dev_tenants
from app.services.tenant_service import TenantService
from app.services.user_service import UserService
from app.tenants.context import TenantContext
from fastapi import Depends, HTTPException, Request
from starlette.testclient import TestClient

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/users/register"
LOGIN_URL = "/api/v1/auth/users/login"
ME_URL = "/api/v1/auth/users/me"

TENANT_A_KEY = "ax_test_tenant_a_mock_key"
TENANT_B_KEY = "ax_test_tenant_b_mock_key"
TENANT_A_HOST = "auth.tenant-a.example.com"
TENANT_B_HOST = "auth.tenant-b.example.com"


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
async def client_a(test_app):
    """HTTP client pre-configured with Tenant A's host."""
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{TENANT_A_HOST}",
        headers={"Host": TENANT_A_HOST},
    ) as c:
        yield c


@pytest.fixture()
async def client_b(test_app):
    """HTTP client pre-configured with Tenant B's host."""
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{TENANT_B_HOST}",
        headers={"Host": TENANT_B_HOST},
    ) as c:
        yield c


@pytest.fixture()
async def client(test_app):
    """Generic client (no default host); used for cross-tenant tests."""
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


def _make_request(host: str) -> Request:
    """Build a minimal Starlette Request with the given Host header."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [(b"host", host.encode())],
    }
    return Request(scope)


class TestMockApiKeyTenantAuth:
    """1. Tenant A mock API key authenticates Tenant A."""

    async def test_tenant_a_mock_api_key_authenticates_tenant_a(
        self, client_a, test_app, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)

        @test_app.get("/test/tenant-auth")
        async def tenant_auth_endpoint(
            tenant: Annotated[TenantContext, Depends(get_authenticated_tenant)],
        ):
            return {"tenant_id": str(tenant.tenant_id), "slug": tenant.slug}

        response = await client_a.get(
            "/test/tenant-auth", headers={"X-AuthX-API-Key": TENANT_A_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == str(ctx_a.tenant_id)
        assert data["slug"] == "tenant-a"

    """2. Tenant B mock API key authenticates Tenant B."""

    async def test_tenant_b_mock_api_key_authenticates_tenant_b(
        self, client_b, test_app, seeded_session
    ) -> None:
        _, ctx_b = await _tenants(seeded_session)

        @test_app.get("/test/tenant-auth-b")
        async def tenant_auth_endpoint(
            tenant: Annotated[TenantContext, Depends(get_authenticated_tenant)],
        ):
            return {"tenant_id": str(tenant.tenant_id), "slug": tenant.slug}

        response = await client_b.get(
            "/test/tenant-auth-b", headers={"X-AuthX-API-Key": TENANT_B_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == str(ctx_b.tenant_id)
        assert data["slug"] == "tenant-b"

    """3. Invalid API key returns 401."""

    async def test_invalid_api_key_returns_401(self, client_a) -> None:
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": "invalid_api_key_12345"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"

    """4. Missing API key returns 401."""

    async def test_missing_api_key_returns_401(self, client_a) -> None:
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"

    """5. Tenant A API key creates users under Tenant A."""

    async def test_tenant_a_api_key_creates_users_under_tenant_a(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["name"] == "Alice"
        assert UUID(body["tenant_id"]) == ctx_a.tenant_id

        # Verify in database
        user_service = UserService(seeded_session)
        user_a = await user_service.get_user_by_email(ctx_a, "alice@example.com")
        user_b = await user_service.get_user_by_email(ctx_b, "alice@example.com")
        assert user_a is not None
        assert user_b is None

    """6. Tenant B API key creates users under Tenant B."""

    async def test_tenant_b_api_key_creates_users_under_tenant_b(
        self, client_b, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        response = await client_b.post(
            REGISTER_URL,
            json={"email": "bob@example.com", "name": "Bob", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "bob@example.com"
        assert body["name"] == "Bob"
        assert UUID(body["tenant_id"]) == ctx_b.tenant_id

        # Verify in database
        user_service = UserService(seeded_session)
        user_a = await user_service.get_user_by_email(ctx_a, "bob@example.com")
        user_b = await user_service.get_user_by_email(ctx_b, "bob@example.com")
        assert user_a is None
        assert user_b is not None

    """7. Same email can exist in Tenant A and Tenant B."""

    async def test_same_email_can_exist_in_tenant_a_and_tenant_b(
        self, client_a, client_b, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        resp_a = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice A", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        resp_b = await client_b.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice B", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201
        assert resp_a.json()["id"] != resp_b.json()["id"]
        assert UUID(resp_a.json()["tenant_id"]) == ctx_a.tenant_id
        assert UUID(resp_b.json()["tenant_id"]) == ctx_b.tenant_id

    """8. Tenant A API key cannot access Tenant B users."""

    async def test_tenant_a_api_key_cannot_access_tenant_b_users(
        self, client_a, client_b, seeded_session
    ) -> None:
        # Register user under Tenant B only
        resp_b = await client_b.post(
            REGISTER_URL,
            json={"email": "bob@example.com", "name": "Bob B", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert resp_b.status_code == 201

        # Attempt to login under Tenant A with Tenant B user credentials
        login_a = await client_a.post(
            LOGIN_URL,
            json={"email": "bob@example.com", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert login_a.status_code == 401

        # Login under Tenant B succeeds
        login_b = await client_b.post(
            LOGIN_URL,
            json={"email": "bob@example.com", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert login_b.status_code == 200

    """9. tenant_id in request body cannot override the API-key tenant."""

    async def test_tenant_id_in_request_body_cannot_override_api_key_tenant(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        response = await client_a.post(
            REGISTER_URL,
            json={
                "tenant_id": str(ctx_b.tenant_id),
                "email": "alice@example.com",
                "name": "Alice",
                "password": "AlicePassword123!",
            },
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 201
        assert UUID(response.json()["tenant_id"]) == ctx_a.tenant_id

        user_service = UserService(seeded_session)
        user_a = await user_service.get_user_by_email(ctx_a, "alice@example.com")
        user_b = await user_service.get_user_by_email(ctx_b, "alice@example.com")
        assert user_a is not None
        assert user_b is None

    """10. Tenant API key does not produce a tenant JWT."""

    async def test_tenant_api_key_does_not_produce_tenant_jwt(
        self, test_app, seeded_session
    ) -> None:
        # Tenant authentication resolves directly to TenantContext without
        # issuing or requiring a tenant JWT
        request = _make_request(TENANT_A_HOST)
        context = await get_authenticated_tenant(
            db=seeded_session, request=request, x_authx_api_key=TENANT_A_KEY
        )
        assert isinstance(context, TenantContext)
        assert context.slug == "tenant-a"

    """11. User login still produces the existing user access token."""

    async def test_user_login_produces_user_access_token(
        self, client_a, seeded_session
    ) -> None:
        await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        login_resp = await client_a.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert login_resp.status_code == 200
        body = login_resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

        settings = get_settings()
        claims = decode_user_access_token(
            body["access_token"],
            secret=settings.user_access_token_secret,
            algorithm=settings.user_access_token_algorithm,
        )
        assert claims.principal_type == "user"
        ctx_a, _ = await _tenants(seeded_session)
        assert claims.tenant_id == ctx_a.tenant_id

    """12. User access token remains tenant-scoped."""

    async def test_user_access_token_remains_tenant_scoped(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        login_resp = await client_a.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        user_token = login_resp.json()["access_token"]

        me_resp = await client_a.get(ME_URL, headers={"Authorization": f"Bearer {user_token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["email"] == "alice@example.com"
        assert UUID(me_data["tenant_id"]) == ctx_a.tenant_id

    """13. Mock API keys do not work when running in production configuration."""

    async def test_mock_api_keys_do_not_work_in_production(
        self, seeded_session, monkeypatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        get_settings.cache_clear()
        try:
            request = _make_request(TENANT_A_HOST)
            with pytest.raises(HTTPException) as exc_info:
                await get_authenticated_tenant(
                    db=seeded_session, request=request, x_authx_api_key=TENANT_A_KEY
                )
            assert exc_info.value.status_code == 401
        finally:
            get_settings.cache_clear()
