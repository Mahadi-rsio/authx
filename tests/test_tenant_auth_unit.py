import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.auth.passwords import hash_password, verify_password
from app.auth.principal import TenantPrincipal
from app.auth.tokens import (
    ExpiredTokenError,
    InvalidPrincipalTypeError,
    InvalidTokenError,
    create_tenant_api_token,
    decode_tenant_api_token,
)

SECRET = "test-secret-key-0123456789abcdefgh"
PRINCIPAL = TenantPrincipal(
    tenant_id=uuid.uuid4(), email="tenant-a@example.com", name="Tenant A", slug="tenant-a"
)


def _token(**overrides) -> str:
    return create_tenant_api_token(PRINCIPAL, secret=SECRET, **overrides)


class TestPasswordHashing:
    def test_hash_is_argon2id(self) -> None:
        digest = hash_password("TenantA123!")
        assert digest.startswith("$argon2id$")
        assert digest != "TenantA123!"

    def test_verify_password(self) -> None:
        digest = hash_password("TenantA123!")
        assert verify_password("TenantA123!", digest) is True
        assert verify_password("wrong-password", digest) is False

    def test_plaintext_never_embedded_in_hash(self) -> None:
        plaintext = "TenantA123!"
        assert plaintext not in hash_password(plaintext)

    def test_hashes_are_salted(self) -> None:
        assert hash_password("TenantA123!") != hash_password("TenantA123!")


class TestTenantApiToken:
    def test_token_claims(self) -> None:
        claims = decode_tenant_api_token(_token(), secret=SECRET)
        assert claims.principal_type == "tenant"
        assert claims.tenant_id == PRINCIPAL.tenant_id
        assert claims.expires_at > claims.issued_at
        assert claims.token_id

    def test_claims_include_issued_and_expiration(self) -> None:
        now = (datetime.now(UTC) - timedelta(minutes=5)).replace(microsecond=0)
        claims = decode_tenant_api_token(
            _token(issued_at=now, expires_in=timedelta(minutes=30)), secret=SECRET
        )
        assert claims.issued_at == now
        assert claims.expires_at == now + timedelta(minutes=30)

    def test_token_has_jti(self) -> None:
        first = decode_tenant_api_token(_token(), secret=SECRET)
        second = decode_tenant_api_token(_token(), secret=SECRET)
        assert first.token_id
        assert first.token_id != second.token_id

    def test_invalid_token_fails(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_tenant_api_token("not-a-jwt", secret=SECRET)

    def test_malformed_token_fails(self) -> None:
        token = _token()
        tampered = token[:-4] + "XXXX"
        with pytest.raises(InvalidTokenError):
            decode_tenant_api_token(tampered, secret=SECRET)

    def test_wrong_signature_fails(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_tenant_api_token(_token(), secret="wrong-secret-key-0123456789abcdefgh")

    def test_expired_token_fails(self) -> None:
        expired = _token(issued_at=datetime.now(UTC) - timedelta(hours=2))
        with pytest.raises(ExpiredTokenError):
            decode_tenant_api_token(expired, secret=SECRET)

    def test_non_tenant_token_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(PRINCIPAL.tenant_id),
            "principal_type": "user",
            "tenant_id": str(PRINCIPAL.tenant_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidPrincipalTypeError):
            decode_tenant_api_token(token, secret=SECRET)

    def test_subject_mismatch_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid.uuid4()),
            "principal_type": "tenant",
            "tenant_id": str(PRINCIPAL.tenant_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_tenant_api_token(token, secret=SECRET)

    def test_missing_tenant_id_fails(self) -> None:
        now = datetime.now(UTC)
        payload = {
            "sub": str(PRINCIPAL.tenant_id),
            "principal_type": "tenant",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=30)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        token = jwt.encode(payload, SECRET, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_tenant_api_token(token, secret=SECRET)
