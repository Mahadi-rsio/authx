import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.auth.principal import TenantPrincipal, UserPrincipal
from app.auth.tokens import (
    ExpiredTokenError,
    InvalidPrincipalTypeError,
    InvalidTokenError,
    create_tenant_api_token,
    create_user_access_token,
    decode_tenant_api_token,
    decode_user_access_token,
)

SECRET = "test-user-secret-key-0123456789abcdefgh"
TENANT_PRINCIPAL = TenantPrincipal(
    tenant_id=uuid.uuid4(), email="tenant-a@example.com", name="Tenant A", slug="tenant-a"
)
USER_PRINCIPAL = UserPrincipal(
    user_id=uuid.uuid4(),
    tenant_id=TENANT_PRINCIPAL.tenant_id,
    email="alice@example.com",
    name="Alice",
)


def _user_token(**overrides) -> str:
    return create_user_access_token(USER_PRINCIPAL, secret=SECRET, **overrides)


class TestUserAccessToken:
    def test_token_claims(self) -> None:
        claims = decode_user_access_token(_user_token(), secret=SECRET)
        assert claims.principal_type == "user"
        assert claims.user_id == USER_PRINCIPAL.user_id
        assert claims.tenant_id == USER_PRINCIPAL.tenant_id
        assert claims.expires_at > claims.issued_at
        assert claims.token_id

    def test_claims_include_issued_and_expiration(self) -> None:
        now = (datetime.now(UTC) - timedelta(minutes=5)).replace(microsecond=0)
        claims = decode_user_access_token(
            _user_token(issued_at=now, expires_in=timedelta(minutes=30)), secret=SECRET
        )
        assert claims.issued_at == now
        assert claims.expires_at == now + timedelta(minutes=30)

    def test_token_has_unique_jti(self) -> None:
        first = decode_user_access_token(_user_token(), secret=SECRET)
        second = decode_user_access_token(_user_token(), secret=SECRET)
        assert first.token_id
        assert first.token_id != second.token_id

    def test_invalid_token_fails(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_user_access_token("not-a-jwt", secret=SECRET)

    def test_malformed_token_fails(self) -> None:
        token = _user_token()
        tampered = token[:-4] + "XXXX"
        with pytest.raises(InvalidTokenError):
            decode_user_access_token(tampered, secret=SECRET)

    def test_wrong_signature_fails(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_user_access_token(_user_token(), secret="wrong-secret-key-0123456789abcdefgh")

    def test_expired_token_fails(self) -> None:
        expired = _user_token(issued_at=datetime.now(UTC) - timedelta(hours=2))
        with pytest.raises(ExpiredTokenError):
            decode_user_access_token(expired, secret=SECRET)

    def test_tenant_token_rejected_as_user_token(self) -> None:
        tenant_token = create_tenant_api_token(TENANT_PRINCIPAL, secret=SECRET)
        with pytest.raises(InvalidPrincipalTypeError):
            decode_user_access_token(tenant_token, secret=SECRET)

    def test_user_token_rejected_as_tenant_token(self) -> None:
        with pytest.raises(InvalidPrincipalTypeError):
            decode_tenant_api_token(_user_token(), secret=SECRET)

    def test_subject_mismatch_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid.uuid4()),
            "principal_type": "user",
            "tenant_id": str(USER_PRINCIPAL.tenant_id),
            "user_id": str(USER_PRINCIPAL.user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_user_access_token(token, secret=SECRET)

    def test_missing_user_id_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(USER_PRINCIPAL.user_id),
            "principal_type": "user",
            "tenant_id": str(USER_PRINCIPAL.tenant_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_user_access_token(token, secret=SECRET)

    def test_missing_tenant_id_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(USER_PRINCIPAL.user_id),
            "principal_type": "user",
            "tenant_id": "",
            "user_id": str(USER_PRINCIPAL.user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_user_access_token(token, secret=SECRET)
