from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "authx"
    assert settings.app_env == "development"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.database_pool_size >= 1


def test_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "custom")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")

    settings = Settings(_env_file=None)
    assert settings.app_name == "custom"
    assert settings.app_env == "production"
    assert settings.debug is True
    assert settings.is_development is False


def test_settings_development_property() -> None:
    assert Settings(_env_file=None).is_development is True
