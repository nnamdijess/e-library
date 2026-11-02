import asyncio
from uuid import uuid4

import httpx
from test_auth_catalog import client_for, login, add_book
from conftest import ORIGIN


def epub_position():
    return dict(version=1, format="epub", artifact_version=2, cfi="epubcfi(/6/2!/4/2/1:0)", href="text/chapter-0000.xhtml")


def test_progress_persistence_conflicts_retry_and_validation(settings):
    add_book(settings, id="epub", format="epub")
    add_book(settings, id="pdf", sha256="b" * 64, storage_key="private/second.pdf")

    async def scenario():
        path = "/api/v1/books/epub/progress"
        async with client_for(settings) as first:
            assert (await first.get(path)).status_code == 401
            csrf = (await login(first)).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
            assert (await first.get(path)).json()["revision"] == 0
            body = dict(base_revision=0, update_id=str(uuid4()), location=epub_position(), percentage=.25)
            assert (await first.put(path, json=body)).status_code == 403
            saved = await first.put(path, headers=headers, json=body)
            assert saved.status_code == 200 and saved.json()["revision"] == 1
            assert (await first.put(path, headers=headers, json=body)).json()["revision"] == 1
            # A second independently authenticated device sees the same saved CFI.
            async with client_for(settings) as second:
                token2 = (await login(second)).json()["csrf_token"]
                assert (await second.get(path)).json()["location"] == body["location"]
                newer = {**body, "update_id": str(uuid4()), "base_revision": 1, "percentage": .5}
                assert (await second.put(path, headers={"Origin": ORIGIN, "X-CSRF-Token": token2}, json=newer)).json()["revision"] == 2
            stale = await first.put(path, headers=headers, json={**body, "update_id": str(uuid4())})
            assert stale.status_code == 409 and stale.json()["detail"]["current"]["revision"] == 2
            assert (await first.put(path, headers=headers, json=body)).status_code == 409
            for location in ({**epub_position(), "artifact_version": 1}, {**epub_position(), "href": "../../secret"}, {**epub_position(), "cfi": "not-a-cfi"}, dict(version=1, format="pdf", page=1, offset=.5)):
                assert (await first.put(path, headers=headers, json={**body, "location": location})).status_code == 422
            pdf = dict(base_revision=0, update_id=str(uuid4()), location=dict(version=1, format="pdf", page=2, offset=.5), percentage=0)
            assert (await first.put("/api/v1/books/pdf/progress", headers=headers, json=pdf)).json()["percentage"] == .75
            pdf["location"]["page"] = 3
            assert (await first.put("/api/v1/books/pdf/progress", headers=headers, json=pdf)).status_code == 422
            assert (await first.get("/api/v1/books/missing/progress")).status_code == 404
            cookies = httpx.Cookies(first.cookies)
        async with client_for(settings, cookies=cookies) as restarted:
            assert (await restarted.get(path)).json()["revision"] == 2
            assert (await restarted.get(path)).json()["percentage"] == .5
    asyncio.run(scenario())


def test_concurrent_initial_saves_have_one_winner(settings):
    add_book(settings)
    async def scenario():
        async with client_for(settings) as client:
            token = (await login(client)).json()["csrf_token"]
            async def write(page):
                return await client.put("/api/v1/books/test-book/progress", headers={"Origin": ORIGIN, "X-CSRF-Token": token}, json=dict(base_revision=0, update_id=str(uuid4()), location=dict(version=1, format="pdf", page=page, offset=0), percentage=0))
            results = await asyncio.gather(write(1), write(2))
            assert sorted(response.status_code for response in results) == [200, 409]
            assert (await client.get("/api/v1/books/test-book/progress")).json()["revision"] == 1
    asyncio.run(scenario())
