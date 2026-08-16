from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.redis import get_redis
from app.database.session import get_db_session

router = APIRouter(tags=["health"])


class CheckStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class HealthResponse(BaseModel):
    status: CheckStatus
    version: str
    checks: dict[str, CheckStatus]


async def _check_database(session: AsyncSession) -> CheckStatus:
    try:
        await session.execute(text("SELECT 1"))
        return CheckStatus.OK
    except Exception:
        return CheckStatus.ERROR


async def _check_redis(redis: Redis) -> CheckStatus:
    try:
        return CheckStatus.OK if await redis.ping() else CheckStatus.ERROR
    except Exception:
        return CheckStatus.ERROR


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> HealthResponse:
    """Liveness endpoint reporting connectivity to backing services."""
    checks = {
        "database": await _check_database(db),
        "redis": await _check_redis(redis),
    }
    status = (
        CheckStatus.OK if all(c is CheckStatus.OK for c in checks.values()) else CheckStatus.ERROR
    )
    return HealthResponse(status=status, version=__version__, checks=checks)
