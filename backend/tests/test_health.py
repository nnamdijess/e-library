import asyncio

import httpx

from app.config import Settings
from app.main import create_app


def test_health_contract():
    # Ignore any developer .env file: the test owns its configuration.
    application = create_app(Settings(_env_file=None))
    async def request_health():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/v1/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}
