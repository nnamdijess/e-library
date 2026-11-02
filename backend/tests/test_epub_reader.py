import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import httpx
import pytest
from sqlalchemy.orm import Session

from app.database import make_engine
from app.documents import InvalidDocument
from app.epub_artifact import build_reading_copy, XHTML
from app.models import Book
from app.storage import storage_path
from book_fixtures import epub_bytes, pdf_bytes
from test_auth_catalog import client_for, login
from test_ingestion import upload


def reading_fixture(*, epub2=False, hostile=False):
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf")
    package = package.replace(b"<dc:title>An EPUB fixture</dc:title>", b"<dc:title>Reader fixture</dc:title>")
    extra = '<item id="second" href="second.xhtml" media-type="application/xhtml+xml"/>'
    if epub2:
        extra += '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        package = package.replace(b'version="3.0"', b'version="2.0"').replace(b"<spine>", b'<spine toc="ncx">')
    else:
        extra += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    package = package.replace(b"</manifest>", extra.encode() + b"</manifest>").replace(b"</spine>", b'<itemref idref="second"/></spine>')
    paragraphs = ''.join(f'<p id="p-{index}">Original fixture paragraph {index}. A patient reader turns the page and keeps exploring this small test library. The garden is quiet and the morning light falls across the desk.</p>' for index in range(80))
    attacks = '''<script>window.readerAttack=1</script><style>body{background:url(https://invalid.example/leak)}</style><form action="https://invalid.example"><input name="secret"/></form><iframe src="https://invalid.example"></iframe><svg xmlns="http://www.w3.org/2000/svg"><script>window.svgAttack=1</script></svg><img src="https://invalid.example/pixel" onerror="alert(1)"/><a href="javascript:alert(1)">Bad link</a>''' if hostile else ''
    first = f'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>First chapter</title></head><body onload="alert(1)"><h1>First chapter</h1><a href="second.xhtml#destination">Internal chapter link</a><a href="#p-1">Local note</a><img src="cover.png" alt="Fixture illustration"/>{attacks}{paragraphs}</body></html>'''.encode()
    second = b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Second chapter</title></head><body><h1 id="destination">Second chapter</h1><p>The second chapter is ready.</p></body></html>'
    nav = b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">First chapter</a></li><li><a href="second.xhtml#destination">Second chapter</a></li><li><a href="https://invalid.example">External</a></li></ol></nav></body></html>'
    ncx = b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="one"><navLabel><text>First chapter</text></navLabel><content src="chapter.xhtml"/></navPoint><navPoint id="two"><navLabel><text>Second chapter</text></navLabel><content src="second.xhtml#destination"/></navPoint></navMap></ncx>'
    return epub_bytes(title="Reader fixture", changes={"OEBPS/package.opf": package, "OEBPS/chapter.xhtml": first}, extras={"OEBPS/second.xhtml": second, "OEBPS/nav.xhtml": nav, "OEBPS/toc.ncx": ncx})


@pytest.mark.parametrize("epub2", [False, True])
def test_reading_copy_sanitizes_content_preserves_links_and_toc(tmp_path, epub2):
    content = reading_fixture(epub2=epub2, hostile=True)
    source = tmp_path / "original.epub"
    source.write_bytes(content)
    build_reading_copy(source, tmp_path, hashlib.sha256(content).hexdigest())
    assert source.read_bytes() == content
    with ZipFile(tmp_path / "reader.epub") as archive:
        chapter = archive.read("book/text/chapter-0000.xhtml")
        text = chapter.decode()
        assert "Original fixture paragraph 79" in text
        assert "invalid.example" not in text and "readerAttack" not in text and "svgAttack" not in text
        root = ET.fromstring(chapter)
        assert not any(node.tag.rsplit("}", 1)[-1] in {"script", "form", "iframe", "svg", "object"} for node in root.iter())
        assert all(not attr.startswith("on") for node in root.iter() for attr in node.attrib)
        anchors = list(root.iter(f"{{{XHTML}}}a"))
        assert anchors[0].get("href") == "chapter-0001.xhtml#destination"
        assert anchors[1].get("href") == "chapter-0000.xhtml#p-1"
        assert any(node.get("http-equiv") == "Content-Security-Policy" for node in root.iter())
        images = list(root.iter(f"{{{XHTML}}}img"))
        assert images[0].get("src").startswith("../images/")
        nav = ET.fromstring(archive.read("book/nav.xhtml"))
        assert [node.text for node in nav.iter(f"{{{XHTML}}}a")] == ["First chapter", "Second chapter"]
        assert all(name.endswith((".xhtml", ".jpg", ".opf", ".xml")) or name == "mimetype" for name in archive.namelist())


def test_reading_copy_refuses_changed_original_and_fixed_layout(tmp_path):
    source = tmp_path / "original.epub"
    source.write_bytes(epub_bytes())
    with pytest.raises(InvalidDocument, match="integrity"):
        build_reading_copy(source, tmp_path, "0" * 64)
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf").replace(b"</metadata>", b'<meta property="rendition:layout">pre-paginated</meta></metadata>')
    content = epub_bytes(changes={"OEBPS/package.opf": package})
    source.write_bytes(content)
    with pytest.raises(InvalidDocument, match="fixed-layout"):
        build_reading_copy(source, tmp_path, hashlib.sha256(content).hexdigest())


def test_reader_routes_authenticated_cached_and_versioned(settings):
    async def scenario():
        async with client_for(settings) as client:
            assert (await client.get("/api/v1/books/missing/epub")).status_code == 401
            assert (await client.get("/api/v1/books/missing/epub/1/content")).status_code == 401
            await login(client)
            uploaded = (await upload(client, reading_fixture(), name="reader.epub")).json()["book"]
            prefix = f"/api/v1/books/{uploaded['id']}/epub"
            response = await client.get(prefix)
            assert response.status_code == 200, response.text
            info = response.json()
            assert info["artifact_version"] == 1
            reading = await client.get(info["content_url"])
            assert reading.status_code == 200 and reading.headers["cache-control"] == "no-store"
            with ZipFile(BytesIO(reading.content)) as archive:
                assert b"First chapter" in archive.read("book/text/chapter-0000.xhtml")
            assert (await client.get(prefix + "/999/content")).status_code == 404
            assert (await client.get(prefix)).json() == info
            cookies = httpx.Cookies(client.cookies)
            engine = make_engine(settings)
            try:
                with Session(engine) as db:
                    book = db.get(Book, uploaded["id"])
                    original = storage_path(settings, book.storage_key)
                    artifact = original.parent / "reader-v1.epub"
                    timestamp = artifact.stat().st_mtime_ns
            finally:
                engine.dispose()
        async with client_for(settings, cookies=cookies) as restarted:
            assert (await restarted.get(info["content_url"])).content == reading.content
            assert artifact.stat().st_mtime_ns == timestamp
            pdf = (await upload(restarted, pdf_bytes(), name="book.pdf")).json()["book"]
            assert (await restarted.get(f"/api/v1/books/{pdf['id']}/epub")).status_code == 409
        assert list((settings.data_dir / "staging").iterdir()) == []
    asyncio.run(scenario())


def test_reading_document_tree_is_reproducible(tmp_path):
    content = reading_fixture()
    source = tmp_path / "original.epub"
    source.write_bytes(content)
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for destination in (first, second):
        build_reading_copy(source, destination, hashlib.sha256(content).hexdigest())
    with ZipFile(first / "reader.epub") as one, ZipFile(second / "reader.epub") as two:
        assert one.read("book/text/chapter-0000.xhtml") == two.read("book/text/chapter-0000.xhtml")
        assert one.read("book/nav.xhtml") == two.read("book/nav.xhtml")
