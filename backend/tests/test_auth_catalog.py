import asyncio
from contextlib import asynccontextmanager
import time

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import COOKIE, LOGIN_LIMIT
from app.config import Settings
from app.database import make_engine, migrate
from app.main import create_app
from app.models import Base, Book, LoginSession, User
from app.security import provision_owner, token_hash
from conftest import ORIGIN, PASSWORD


@asynccontextmanager
async def client_for(settings, cookies=None):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies) as client:
            yield client


async def login(client, username="owner", password=PASSWORD):
    initial = await client.get("/api/v1/auth/csrf", headers={"X-Ebook-Request": "1"})
    assert initial.status_code == 200
    return await client.post("/api/v1/auth/login", headers={"Origin": ORIGIN, "X-CSRF-Token": initial.json()["csrf_token"]}, json={"username": username, "password": password})


def add_book(settings, **overrides):
    values = dict(id="test-book", owner_id=1, format="pdf", title="Persistence fixture", authors=["Test author"], original_filename="fixture.pdf", storage_key="private/fixture.pdf", sha256="a" * 64, byte_size=20, page_count=2)
    values.update(overrides)
    engine = make_engine(settings)
    try:
        with Session(engine) as db:
            db.add(Book(**values))
            db.commit()
    finally:
        engine.dispose()


def test_catalog_requires_authentication(settings):
    async def scenario():
        async with client_for(settings) as client:
            for endpoint in ("/auth/me", "/books", "/books/test-book"):
                response = await client.get("/api/v1" + endpoint)
                assert response.status_code == 401
                assert response.headers["cache-control"] == "no-store"
            assert (await client.get("/api/v1/health")).status_code == 200
    asyncio.run(scenario())


def test_login_rotates_and_hashes_session_cookie(settings):
    async def scenario():
        async with client_for(settings) as client:
            await client.get("/api/v1/auth/csrf", headers={"X-Ebook-Request": "1"})
            anonymous = client.cookies.get(COOKIE)
            response = await login(client, username="OWNER")
            assert response.status_code == 200
            token = client.cookies.get(COOKIE)
            assert token != anonymous
            cookie = response.headers["set-cookie"].lower()
            assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
            assert response.json()["user"] == {"username": "owner"}
            assert (await client.get("/api/v1/auth/me")).json() == response.json()
            assert (await client.get("/api/v1/books")).json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
            engine = make_engine(settings)
            try:
                with Session(engine) as db:
                    assert db.get(LoginSession, token_hash(anonymous)) is None
                    record = db.get(LoginSession, token_hash(token))
                    assert record.user_id == 1 and record.token_hash != token
                    assert db.get(User, 1).password_hash.startswith("$argon2id$")
            finally:
                engine.dispose()
    asyncio.run(scenario())


def test_login_and_logout_require_origin_and_csrf(settings):
    async def scenario():
        async with client_for(settings) as client:
            assert (await client.get("/api/v1/auth/csrf")).status_code == 403
            initial = await client.get("/api/v1/auth/csrf", headers={"X-Ebook-Request": "1"})
            csrf = initial.json()["csrf_token"]
            body = {"username": "owner", "password": PASSWORD}
            for headers in ({}, {"Origin": ORIGIN}, {"Origin": "https://attacker.example", "X-CSRF-Token": csrf}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}):
                assert (await client.post("/api/v1/auth/login", json=body, headers=headers)).status_code == 403
            auth = await login(client)
            authenticated_csrf = auth.json()["csrf_token"]
            assert authenticated_csrf != csrf
            assert (await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})).status_code == 403
            assert (await client.get("/api/v1/auth/me")).status_code == 200
            saved = httpx.Cookies(client.cookies)
            assert (await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": authenticated_csrf})).status_code == 204
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            client.cookies.update(saved)
            assert (await client.get("/api/v1/auth/me")).status_code == 401
    asyncio.run(scenario())


def test_invalid_credentials_are_generic_and_validation_does_not_echo_password(settings):
    async def scenario():
        async with client_for(settings) as client:
            known = await login(client, password="incorrect secret")
            unknown = await login(client, username="absent", password="incorrect secret")
            assert known.status_code == unknown.status_code == 401
            assert known.json() == unknown.json()
            invalid = await login(client, password="s" * 1025)
            assert invalid.status_code == 422
            assert "s" * 1025 not in invalid.text
    asyncio.run(scenario())


def test_expired_sessions_are_rejected_by_server(settings):
    async def scenario():
        async with client_for(settings) as client:
            assert (await login(client)).status_code == 200
            token = client.cookies.get(COOKIE)
            engine = make_engine(settings)
            try:
                with Session(engine) as db:
                    db.execute(update(LoginSession).where(LoginSession.token_hash == token_hash(token)).values(expires_at=int(time.time()) - 1))
                    db.commit()
            finally:
                engine.dispose()
            assert (await client.get("/api/v1/books")).status_code == 401
    asyncio.run(scenario())


def test_throttle_survives_new_application_instance(settings):
    async def scenario():
        async with client_for(settings) as client:
            for _ in range(LOGIN_LIMIT):
                assert (await login(client, password="wrong")).status_code == 401
            response = await login(client)
            assert response.status_code == 429 and response.headers["retry-after"] == "300"
        async with client_for(settings) as restarted:
            assert (await login(restarted)).status_code == 429
    asyncio.run(scenario())


def test_concurrent_logins_use_independent_sessions(settings):
    async def scenario():
        async with client_for(settings) as first, client_for(settings) as second:
            responses = await asyncio.gather(login(first), login(second))
            assert [response.status_code for response in responses] == [200, 200]
            assert first.cookies.get(COOKIE) != second.cookies.get(COOKIE)
            assert (await first.get("/api/v1/auth/me")).status_code == 200
            assert (await second.get("/api/v1/auth/me")).status_code == 200
    asyncio.run(scenario())


def test_catalog_and_session_survive_restart_and_migration_rerun(settings):
    add_book(settings)

    async def scenario():
        async with client_for(settings) as client:
            assert (await login(client)).status_code == 200
            cookies = httpx.Cookies(client.cookies)
            initial = (await client.get("/api/v1/books")).json()
            item = initial["items"][0]
            assert item["title"] == "Persistence fixture"
            assert "storage_key" not in item and "sha256" not in item
            assert (await client.get("/api/v1/books/test-book")).json() == item
            assert (await client.get("/api/v1/books/missing")).status_code == 404
            assert (await client.get("/api/v1/books?limit=0")).status_code == 422
            assert (await client.get("/api/v1/books?offset=1")).json()["items"] == []
        migrate(settings)
        async with client_for(settings, cookies=cookies) as restarted:
            assert (await restarted.get("/api/v1/books")).json() == initial
    asyncio.run(scenario())


def test_schema_matches_models_and_owner_cannot_be_replaced(settings):
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        with Session(engine) as db:
            encoded = db.get(User, 1).password_hash
            with pytest.raises(ValueError, match="already exists"):
                provision_owner(db, "replacement", "another long password")
            assert db.get(User, 1).password_hash == encoded
    finally:
        engine.dispose()


@pytest.mark.parametrize("overrides", [{"owner_id": 999}, {"format": "exe"}, {"byte_size": -1}, {"page_count": 0}])
def test_catalog_integrity_constraints(settings, overrides):
    with pytest.raises(IntegrityError):
        add_book(settings, **overrides)


def test_secure_cookie_configuration(settings):
    async def scenario():
        secure = settings.model_copy(update={"session_cookie_secure": True})
        async with client_for(secure) as client:
            response = await client.get("/api/v1/auth/csrf", headers={"X-Ebook-Request": "1"})
            assert "secure" in response.headers["set-cookie"].lower()
    asyncio.run(scenario())


@pytest.mark.parametrize("origin", ["http://server.example", "https://server.example", "http://127.0.0.1:3000/", "https://user:secret@server.example"])
def test_unsafe_origins_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_origins=[origin])


def test_startup_requires_explicit_migration(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)

    async def scenario():
        app = create_app(settings)
        with pytest.raises(RuntimeError, match="app.cli migrate"):
            async with app.router.lifespan_context(app):
                pass
        assert not (tmp_path / "library.sqlite3").exists()
    asyncio.run(scenario())
