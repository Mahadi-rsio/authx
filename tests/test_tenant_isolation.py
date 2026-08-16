import pytest
from app.repositories.password_credential import PasswordCredentialRepository
from app.services.identity_service import IdentityService
from app.services.tenant_service import TenantService
from app.services.user_service import UserService
from app.tenants.context import TenantContext
from app.tenants.resolver import HeaderTenantResolver, TenantNotFoundError
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

PROVIDER = "google"


async def _tenants(db_session) -> tuple[TenantContext, TenantContext]:
    service = TenantService(db_session)
    tenant_a = await service.create_tenant(name="Tenant A", slug="tenant-a")
    tenant_b = await service.create_tenant(name="Tenant B", slug="tenant-b")
    return TenantContext.from_tenant(tenant_a), TenantContext.from_tenant(tenant_b)


async def test_same_email_in_different_tenants_creates_independent_users(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)

    alice_a = await user_service.create_user(ctx_a, email="alice@example.com", name="Alice")
    alice_b = await user_service.create_user(ctx_b, email="alice@example.com", name="Alice")

    assert alice_a.id != alice_b.id
    assert alice_a.email == alice_b.email == "alice@example.com"

    assert (await user_service.get_user_by_email(ctx_a, "alice@example.com")).id == alice_a.id
    assert (await user_service.get_user_by_email(ctx_b, "alice@example.com")).id == alice_b.id

    # Neither tenant can see the other tenant's user.
    assert await user_service.get_user(ctx_a, alice_b.id) is None
    assert await user_service.get_user(ctx_b, alice_a.id) is None


async def test_email_uniqueness_is_tenant_scoped(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)

    await user_service.create_user(ctx_a, email="dup@example.com", name="First")

    with pytest.raises(IntegrityError):
        await user_service.create_user(ctx_a, email="dup@example.com", name="Second")
    await db_session.rollback()

    # Same email is allowed in a different tenant.
    other = await user_service.create_user(ctx_b, email="dup@example.com", name="Third")
    assert other.id is not None


async def test_email_lookup_is_case_insensitive(db_session) -> None:
    ctx_a, _ = await _tenants(db_session)
    user_service = UserService(db_session)

    created = await user_service.create_user(ctx_a, email="Alice@Example.COM", name="Alice")
    assert created.email == "alice@example.com"

    fetched = await user_service.get_user_by_email(ctx_a, "ALICE@example.com")
    assert fetched is not None
    assert fetched.id == created.id


async def test_identity_belongs_to_one_tenant(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)
    identity_service = IdentityService(db_session)

    user_a = await user_service.create_user(ctx_a, email="a@example.com", name="A")
    await user_service.create_user(ctx_b, email="b@example.com", name="B")

    identity = await identity_service.create_identity(
        ctx_a,
        user_id=user_a.id,
        provider=PROVIDER,
        provider_user_id="g-1",
        provider_email="a@example.com",
    )

    # Accessible within the owning tenant.
    assert (await identity_service.get_identity(ctx_a, PROVIDER, "g-1")).id == identity.id
    assert (await identity_service.get_identity_by_id(ctx_a, identity.id)).id == identity.id

    # Invisible through the other tenant even with identical provider keys.
    assert await identity_service.get_identity(ctx_b, PROVIDER, "g-1") is None
    assert await identity_service.get_identity_by_id(ctx_b, identity.id) is None


async def test_provider_identity_uniqueness_is_tenant_scoped(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)
    identity_service = IdentityService(db_session)

    user_a = await user_service.create_user(ctx_a, email="a@example.com", name="A")
    user_b = await user_service.create_user(ctx_b, email="b@example.com", name="B")
    user_a_id = user_a.id
    user_b_id = user_b.id

    await identity_service.create_identity(
        ctx_a, user_id=user_a_id, provider=PROVIDER, provider_user_id="g-1"
    )

    with pytest.raises(IntegrityError):
        await identity_service.create_identity(
            ctx_a, user_id=user_a_id, provider=PROVIDER, provider_user_id="g-1"
        )
    await db_session.rollback()

    # Same provider_user_id in a different tenant is allowed.
    other = await identity_service.create_identity(
        ctx_b, user_id=user_b_id, provider=PROVIDER, provider_user_id="g-1"
    )
    assert other.id is not None


async def test_cross_tenant_identity_user_link_is_rejected(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)
    identity_service = IdentityService(db_session)

    await user_service.create_user(ctx_a, email="a@example.com", name="A")
    user_b = await user_service.create_user(ctx_b, email="b@example.com", name="B")

    # Attempting to attach a user that belongs to tenant B onto an identity
    # in tenant A must fail at the database level.
    with pytest.raises(IntegrityError):
        await identity_service.create_identity(
            ctx_a, user_id=user_b.id, provider=PROVIDER, provider_user_id="g-x"
        )
    await db_session.rollback()


async def test_cross_tenant_password_credential_user_link_is_rejected(db_session) -> None:
    ctx_a, ctx_b = await _tenants(db_session)
    user_service = UserService(db_session)
    credential_repository = PasswordCredentialRepository(db_session)

    await user_service.create_user(ctx_a, email="a@example.com", name="A")
    user_b = await user_service.create_user(ctx_b, email="b@example.com", name="B")

    # A credential for tenant B's user can never be created inside tenant A:
    # the composite FK (tenant_id, user_id) -> users(tenant_id, id) rejects it.
    with pytest.raises(IntegrityError):
        await credential_repository.create(
            tenant_id=ctx_a.tenant_id,
            user_id=user_b.id,
            password_hash="does-not-matter",
        )
    await db_session.rollback()


async def test_tenant_slug_is_unique(db_session) -> None:
    service = TenantService(db_session)
    await service.create_tenant(name="First", slug="acme")

    with pytest.raises(IntegrityError):
        await service.create_tenant(name="Second", slug="acme")


async def test_header_resolver_validates_against_database(db_session) -> None:
    service = TenantService(db_session)
    tenant = await service.create_tenant(name="Acme", slug="acme")

    resolver = HeaderTenantResolver()
    context = await resolver.resolve(db_session, str(tenant.id))
    assert context.tenant_id == tenant.id
    assert context.slug == "acme"

    with pytest.raises(TenantNotFoundError):
        await resolver.resolve(db_session, "00000000-0000-0000-0000-000000000000")
