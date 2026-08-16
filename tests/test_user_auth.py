from datetime import UTC, datetime, timedelta
from uuid import UUID

import app.models  # noqa: F401  (registers tables on Base.metadata)
import httpx
import pytest
from app.api.dependencies import get_authenticated_user, get_db_session
from app.auth.principal import TenantPrincipal, UserPrincipal
from app.auth.tokens import (
    create_tenant_api_token,
    create_user_access_token,
    decode_user_access_token,
)
from app.core.config import get_settings
from app.main import create_app
from app.models.password_credential import PasswordCredential
from app.services.dev_seed import seed_dev_tenants
from app.services.tenant_service import TenantService
from app.services.user_service import UserService
from app.tenants.context import TenantContext
from fastapi import HTTPException
from sqlalchemy import select

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/users/register"
LOGIN_URL = "/api/v1/auth/users/login"
ME_URL = "/api/v1/auth/users/me"

TENANT_A_KEY = "ax_test_tenant_a_mock_key"
TENANT_B_KEY = "ax_test_tenant_b_mock_key"


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


def _settings():
    return get_settings()


async def _tenants(session) -> tuple[TenantContext, TenantContext]:
    service = TenantService(session)
    tenant_a = await service.get_by_slug("tenant-a")
    tenant_b = await service.get_by_slug("tenant-b")
    assert tenant_a is not None
    assert tenant_b is not None
    return TenantContext.from_tenant(tenant_a), TenantContext.from_tenant(tenant_b)


async def _user_token(session, *, user_id: UUID, tenant_id: UUID, **overrides) -> str:
    principal = UserPrincipal(user_id=user_id, tenant_id=tenant_id, email="alice@example.com")
    return create_user_access_token(
        principal,
        secret=_settings().user_access_token_secret,
        algorithm=_settings().user_access_token_algorithm,
        **overrides,
    )


async def _register(
    client,
    api_key: str = TENANT_A_KEY,
    *,
    email: str,
    name: str,
    password: str,
) -> httpx.Response:
    return await client.post(
        REGISTER_URL,
        json={"email": email, "name": name, "password": password},
        headers={"X-AuthX-API-Key": api_key},
    )


class TestRegister:
    async def test_requires_tenant_api_key(self, client) -> None:
        response = await client.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
        )
        assert response.status_code == 401

    async def test_invalid_tenant_key_rejected(self, client) -> None:
        response = await client.post(
            REGISTER_URL,
            json={"email": "alice@example.com", "name": "Alice", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": "not-a-valid-key"},
        )
        assert response.status_code == 401

    async def test_bearer_token_not_used_for_tenant_registration(
        self, client, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        alice = await UserService(seeded_session).create_user(
            ctx_a, email="alice@example.com", name="Alice"
        )
        user_token = await _user_token(seeded_session, user_id=alice.id, tenant_id=ctx_a.tenant_id)
        response = await client.post(
            REGISTER_URL,
            json={"email": "bob@example.com", "name": "Bob", "password": "BobPassword123!"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 401

    async def test_register_with_tenant_a_key_creates_user_in_a(
        self, client, seeded_session
    ) -> None:
        ctx_a, _ = await _tenants(seeded_session)

        response = await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["name"] == "Alice"
        assert body["email_verified"] is False
        assert UUID(body["tenant_id"]) == ctx_a.tenant_id

        user = await UserService(seeded_session).get_user_by_email(ctx_a, "alice@example.com")
        assert user is not None
        assert user.id == UUID(body["id"])

    async def test_tenant_id_in_body_is_ignored(self, client, seeded_session) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)

        response = await client.post(
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

        user_a = await UserService(seeded_session).get_user_by_email(ctx_a, "alice@example.com")
        user_b = await UserService(seeded_session).get_user_by_email(ctx_b, "alice@example.com")
        assert user_a is not None
        assert user_b is None

    async def test_duplicate_email_same_tenant_rejected(self, client, seeded_session) -> None:
        first = await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        assert first.status_code == 201

        second = await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        assert second.status_code == 409

    async def test_same_email_across_tenants_allowed(self, client, seeded_session) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)

        in_a = await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        in_b = await _register(
            client,
            TENANT_B_KEY,
            email="alice@example.com",
            name="Alice",
            password="DifferentPassword123!",
        )
        assert in_a.status_code == 201
        assert in_b.status_code == 201
        assert in_a.json()["id"] != in_b.json()["id"]

    async def test_email_is_normalized_lowercase(self, client, seeded_session) -> None:
        response = await _register(
            client,
            TENANT_A_KEY,
            email="ALICE@Example.COM",
            name="Alice",
            password="AlicePassword123!",
        )
        assert response.status_code == 201
        assert response.json()["email"] == "alice@example.com"


class TestLogin:
    async def _create_alice(self, client, api_key: str, password: str) -> None:
        response = await _register(
            client, api_key, email="alice@example.com", name="Alice", password=password
        )
        assert response.status_code == 201

    async def test_login_with_correct_password_succeeds(self, client, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        await self._create_alice(client, TENANT_A_KEY, "AlicePassword123!")

        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

        claims = decode_user_access_token(
            body["access_token"],
            secret=_settings().user_access_token_secret,
            algorithm=_settings().user_access_token_algorithm,
        )
        assert claims.principal_type == "user"
        assert claims.tenant_id == ctx_a.tenant_id
        assert claims.expires_at > claims.issued_at
        assert claims.token_id

    async def test_login_with_wrong_password_rejected(self, client, seeded_session) -> None:
        await self._create_alice(client, TENANT_A_KEY, "AlicePassword123!")

        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "wrong-password"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 401
        assert "access_token" not in response.json()

    async def test_login_requires_tenant_api_key(self, client, seeded_session) -> None:
        await self._create_alice(client, TENANT_A_KEY, "AlicePassword123!")

        response = await client.post(
            LOGIN_URL, json={"email": "alice@example.com", "password": "AlicePassword123!"}
        )
        assert response.status_code == 401

    async def test_login_is_scoped_to_authenticated_tenant(self, client, seeded_session) -> None:
        await self._create_alice(client, TENANT_A_KEY, "AlicePassword123!")
        await self._create_alice(client, TENANT_B_KEY, "DifferentPassword123!")

        # Correct credentials only authenticate within the owning tenant.
        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "DifferentPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_A_KEY},
        )
        assert response.status_code == 401

        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 401

        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "DifferentPassword123!"},
            headers={"X-AuthX-API-Key": TENANT_B_KEY},
        )
        assert response.status_code == 200


class TestUsersMe:
    async def _login_token(self, client, api_key: str = TENANT_A_KEY) -> str:
        response = await client.post(
            LOGIN_URL,
            json={"email": "alice@example.com", "password": "AlicePassword123!"},
            headers={"X-AuthX-API-Key": api_key},
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    async def test_users_me_returns_authenticated_user(self, client, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        user_token = await self._login_token(client, TENANT_A_KEY)

        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {user_token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["name"] == "Alice"
        assert body["email_verified"] is False
        assert UUID(body["tenant_id"]) == ctx_a.tenant_id

    async def test_api_key_header_alone_rejected_for_users_me(self, client, seeded_session) -> None:
        response = await client.get(ME_URL, headers={"X-AuthX-API-Key": TENANT_A_KEY})
        assert response.status_code == 401

    async def test_invalid_user_token_rejected(self, client) -> None:
        response = await client.get(ME_URL, headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401

    async def test_expired_user_token_rejected(self, client, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        user = await UserService(seeded_session).get_user_by_email(ctx_a, "alice@example.com")
        assert user is not None
        expired = await _user_token(
            seeded_session,
            user_id=user.id,
            tenant_id=ctx_a.tenant_id,
            issued_at=datetime.now(UTC) - timedelta(hours=2),
        )
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {expired}"})
        assert response.status_code == 401

    async def test_user_token_tenant_mismatch_rejected(self, client, seeded_session) -> None:
        ctx_a, ctx_b = await _tenants(seeded_session)
        await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )
        user = await UserService(seeded_session).get_user_by_email(ctx_a, "alice@example.com")
        assert user is not None

        mismatched = await _user_token(seeded_session, user_id=user.id, tenant_id=ctx_b.tenant_id)
        response = await client.get(ME_URL, headers={"Authorization": f"Bearer {mismatched}"})
        assert response.status_code == 401


class TestGetAuthenticatedUser:
    async def test_valid_user_token_produces_user_context(self, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        user = await UserService(seeded_session).create_user(
            ctx_a, email="alice@example.com", name="Alice"
        )
        token = await _user_token(seeded_session, user_id=user.id, tenant_id=ctx_a.tenant_id)
        context = await get_authenticated_user(db=seeded_session, authorization=f"Bearer {token}")
        assert context.user_id == user.id
        assert context.tenant_id == ctx_a.tenant_id
        assert context.email == "alice@example.com"

    async def test_tenant_token_rejected_by_user_dependency(self, seeded_session) -> None:
        ctx_a, _ = await _tenants(seeded_session)
        principal = TenantPrincipal(tenant_id=ctx_a.tenant_id, email="tenant-a@example.com")
        token = create_tenant_api_token(
            principal,
            secret=_settings().tenant_api_token_secret,
            algorithm=_settings().tenant_api_token_algorithm,
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_user(db=seeded_session, authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401

    async def test_missing_authorization_fails(self, seeded_session) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await get_authenticated_user(db=seeded_session, authorization=None)
        assert exc_info.value.status_code == 401


class TestPasswordStorage:
    async def test_plaintext_password_never_stored(self, client, seeded_session) -> None:
        await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )

        rows = (await seeded_session.execute(select(PasswordCredential))).scalars().all()
        assert len(rows) == 1
        credential = rows[0]
        assert credential.password_hash.startswith("$argon2id$")
        assert "AlicePassword123!" not in credential.password_hash
        assert "alice" not in credential.password_hash.lower()

    async def test_stored_hash_verifies_only_with_correct_password(
        self, client, seeded_session
    ) -> None:
        from app.auth.passwords import verify_password

        await _register(
            client,
            TENANT_A_KEY,
            email="alice@example.com",
            name="Alice",
            password="AlicePassword123!",
        )

        credential = (await seeded_session.execute(select(PasswordCredential))).scalar_one()
        assert verify_password("AlicePassword123!", credential.password_hash) is True
        assert verify_password("DifferentPassword123!", credential.password_hash) is False
