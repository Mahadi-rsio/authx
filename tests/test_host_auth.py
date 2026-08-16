"""Tests for the host-based tenant authentication architecture.

Covers all 15 required test cases from the specification:

  Test 1:  Valid Tenant A host + Tenant A API key → success.
  Test 2:  Valid Tenant B host + Tenant B API key → success.
  Test 3:  Tenant A host + Tenant B API key → 401.
  Test 4:  Tenant B host + Tenant A API key → 401.
  Test 5:  Missing API key → 401.
  Test 6:  Invalid API key → 401.
  Test 7:  Unknown tenant hostname → 404.
  Test 8:  Tenant A user registration creates user under Tenant A.
  Test 9:  Tenant B user registration creates user under Tenant B.
  Test 10: Same email can exist in both tenants.
  Test 11: tenant_id supplied by client cannot override authenticated tenant.
  Test 12: Tenant A cannot access Tenant B resources.
  Test 13: User login under Tenant A cannot authenticate a Tenant B user.
  Test 14: User access token remains scoped to the tenant.
  Test 15: No tenant JWT is generated as part of API-key authentication.
"""

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
from app.tenants.resolver import TenantHostResolver, TenantMismatchError, TenantNotFoundError
from starlette.requests import Request

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/users/register"
LOGIN_URL = "/api/v1/auth/users/login"
ME_URL = "/api/v1/auth/users/me"

TENANT_A_KEY = "ax_test_tenant_a_mock_key"
TENANT_B_KEY = "ax_test_tenant_b_mock_key"
TENANT_A_HOST = "auth.tenant-a.example.com"
TENANT_B_HOST = "auth.tenant-b.example.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _client(test_app, host: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=test_app),
        base_url=f"http://{host}",
        headers={"Host": host},
    )


@pytest.fixture()
async def client_a(test_app):
    async with _client(test_app, TENANT_A_HOST) as c:
        yield c


@pytest.fixture()
async def client_b(test_app):
    async with _client(test_app, TENANT_B_HOST) as c:
        yield c


async def _tenants(session) -> tuple[TenantContext, TenantContext]:
    svc = TenantService(session)
    ta = await svc.get_by_slug("tenant-a")
    tb = await svc.get_by_slug("tenant-b")
    assert ta and tb
    return TenantContext.from_tenant(ta), TenantContext.from_tenant(tb)


def _make_request(host: str) -> Request:
    """Return a minimal Starlette Request carrying the given Host header."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": [(b"host", host.encode())],
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Unit tests — TenantHostResolver slug extraction (no DB required)
# ---------------------------------------------------------------------------


class TestTenantHostResolverSlugExtraction:
    """Slug extraction from Host headers (pure logic, no database)."""

    def _resolver(self) -> TenantHostResolver:
        return TenantHostResolver()

    def test_extracts_slug_from_tenant_a_host(self) -> None:
        resolver = self._resolver()
        assert resolver.extract_slug("auth.tenant-a.example.com") == "tenant-a"

    def test_extracts_slug_from_tenant_b_host(self) -> None:
        resolver = self._resolver()
        assert resolver.extract_slug("auth.tenant-b.example.com") == "tenant-b"

    def test_strips_port_from_host(self) -> None:
        resolver = self._resolver()
        assert resolver.extract_slug("auth.tenant-a.example.com:8000") == "tenant-a"

    def test_missing_host_raises_missing_tenant_error(self) -> None:
        from app.tenants.resolver import MissingTenantError

        resolver = self._resolver()
        with pytest.raises(MissingTenantError):
            resolver.extract_slug(None)
        with pytest.raises(MissingTenantError):
            resolver.extract_slug("")

    def test_wrong_prefix_raises_tenant_not_found(self) -> None:
        resolver = self._resolver()
        with pytest.raises(TenantNotFoundError):
            resolver.extract_slug("api.tenant-a.example.com")

    def test_missing_slug_segment_raises_tenant_not_found(self) -> None:
        # "auth.example.com" has prefix "auth." but then the suffix ".example.com"
        # immediately follows, leaving an empty slug.
        resolver = self._resolver()
        with pytest.raises(TenantNotFoundError):
            resolver.extract_slug("auth.example.com")

    def test_generic_host_without_slug_is_rejected(self) -> None:
        resolver = self._resolver()
        with pytest.raises(TenantNotFoundError):
            resolver.extract_slug("example.com")

    def test_localhost_without_prefix_is_rejected(self) -> None:
        resolver = self._resolver()
        with pytest.raises(TenantNotFoundError):
            resolver.extract_slug("localhost")

    def test_host_is_normalised_to_lowercase(self) -> None:
        resolver = self._resolver()
        assert resolver.extract_slug("AUTH.Tenant-A.Example.COM") == "tenant-a"


# ---------------------------------------------------------------------------
# Integration tests — HTTP layer
# ---------------------------------------------------------------------------


class TestHostApiKeyValidation:
    """Core host + API key dual-validation rules."""

    # Test 1
    async def test_tenant_a_host_and_tenant_a_key_succeeds(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 201
        assert UUID(response.json()["tenant_id"]) == ctx_a.tenant_id

    # Test 2
    async def test_tenant_b_host_and_tenant_b_key_succeeds(
        self, client_b, seeded_session
    ) -> None:
        _, ctx_b = await _tenants(seeded_session)
        response = await client_b.post(
            REGISTER_URL,
            json={"email": "bob@example.com", "name": "Bob", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 201
        assert UUID(response.json()["tenant_id"]) == ctx_b.tenant_id

    # Test 3
    async def test_tenant_a_host_with_tenant_b_key_rejected(self, client_a) -> None:
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 401
        # Must not leak which tenant the key belongs to
        assert response.json()["detail"] == "Invalid API key"

    # Test 4
    async def test_tenant_b_host_with_tenant_a_key_rejected(self, client_b) -> None:
        response = await client_b.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"

    # Test 5
    async def test_missing_api_key_returns_401(self, client_a) -> None:
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing API key"

    # Test 6
    async def test_invalid_api_key_returns_401(self, client_a) -> None:
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": "ax_totally_invalid_key"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"

    # Test 7
    async def test_unknown_tenant_hostname_returns_404(self, test_app) -> None:
        async with _client(test_app, "auth.unknown-tenant.example.com") as c:
            response = await c.post(
                REGISTER_URL,
                json={
                    "email": "alice@example.com",
                    "name": "Alice",
                    "password": "AlicePassword123!",
                },
                headers={"X-AuthX-API-Key": TENANT_A_KEY},
            )
        assert response.status_code == 404

    async def test_non_matching_hostname_pattern_returns_404(self, test_app) -> None:
        """A host that doesn't match auth.<slug>.example.com returns 404."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=test_app),
            base_url="http://example.com",
            headers={"Host": "example.com"},
        ) as c:
            response = await c.post(
                REGISTER_URL,
                json={
                    "email": "alice@example.com",
                    "name": "Alice",
                    "password": "AlicePassword123!",
                },
                headers={"X-AuthX-API-Key": TENANT_A_KEY},
            )
        assert response.status_code == 404


class TestUserRegistrationTenantScoping:
    """User creation is always scoped to the authenticated tenant."""

    # Test 8
    async def test_registration_creates_user_under_tenant_a(
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
        assert UUID(body["tenant_id"]) == ctx_a.tenant_id

        svc = UserService(seeded_session)
        assert await svc.get_user_by_email(ctx_a, "alice@example.com") is not None
        assert await svc.get_user_by_email(ctx_b, "alice@example.com") is None

    # Test 9
    async def test_registration_creates_user_under_tenant_b(
        self, client_b, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        response = await client_b.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice B", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 201
        body = response.json()
        assert UUID(body["tenant_id"]) == ctx_b.tenant_id

        svc = UserService(seeded_session)
        assert await svc.get_user_by_email(ctx_a, "alice@example.com") is None
        assert await svc.get_user_by_email(ctx_b, "alice@example.com") is not None

    # Test 10
    async def test_same_email_can_exist_in_both_tenants(
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
        # Different users despite same email
        assert resp_a.json()["id"] != resp_b.json()["id"]
        assert UUID(resp_a.json()["tenant_id"]) == ctx_a.tenant_id
        assert UUID(resp_b.json()["tenant_id"]) == ctx_b.tenant_id

    # Test 11
    async def test_client_supplied_tenant_id_cannot_override_authenticated_tenant(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        # Client sends Tenant B's ID in the body but authenticates as Tenant A
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
        # Must be under Tenant A regardless
        assert UUID(response.json()["tenant_id"]) == ctx_a.tenant_id
        svc = UserService(seeded_session)
        assert await svc.get_user_by_email(ctx_a, "alice@example.com") is not None
        assert await svc.get_user_by_email(ctx_b, "alice@example.com") is None


class TestCrossTenantIsolation:
    """Tenant A cannot access Tenant B resources and vice versa."""

    # Test 12
    async def test_tenant_a_cannot_access_tenant_b_users_via_login(
        self, client_a, client_b, seeded_session
    ) -> None:
        # Register Bob under Tenant B
        await client_b.post(
            REGISTER_URL,
            json={"email": "bob@example.com", "name": "Bob", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        # Tenant A key with Tenant A host cannot log in as Bob (not in Tenant A)
        login = await client_a.post(
            LOGIN_URL,
            json={"email": "bob@example.com", "password": "BobPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert login.status_code == 401

    # Test 13
    async def test_user_login_under_tenant_a_cannot_authenticate_tenant_b_user(
        self, client_a, client_b, seeded_session
    ) -> None:
        # Alice in Tenant B only
        await client_b.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice B", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        # Tenant A login with Alice's correct password must fail (no Alice in A)
        login_a = await client_a.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert login_a.status_code == 401

        # Tenant B login with the same credentials succeeds
        login_b = await client_b.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert login_b.status_code == 200

    # Test 14
    async def test_user_access_token_remains_scoped_to_tenant(
        self, client_a, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        login = await client_a.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        # Decode and verify claims
        settings = get_settings()
        claims = decode_user_access_token(
            token,
            secret=settings.user_access_token_secret,
            algorithm=settings.user_access_token_algorithm,
        )
        assert claims.principal_type == "user"
        assert claims.tenant_id == ctx_a.tenant_id

        # /me endpoint returns data for Tenant A
        me = await client_a.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert UUID(me.json()["tenant_id"]) == ctx_a.tenant_id

    # Test 15
    async def test_no_tenant_jwt_generated_by_api_key_auth(
        self, seeded_session
    ) -> None:
        """API-key authentication must resolve directly to TenantContext; no JWT."""
        request = _make_request(TENANT_A_HOST)
        context = await get_authenticated_tenant(
            db=seeded_session, request=request, x_authx_api_key=TENANT_A_KEY
        )
        # Result is a TenantContext, not a JWT string
        assert isinstance(context, TenantContext)
        assert context.slug == "tenant-a"
        # No token returned; just a plain context object
        assert not hasattr(context, "access_token")
        assert not hasattr(context, "token")


class TestErrorResponseNonLeakage:
    """Authentication errors must not reveal which tenant owns a key."""

    async def test_mismatch_error_message_does_not_reveal_tenant(
        self, client_a
    ) -> None:
        """Mismatch must return generic 401, not 'key belongs to Tenant B'."""
        response = await client_a.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 401
        detail = response.json()["detail"]
        # Must not leak tenant identity
        assert "tenant-b" not in detail.lower()
        assert "tenant b" not in detail.lower()
        assert "mismatch" not in detail.lower()
