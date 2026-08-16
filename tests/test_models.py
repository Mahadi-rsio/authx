from app.models.identity import Identity
from app.models.password_credential import PasswordCredential
from app.models.tenant import Tenant
from app.models.user import User
from sqlalchemy import UniqueConstraint


def _unique_constraints(table) -> dict[str, UniqueConstraint]:
    return {c.name: c for c in table.constraints if isinstance(c, UniqueConstraint)}


def _unique_indexes(table):
    return {ix.name: list(ix.columns.keys()) for ix in table.indexes if ix.unique}


def _fk_to_tenants(table):
    return next(fk for fk in table.foreign_keys if fk.column.table.name == "tenants")


def test_tenant_slug_is_unique() -> None:
    assert _unique_indexes(Tenant.__table__)["ix_tenants_slug"] == ["slug"]


def test_tenant_columns() -> None:
    columns = set(Tenant.__table__.columns.keys())
    assert {"id", "name", "slug", "created_at", "updated_at"} <= columns


def test_user_email_uniqueness_is_tenant_scoped() -> None:
    constraints = _unique_constraints(User.__table__)
    assert "uq_users_tenant_id_email" in constraints
    assert list(constraints["uq_users_tenant_id_email"].columns.keys()) == ["tenant_id", "email"]


def test_user_belongs_to_exactly_one_tenant() -> None:
    fk = _fk_to_tenants(User.__table__)
    assert fk.parent.name == "tenant_id"
    assert fk.column.table.name == "tenants"
    assert User.__table__.columns["tenant_id"].nullable is False


def test_tenant_owned_tables_index_tenant_id() -> None:
    for table in (User.__table__, Identity.__table__, PasswordCredential.__table__):
        assert any(list(ix.columns.keys()) == ["tenant_id"] for ix in table.indexes), table.name


def test_identity_provider_uniqueness_is_tenant_scoped() -> None:
    constraints = _unique_constraints(Identity.__table__)
    assert "uq_identities_tenant_provider_provider_user_id" in constraints
    assert list(constraints["uq_identities_tenant_provider_provider_user_id"].columns.keys()) == [
        "tenant_id",
        "provider",
        "provider_user_id",
    ]


def test_identity_has_composite_fk_against_users_tenant() -> None:
    composite = next(
        c
        for c in Identity.__table__.foreign_key_constraints
        if c.name == "fk_identities_tenant_user_users"
    )
    assert list(composite.columns.keys()) == ["tenant_id", "user_id"]
    assert composite.referred_table.name == "users"
    assert [e.target_fullname for e in composite.elements] == ["users.tenant_id", "users.id"]


def test_identity_owns_tenant_fk_and_user_index() -> None:
    assert _fk_to_tenants(Identity.__table__).parent.name == "tenant_id"
    assert any(list(ix.columns.keys()) == ["user_id"] for ix in Identity.__table__.indexes)


def test_password_credential_uniqueness_is_tenant_scoped() -> None:
    constraints = _unique_constraints(PasswordCredential.__table__)
    assert "uq_password_credentials_tenant_id_user_id" in constraints
    assert list(constraints["uq_password_credentials_tenant_id_user_id"].columns.keys()) == [
        "tenant_id",
        "user_id",
    ]


def test_password_credential_has_composite_fk_against_users_tenant() -> None:
    composite = next(
        c
        for c in PasswordCredential.__table__.foreign_key_constraints
        if c.name == "fk_password_credentials_tenant_user_users"
    )
    assert list(composite.columns.keys()) == ["tenant_id", "user_id"]
    assert composite.referred_table.name == "users"
    assert [e.target_fullname for e in composite.elements] == ["users.tenant_id", "users.id"]


def test_password_credential_owns_tenant_fk_and_user_index() -> None:
    assert _fk_to_tenants(PasswordCredential.__table__).parent.name == "tenant_id"
    user_indexes = [
        ix for ix in PasswordCredential.__table__.indexes if list(ix.columns.keys()) == ["user_id"]
    ]
    assert user_indexes


def test_password_credential_has_changed_at() -> None:
    assert "password_changed_at" in PasswordCredential.__table__.columns.keys()
