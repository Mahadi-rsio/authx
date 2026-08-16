"""Tenant API Token creation and validation (signed JWTs).

A Tenant API Token is NOT a user credential. It represents an authenticated
tenant and is required for tenant-level operations such as user registration.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt

from app.auth.principal import TenantPrincipal

PRINCIPAL_TYPE_TENANT = "tenant"

Algorithm = str


class TenantTokenError(Exception):
    """Base error for Tenant API Token failures."""


class InvalidTokenError(TenantTokenError):
    """Raised when a token is malformed, unsigned, or tampered with."""


class ExpiredTokenError(TenantTokenError):
    """Raised when a token has passed its expiration time."""


class InvalidPrincipalTypeError(TenantTokenError):
    """Raised when a valid token is not a tenant token."""


@dataclass(frozen=True, slots=True)
class TenantTokenClaims:
    """Validated claims extracted from a Tenant API Token."""

    tenant_id: UUID
    principal_type: Literal["tenant"]
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


def decode_tenant_api_token(
    token: str,
    *,
    secret: str,
    algorithm: Algorithm = "HS256",
) -> TenantTokenClaims:
    """Validate a Tenant API Token and return its claims.

    Raises :class:`ExpiredTokenError` for expired tokens,
    :class:`InvalidPrincipalTypeError` for non-tenant tokens, and
    :class:`InvalidTokenError` for anything else.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Tenant API Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid Tenant API Token") from exc

    principal_type = payload.get("principal_type")
    if principal_type != PRINCIPAL_TYPE_TENANT:
        raise InvalidPrincipalTypeError("Token is not a tenant token")

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
