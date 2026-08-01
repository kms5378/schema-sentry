import httpx
import pytest


@pytest.mark.asyncio
async def test_live_does_not_touch_dependencies() -> None:
    from schema_sentry.api.app import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
