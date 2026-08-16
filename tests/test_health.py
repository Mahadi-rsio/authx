import httpx
from app.main import app


async def test_health_returns_200() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "error"}
    assert set(payload["checks"]) == {"database", "redis"}
    assert isinstance(payload["version"], str)


async def test_health_openapi_documented() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths


async def test_openapi_declares_bearer_security_schemes() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()

    schemes = schema["components"]["securitySchemes"]
    assert set(schemes) == {"TenantAPIKey", "UserAccessToken"}
    assert schemes["TenantAPIKey"]["type"] == "http"
    assert schemes["TenantAPIKey"]["scheme"] == "bearer"
    assert schemes["UserAccessToken"]["type"] == "http"
    assert schemes["UserAccessToken"]["scheme"] == "bearer"

    paths = schema["paths"]
    assert paths["/api/v1/auth/users/register"]["post"]["security"] == [{"TenantAPIKey": []}]
    assert paths["/api/v1/auth/users/login"]["post"]["security"] == [{"TenantAPIKey": []}]
    assert paths["/api/v1/auth/users/me"]["get"]["security"] == [{"UserAccessToken": []}]
