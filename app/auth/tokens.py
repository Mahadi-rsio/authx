"""Tenant API Token and User Access Token creation and validation (signed JWTs).

There are two distinct token types:

1. **Tenant API Token** (``principal_type = "tenant"``) — represents an
   authenticated tenant and is required for tenant-level operations such as
   user registration.
2. **User Access Token** (``principal_type = "user"``) — represents an
   authenticated user within a tenant and is required for user-protected
   endpoints.

The ``principal_type`` claim is validated strictly: a tenant token is never
accepted where a user token is required and vice versa.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt

from app.auth.principal import TenantPrincipal, UserPrincipal

PRINCIPAL_TYPE_TENANT = "tenant"
PRINCIPAL_TYPE_USER = "user"

Algorithm = str


class TokenError(Exception):
    """Base error for signed token failures."""


class TenantTokenError(TokenError):
    """Base error for Tenant API Token failures."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed, unsigned, or tampered with."""


class ExpiredTokenError(TokenError):
    """Raised when a token has passed its expiration time."""


class InvalidPrincipalTypeError(TokenError):
    """Raised when a valid token is not of the expected principal type."""


@dataclass(frozen=True, slots=True)
class TenantTokenClaims:
    """Validated claims extracted from a Tenant API Token."""

    tenant_id: UUID
    principal_type: Literal["tenant"]
    issued_at: datetime
    expires_at: datetime
    token_id: str


@dataclass(frozen=True, slots=True)
class UserTokenClaims:
    """Validated claims extracted from a User Access Token."""

    user_id: UUID
    tenant_id: UUID
    principal_type: Literal["user"]
    issued_at: datetime
    expires_at: datetime
    token_id: str


def create_tenant_api_token(
    principal: TenantPrincipal,
    *,
    secret: str,
    algorithm: Algorithm = "HS256",
    expires_in: timedelta | None = None,
    issued_at: datetime | None = None,
    token_id: str | None = None,
) -> str:
    """Mint a signed Tenant API Token for an authenticated tenant.

    The ``sub`` and ``tenant_id`` claims both carry the tenant's id: the
    token is the trusted source of tenant identity.
    """
    now = issued_at or datetime.now(UTC)
    lifetime = expires_in or timedelta(minutes=60)
    tenant_id = str(principal.tenant_id)
    payload = {
        "sub": tenant_id,
        "principal_type": PRINCIPAL_TYPE_TENANT,
        "tenant_id": tenant_id,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": token_id or str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_user_access_token(
    principal: UserPrincipal,
    *,
    secret: str,
    algorithm: Algorithm = "HS256",
    expires_in: timedelta | None = None,
    issued_at: datetime | None = None,
    token_id: str | None = None,
) -> str:
    """Mint a signed User Access Token for an authenticated user.

    ``sub``/``user_id`` carry the user's id and ``tenant_id`` carries the
    tenant the user belongs to: the token is the trusted source of both
    user and tenant identity.
    """
    now = issued_at or datetime.now(UTC)
    lifetime = expires_in or timedelta(minutes=60)
    user_id = str(principal.user_id)
    payload = {
        "sub": user_id,
        "principal_type": PRINCIPAL_TYPE_USER,
        "tenant_id": str(principal.tenant_id),
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": token_id or str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def _decode_token(
    token: str,
    *,
    secret: str,
    algorithm: Algorithm,
    expected_principal_type: Literal["tenant", "user"],
) -> dict:
    """Verify signature/expiration and enforce the expected principal type.

    Raises :class:`ExpiredTokenError` for expired tokens,
    :class:`InvalidPrincipalTypeError` when the principal type differs, and
    :class:`InvalidTokenError` for anything else.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid token") from exc

    principal_type = payload.get("principal_type")
    if principal_type != expected_principal_type:
        raise InvalidPrincipalTypeError(f"Token is not a {expected_principal_type} token")
    return payload


def decode_tenant_api_token(
    token: str,
    *,
    secret: str,
    algorithm: Algorithm = "HS256",
) -> TenantTokenClaims:
    """Validate a Tenant API Token and return its claims."""
    payload = _decode_token(
        token,
        secret=secret,
        algorithm=algorithm,
        expected_principal_type=PRINCIPAL_TYPE_TENANT,
    )

    try:
        tenant_id = UUID(payload["tenant_id"])
        subject = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid Tenant API Token claims") from exc

    if subject != tenant_id:
        raise InvalidTokenError("Invalid Tenant API Token subject")

    issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    return TenantTokenClaims(
        tenant_id=tenant_id,
        principal_type=PRINCIPAL_TYPE_TENANT,
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=str(payload.get("jti") or ""),
    )


def decode_user_access_token(
    token: str,
    *,
    secret: str,
    algorithm: Algorithm = "HS256",
) -> UserTokenClaims:
    """Validate a User Access Token and return its claims."""
    payload = _decode_token(
        token,
        secret=secret,
        algorithm=algorithm,
        expected_principal_type=PRINCIPAL_TYPE_USER,
    )

    try:
        user_id = UUID(payload["user_id"])
        tenant_id = UUID(payload["tenant_id"])
        subject = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid User Access Token claims") from exc

    if subject != user_id:
        raise InvalidTokenError("Invalid User Access Token subject")

    issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    return UserTokenClaims(
        user_id=user_id,
        tenant_id=tenant_id,
        principal_type=PRINCIPAL_TYPE_USER,
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=str(payload.get("jti") or ""),
    )
