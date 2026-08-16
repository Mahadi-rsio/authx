from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.services.tenant_auth_service import TenantAuthService

router = APIRouter(tags=["auth"])


class TenantLoginRequest(BaseModel):
    """Development tenant login credentials."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """A Tenant API Token (development tenant authentication)."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


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
