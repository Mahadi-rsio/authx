from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Security, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_authenticated_tenant,
    get_authenticated_user,
    tenant_bearer,
    user_bearer,
)
from app.auth.principal import UserContext
from app.database.session import get_db_session
from app.services.tenant_auth_service import TenantAuthService
from app.services.user_auth_service import DuplicateEmailError, UserAuthService
from app.tenants.context import TenantContext

router = APIRouter(tags=["auth"])


class TenantLoginRequest(BaseModel):
    """Development tenant login credentials."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """A bearer token (tenant or user)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class UserRegisterRequest(BaseModel):
    """User registration payload.

    The tenant is derived from the authenticated Tenant API Token; a
    ``tenant_id`` supplied here is intentionally ignored.
    """

    email: str
    name: str
    password: str


class UserLoginRequest(BaseModel):
    """User login credentials (scoped to the authenticated tenant)."""

    email: str
    password: str


class UserResponse(BaseModel):
    """A public user representation."""

    id: UUID
    tenant_id: UUID
    email: str
    name: str
    email_verified: bool


@router.post("/auth/tenant/login", response_model=TokenResponse)
async def tenant_login(
    payload: TenantLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Authenticate a development tenant and issue a Tenant API Token.

    The returned token is a TENANT token, not a user token: it represents
    an authenticated tenant and is required for tenant-level operations such
    as user registration. Unknown tenants and wrong passwords both return
    401 to avoid user enumeration.
    """
    service = TenantAuthService(db)
    principal = await service.authenticate(payload.email, payload.password)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = service.issue_api_token(principal)
    return TokenResponse(access_token=token, token_type="bearer")


@router.post(
    "/auth/users/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(tenant_bearer)],
)
async def register_user(
    payload: UserRegisterRequest,
    tenant: Annotated[TenantContext, Depends(get_authenticated_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Register a user inside the authenticated tenant.

    Requires a valid Tenant API Token. The tenant comes ONLY from the token;
    a ``tenant_id`` in the request body is ignored. Passwords are hashed
    with Argon2id and never stored in plaintext.
    """
    service = UserAuthService(db)
    try:
        user = await service.register_user(
            tenant,
            email=payload.email,
            name=payload.name,
            password=payload.password,
        )
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in this tenant",
        ) from exc
    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
    )


@router.post(
    "/auth/users/login",
    response_model=TokenResponse,
    dependencies=[Security(tenant_bearer)],
)
async def user_login(
    payload: UserLoginRequest,
    tenant: Annotated[TenantContext, Depends(get_authenticated_tenant)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Authenticate a user within the authenticated tenant.

    Requires a valid Tenant API Token so the email lookup is scoped to one
    tenant. On success a USER Access Token is issued — never a Tenant API
    Token. Unknown users and wrong passwords both return 401.
    """
    service = UserAuthService(db)
    principal = await service.authenticate_user(
        tenant, email=payload.email, password=payload.password
    )
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = service.issue_user_token(principal)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get(
    "/auth/users/me",
    response_model=UserResponse,
    dependencies=[Security(user_bearer)],
)
async def users_me(
    user: Annotated[UserContext, Depends(get_authenticated_user)],
) -> UserResponse:
    """Return the authenticated user.

    Requires a valid USER Access Token (a Tenant API Token is rejected).
    """
    return UserResponse(
        id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified,
    )
