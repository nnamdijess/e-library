import asyncio
from io import BytesIO
from pathlib import Path
import stat
import threading
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import httpx
from PIL import Image
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import make_engine, migrate
from app.documents import InvalidDocument, inspect_document
from app.models import Book
from app.storage import StorageFailure, audit_storage, ingest_book, inspect_in_process, storage_path
from book_fixtures import duplicate_cover_epub, epub_bytes, pdf_bytes
from conftest import ORIGIN
from test_auth_catalog import client_for, login


async def upload(client, content, name="fixture.epub", csrf=None):
    if csrf is None:
        csrf = (await client.get("/api/v1/auth/me")).json()["csrf_token"]
    return await client.post("/api/v1/books", files={"file": (name, content, "application/octet-stream")}, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})


@pytest.mark.parametrize("kind", ["epub", "pdf"])
def test_upload_metadata_private_files_covers_and_restart(settings, kind):
    content = epub_bytes() if kind == "epub" else pdf_bytes()

    async def scenario():
        async with client_for(settings) as client:
            assert (await login(client)).status_code == 200
            # The signature, not the misleading extension or MIME type, determines format.
            response = await upload(client, content, name="../../wrong.txt")
            assert response.status_code == 201, response.text
            body = response.json()
            book = body["book"]
            assert book["format"] == kind and book["has_cover"] is True
            assert body["duplicate"] is False
            assert book["title"] == ("An EPUB fixture" if kind == "epub" else "A PDF fixture")
            assert book["authors"] == (["Test Author"] if kind == "epub" else ["PDF Test Author"])
            assert book["page_count"] == (None if kind == "epub" else 2)
            if kind == "epub":
                assert book["publisher"] == "Fixture Press" and book["description"] == "An original test book."
            cover_response = await client.get(f"/api/v1/books/{book['id']}/cover")
            assert cover_response.status_code == 200
            assert cover_response.headers["content-type"] == "image/jpeg"
            assert cover_response.headers["cache-control"] == "no-store"
            with Image.open(BytesIO(cover_response.content)) as cover:
                assert cover.format == "JPEG" and cover.width <= 512 and cover.height <= 768
            duplicate = await upload(client, content)
            assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
            assert duplicate.json()["book"]["id"] == book["id"]
            assert (await client.get("/api/v1/books")).json()["total"] == 1
            assert (await client.get(f"/api/v1/books/{book['id']}/content")).status_code == 404
            cookies = httpx.Cookies(client.cookies)
        migrate(settings)
        async with client_for(settings, cookies=cookies) as restarted:
            assert (await restarted.get("/api/v1/books")).json()["items"][0] == book
        engine = make_engine(settings)
        try:
            with Session(engine) as db:
                record = db.get(Book, book["id"])
                assert record.original_filename == "wrong.txt"
                assert storage_path(settings, record.storage_key).read_bytes() == content
                assert "storage_key" not in book
            assert audit_storage(settings, engine) == []
        finally:
            engine.dispose()
    asyncio.run(scenario())


def test_cover_and_upload_require_login_and_csrf(settings):
    async def scenario():
        async with client_for(settings) as client:
            assert (await client.post("/api/v1/books", files={"file": ("book.epub", epub_bytes())})).status_code == 401
            assert (await client.get("/api/v1/books/missing/cover")).status_code == 401
            assert (await client.get("/api/v1/upload-policy")).status_code == 401
            assert (await login(client)).status_code == 200
            assert (await upload(client, epub_bytes(), csrf="bad")).status_code == 403
            assert not (settings.data_dir / "staging").exists()
    asyncio.run(scenario())


def test_fallback_metadata_and_cover_placeholder(settings):
    content = epub_bytes(cover=False)
    with ZipFile(BytesIO(content)) as archive:
        package = archive.read("OEBPS/package.opf").replace(b"<dc:title>An EPUB fixture</dc:title>", b"").replace(b"<dc:creator>Test Author</dc:creator>", b"")
    content = epub_bytes(cover=False, changes={"OEBPS/package.opf": package})

    async def scenario():
        async with client_for(settings) as client:
            await login(client)
            response = await upload(client, content, name="My fallback.epub")
            assert response.status_code == 201, response.text
            result = response.json()
            assert result["book"]["title"] == "My fallback"
            assert result["book"]["authors"] == [] and result["book"]["has_cover"] is False
            assert result["warnings"]
            assert (await client.get(f"/api/v1/books/{result['book']['id']}/cover")).status_code == 404
    asyncio.run(scenario())


@pytest.mark.parametrize("content", [b"", b"not a book", b"%PDF-1.7\ninvalid", b"PK\x03\x04invalid", epub_bytes(extras={"../escape.txt": b"no"}), epub_bytes(changes={"OEBPS/chapter.xhtml": None})])
def test_rejected_uploads_leave_no_records_or_files(settings, content):
    async def scenario():
        async with client_for(settings) as client:
            await login(client)
            response = await upload(client, content)
            assert response.status_code in {415, 422}, response.text
            assert (await client.get("/api/v1/books")).json()["total"] == 0
            assert list((settings.data_dir / "staging").iterdir()) == []
            assert not (settings.data_dir / "books").exists()
    asyncio.run(scenario())


def test_file_limit_and_malformed_multipart(settings):
    small = settings.model_copy(update={"max_upload_bytes": 1024})

    async def scenario():
        async with client_for(small) as client:
            await login(client)
            assert (await client.get("/api/v1/upload-policy")).json()["max_bytes"] == 1024
            assert (await upload(client, b"x" * 1025)).status_code == 413
            csrf = (await client.get("/api/v1/auth/me")).json()["csrf_token"]
            headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
            response = await client.post("/api/v1/books", files=[("file", ("a.epub", b"a")), ("file", ("b.pdf", b"b"))], headers=headers)
            assert response.status_code == 400
            assert (await client.post("/api/v1/books", json={}, headers=headers)).status_code == 415
    asyncio.run(scenario())


def test_transport_limit_checks_chunked_body_without_content_length(settings):
    small = settings.model_copy(update={"max_upload_bytes": 1024})

    async def scenario():
        async with client_for(small) as client:
            await login(client)
            csrf = (await client.get("/api/v1/auth/me")).json()["csrf_token"]
            async def chunks():
                yield b'--fixture\r\nContent-Disposition: form-data; name="file"; filename="big.pdf"\r\n\r\n'
                for _ in range(80):
                    yield b"x" * 1024
                yield b"\r\n--fixture--\r\n"
            response = await client.post("/api/v1/books", content=chunks(), headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Content-Type": "multipart/form-data; boundary=fixture"})
            assert response.status_code == 413
            assert (await client.get("/api/v1/books")).json()["total"] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("extra", [
    {"C:/drive.txt": b"unsafe"},
    {"OEBPS\\backslash.txt": b"unsafe"},
    {"OEBPS/../traversal.txt": b"unsafe"},
    {"OEBPS/nul\x00file.txt": b"unsafe"},
    {"OEBPS/CHAPTER.XHTML": b"ambiguous"},
    {"bomb.txt": b"0" * (2 * 1024 * 1024)},
    {"META-INF/encryption.xml": b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#"><EncryptionMethod Algorithm="unsupported"/></EncryptedData></encryption>'},
])
def test_hostile_epub_archives_rejected(tmp_path, extra):
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes(extras=extra))
    with pytest.raises(InvalidDocument):
        inspect_document(source, tmp_path, "Fallback")


def test_epub_xml_entities_rejected(tmp_path):
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes(changes={"META-INF/container.xml": b'<!DOCTYPE container [<!ENTITY secret SYSTEM "file:///etc/passwd">]><container>&secret;</container>'}))
    with pytest.raises(InvalidDocument):
        inspect_document(source, tmp_path, "Fallback")


def test_epub_font_obfuscation_is_not_mistaken_for_drm(tmp_path):
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf").replace(b"</manifest>", b'<item id="font" href="fonts/sample.otf" media-type="font/otf"/></manifest>')
    source = tmp_path / "font-book.epub"
    source.write_bytes(epub_bytes(changes={"OEBPS/package.opf": package}, extras={
        "OEBPS/fonts/sample.otf": b"unused test font bytes",
        "META-INF/encryption.xml": b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#"><EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/><CipherData><CipherReference URI="OEBPS/fonts/sample.otf"/></CipherData></EncryptedData></encryption>',
    }))
    assert inspect_document(source, tmp_path, "Fallback")["format"] == "epub"


def test_unusable_epub_cover_uses_placeholder(tmp_path):
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes(changes={"OEBPS/cover.png": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'}))
    assert inspect_document(source, tmp_path, "Fallback")["has_cover"] is False
    assert not (tmp_path / "cover.jpg").exists()


def test_pdf_password_and_encryption_errors_are_rejected(tmp_path):
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    source = tmp_path / "book.pdf"
    source.write_bytes(pdf_bytes())
    with patch("pypdfium2.PdfDocument", side_effect=pdfium.PdfiumError("password", err_code=raw.FPDF_ERR_PASSWORD)):
        with pytest.raises(InvalidDocument, match="Encrypted"):
            inspect_document(source, tmp_path, "Fallback")
    with patch("pypdfium2.raw.FPDF_GetSecurityHandlerRevision", return_value=2):
        with pytest.raises(InvalidDocument, match="Encrypted"):
            inspect_document(source, tmp_path, "Fallback")


def test_only_one_upload_processes_at_a_time(settings):
    entered = threading.Event()
    release = threading.Event()
    original = ingest_book

    def blocked_ingest(*args):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args)

    async def scenario():
        async with client_for(settings) as client:
            auth = await login(client)
            csrf = auth.json()["csrf_token"]
            with patch("app.api.ingest_book", side_effect=blocked_ingest):
                first = asyncio.create_task(upload(client, epub_bytes(), csrf=csrf))
                try:
                    assert await asyncio.to_thread(entered.wait, 5)
                    assert (await upload(client, pdf_bytes(), name="book.pdf", csrf=csrf)).status_code == 503
                finally:
                    release.set()
                assert (await first).status_code == 201
    asyncio.run(scenario())


def test_epub_symlinks_rejected(tmp_path):
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes())
    with ZipFile(source, "a") as archive:
        link = ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "outside")
    with pytest.raises(InvalidDocument):
        inspect_document(source, tmp_path, "Fallback")


def test_database_failure_cleans_published_files(settings):
    engine = make_engine(settings)
    try:
        # Fail at commit after processing and moving the files into place.
        with patch("app.storage.Session.commit", side_effect=OperationalError("write failed", {}, Exception("simulated"))):
            with pytest.raises(StorageFailure):
                ingest_book(BytesIO(epub_bytes()), "book.epub", 1, settings, engine)
        assert list((settings.data_dir / "staging").iterdir()) == []
        assert list((settings.data_dir / "books").iterdir()) == []
        with Session(engine) as db:
            assert db.scalar(select(Book)) is None
    finally:
        engine.dispose()


def test_worker_timeout_terminates_owned_process(tmp_path):
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes())
    # Zero join time forces timeout without making tests wait for a slow parser.
    with pytest.raises(InvalidDocument, match="timed out"):
        inspect_in_process(source, tmp_path, "Fallback", 0)


def test_commit_acknowledgement_failure_preserves_referenced_files(settings):
    engine = make_engine(settings)
    content = epub_bytes()
    original_commit = Session.commit

    def committed_then_failed(db):
        original_commit(db)
        raise OperationalError("acknowledgement lost", {}, Exception("simulated"))

    try:
        with patch("app.storage.Session.commit", new=committed_then_failed):
            with pytest.raises(StorageFailure):
                ingest_book(BytesIO(content), "book.epub", 1, settings, engine)
        # The record is already committed. A retry must keep the original intact.
        retry = ingest_book(BytesIO(content), "book.epub", 1, settings, engine)
        assert retry.duplicate is True
        assert storage_path(settings, retry.book.storage_key).read_bytes() == content
        assert audit_storage(settings, engine) == []
    finally:
        engine.dispose()


def test_storage_audit_reports_leftovers_without_deletion(settings):
    staging = settings.data_dir / "staging" / "interrupted-upload"
    staging.mkdir(parents=True)
    (staging / "source.bin").write_bytes(b"original")
    orphan = settings.data_dir / "books" / "orphan"
    orphan.mkdir(parents=True)
    engine = make_engine(settings)
    try:
        issues = audit_storage(settings, engine)
        assert len(issues) == 2 and staging.exists() and orphan.exists()
        for key in ("../outside", "C:/outside", "books/../../outside", "books\\outside", settings.data_dir.as_posix() + "/books/file"):
            with pytest.raises(StorageFailure):
                storage_path(settings, key)
    finally:
        engine.dispose()


def test_duplicate_nonstructural_cover_ids_upload_with_warning(settings):
    content = duplicate_cover_epub()

    async def scenario():
        async with client_for(settings) as client:
            await login(client)
            response = await upload(client, content)
            assert response.status_code == 201, response.text
            result = response.json()
            assert result["book"]["has_cover"] is True
            assert len(result["warnings"]) == 1 and "duplicate cover identifiers" in result["warnings"][0]
            engine = make_engine(settings)
            try:
                with Session(engine) as db:
                    book = db.get(Book, result["book"]["id"])
                    assert storage_path(settings, book.storage_key).read_bytes() == content
            finally:
                engine.dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("options", [{"structural_reference": True}, {"second_type": "application/xhtml+xml"}])
def test_duplicate_cover_ids_reject_ambiguous_structural_resources(tmp_path, options):
    source = tmp_path / "book.epub"
    source.write_bytes(duplicate_cover_epub(**options))
    with pytest.raises(InvalidDocument, match="duplicate identifier"):
        inspect_document(source, tmp_path, "Fallback")


@pytest.mark.parametrize("replacement, message", [
    (b'<item href="chapter.xhtml"', "missing its identifier"),
    (b'<item id="cover" href="chapter.xhtml"', "duplicate identifier"),
])
def test_missing_and_duplicate_chapter_ids_remain_rejected(tmp_path, replacement, message):
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf").replace(b'<item id="chapter" href="chapter.xhtml"', replacement)
    source = tmp_path / "book.epub"
    source.write_bytes(epub_bytes(changes={"OEBPS/package.opf": package}))
    with pytest.raises(InvalidDocument, match=message):
        inspect_document(source, tmp_path, "Fallback")
