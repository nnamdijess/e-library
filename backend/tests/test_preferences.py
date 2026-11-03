import asyncio
import httpx
import pytest
from test_auth_catalog import client_for, login
from conftest import ORIGIN


def test_preferences_auth_patch_merge_and_restart(settings):
    async def scenario():
        async with client_for(settings) as client:
            assert (await client.get("/api/v1/preferences")).status_code == 401
            token = (await login(client)).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
            defaults = (await client.get("/api/v1/preferences")).json()
            assert defaults["pdf_zoom"] == "fit-page"
            assert (await client.patch("/api/v1/preferences", json={"theme": "dark"})).status_code == 403
            assert (await client.patch("/api/v1/preferences", headers=headers, json={"theme": "dark", "pdf_zoom": "75"})).status_code == 200
            # An independent device changing typography must preserve the theme.
            async with client_for(settings) as other:
                other_token = (await login(other)).json()["csrf_token"]
                changed = await other.patch("/api/v1/preferences", headers={"Origin": ORIGIN, "X-CSRF-Token": other_token}, json={"font_size": 26, "margin": 64})
                assert changed.json()["theme"] == "dark" and changed.json()["pdf_zoom"] == "75"
            cookies = httpx.Cookies(client.cookies)
        async with client_for(settings, cookies=cookies) as restarted:
            saved = (await restarted.get("/api/v1/preferences")).json()
            assert saved["theme"] == "dark" and saved["font_size"] == 26 and saved["margin"] == 64
    asyncio.run(scenario())


@pytest.mark.parametrize("patch", [{"theme": "javascript:alert(1)"}, {"font_family": "url(https://invalid.example)"}, {"font_size": 200}, {"line_height": 0}, {"margin": -1}, {"pdf_zoom": "900"}, {"theme": None}, {"unknown": 1}])
def test_invalid_preferences_are_rejected(settings, patch):
    async def scenario():
        async with client_for(settings) as client:
            token = (await login(client)).json()["csrf_token"]
            assert (await client.patch("/api/v1/preferences", headers={"Origin": ORIGIN, "X-CSRF-Token": token}, json=patch)).status_code == 422
            assert (await client.get("/api/v1/preferences")).json()["theme"] == "light"
    asyncio.run(scenario())
