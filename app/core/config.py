from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DevTenantCredential(BaseModel):
    """A development-only mock tenant credential.

    Used to seed mock tenants on development/test startup. Never populated
    in production; plaintext passwords never touch the database.
    """

    email: str
    password: str
    name: str
    slug: str
    api_key: str | None = None


class Settings(BaseSettings):
    """Application settings.

    Values are read from the process environment (case-insensitive) and,
    when present, an ``.env``/``.env.local`` file. Field names map to
    environment variables directly, e.g. ``DATABASE_URL`` -> ``database_url``.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "authx"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Tenant authentication hostname. Each tenant is addressed via
    # ``auth.<slug><auth_host_suffix>`` (e.g. ``auth.tenant-a.example.com``).
    # The hostname identifies WHICH tenant is being accessed and must match
    # the tenant authenticated by the API key.
    auth_host_prefix: str = "auth."
    auth_host_suffix: str = ".example.com"

    database_url: str = "postgresql+asyncpg://authx:authx@localhost:5432/authx"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"

    # Tenant API Token (development tenant authentication).
    tenant_api_token_secret: str = "dev-tenant-api-token-secret-change-me"
    tenant_api_token_algorithm: str = "HS256"
    tenant_api_token_expire_minutes: int = 60

    # User Access Token (authenticated user within a tenant).
    user_access_token_secret: str = "dev-user-access-token-secret-change-me"
    user_access_token_algorithm: str = "HS256"
    user_access_token_expire_minutes: int = 60

    # Development-only mock tenant credentials used by the seed/bootstrap
    # logic and mock API key resolver. Override as a JSON array, e.g.:
    #   DEV_TENANT_CREDENTIALS='[{"email":"a@example.com","password":"..",...}]'
    dev_tenant_credentials: list[DevTenantCredential] = [
        DevTenantCredential(
            email="tenant-a@example.com",
            password="TenantA123!",
            name="Tenant A",
            slug="tenant-a",
            api_key="ax_test_tenant_a_mock_key",
        ),
        DevTenantCredential(
            email="tenant-b@example.com",
            password="TenantB123!",
            name="Tenant B",
            slug="tenant-b",
            api_key="ax_test_tenant_b_mock_key",
        ),
    ]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Cached so that all import-time consumers share one configuration.
    """
    return Settings()
