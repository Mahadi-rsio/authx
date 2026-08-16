from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.redis import close_redis
from app.database.session import async_session_factory, engine
from app.services.dev_seed import seed_dev_tenants


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.is_development:
        async with async_session_factory() as session:
            await seed_dev_tenants(session, settings)
    yield
    await engine.dispose()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


app = create_app()
