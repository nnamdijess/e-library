import asyncio
import httpx
import pytest
from uuid import uuid4
from sqlalchemy.orm import Session

from app.database import make_engine
from app.models import Book
from app.storage import storage_path
from book_fixtures import epub_bytes
from conftest import ORIGIN
from test_auth_catalog import client_for, login, add_book
from test_ingestion import upload


def test_rename_preserves_original_artifact_and_progress(settings):
    async def scenario():
        async with client_for(settings) as client:
            token = (await login(client)).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
            content = epub_bytes()
            uploaded = (await upload(client, content)).json()["book"]
            path = f"/api/v1/books/{uploaded['id']}"
            assert (await client.patch(path, json={"title": "New title"})).status_code == 403
            prepared = (await client.get(path + "/epub")).json()
            artifact = (await client.get(prepared["content_url"])).content
            saved = await client.put(path + "/progress", headers=headers, json={"base_revision": 0, "update_id": str(uuid4()), "location": {"version": 1, "format": "epub", "artifact_version": 2, "cfi": "epubcfi(/6/2!/4/2/1:0)", "href": "text/chapter-0000.xhtml"}, "percentage": .25})
            assert saved.status_code == 200
            progress = (await client.get(path + "/progress")).json()
            renamed = await client.patch(path, headers=headers, json={"title": "  Clean title — Ω & #1  "})
            assert renamed.status_code == 200 and renamed.json()["title"] == "Clean title — Ω & #1"
            assert (await client.get(prepared["content_url"])).content == artifact
            assert (await client.get(path + "/progress")).json() == progress
            engine = make_engine(settings)
            try:
                with Session(engine) as db:
                    record = db.get(Book, uploaded["id"])
                    assert storage_path(settings, record.storage_key).read_bytes() == content
            finally:
                engine.dispose()
            cookies = httpx.Cookies(client.cookies)
        async with client_for(settings, cookies=cookies) as restarted:
            assert (await restarted.get(path)).json()["title"] == "Clean title — Ω & #1"
            assert (await restarted.get("/api/v1/books")).json()["items"][0]["title"] == "Clean title — Ω & #1"
    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [{"title": "  "}, {"title": "x" * 501}, {"title": "a\x00b"}, {"title": "a\nb"}, {"title": "Good", "storage_key": "../../secret"}])
def test_title_validation_and_access(settings, payload):
    add_book(settings)
    async def scenario():
        async with client_for(settings) as client:
            assert (await client.patch("/api/v1/books/test-book", json=payload)).status_code == 401
            token = (await login(client)).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": token}
            assert (await client.patch("/api/v1/books/test-book", headers=headers, json=payload)).status_code == 422
            assert (await client.patch("/api/v1/books/missing", headers=headers, json={"title": "Valid"})).status_code == 404
            assert (await client.get("/api/v1/books/test-book")).json()["title"] == "Persistence fixture"
    asyncio.run(scenario())
