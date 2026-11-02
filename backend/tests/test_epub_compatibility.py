import base64
import hashlib
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pytest

from app.documents import InvalidDocument
from app.epub_artifact import build_reading_copy, XHTML
from book_fixtures import epub_bytes


def prepare(tmp_path, *, additions="", spine='<itemref idref="chapter"/>', files=None, chapter=None):
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf")
    package = package.replace(b"</manifest>", additions.encode() + b"</manifest>")
    package = package.replace(b'<itemref idref="chapter"/>', spine.encode())
    changes = {"OEBPS/package.opf": package}
    if chapter is not None:
        changes["OEBPS/chapter.xhtml"] = chapter
    content = epub_bytes(changes=changes, extras=files)
    source = tmp_path / "original.epub"
    source.write_bytes(content)
    notices = build_reading_copy(source, tmp_path, hashlib.sha256(content).hexdigest())
    assert source.read_bytes() == content
    return ZipFile(tmp_path / "reader.epub"), notices


def test_svg_spine_and_safe_publisher_css(tmp_path):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><script>alert(1)</script><text x="5" y="20">Vector title</text><image href="cover.png"/><image href="https://invalid.example/leak"/></svg>'
    chapter = b'<html><head><link rel="stylesheet" href="style.css"/></head><body><p class="indent" style="font-weight:bold;background-image:url(https://invalid.example)">Styled text</p></body></html>'
    archive, _ = prepare(tmp_path, additions='<item id="vector" href="title.svg" media-type="image/svg+xml"/><item id="css" href="style.css" media-type="text/css"/>', spine='<itemref idref="vector"/><itemref idref="chapter"/>', chapter=chapter, files={"OEBPS/title.svg": svg, "OEBPS/style.css": b'@import "https://invalid.example";.indent{text-indent:2em;color:rgb(20,30,40);background:url(https://invalid.example)}'})
    with archive:
        text = archive.read("book/text/chapter-0000.xhtml").decode()
        assert "text-indent:2em" in text and 'class="indent"' in text and "font-weight:bold" in text
        assert "invalid.example" not in text
        vector = ET.fromstring(archive.read("book/text/chapter-0001.xhtml"))
        src = vector.find(f".//{{{XHTML}}}img").get("src")
        safe = base64.b64decode(src.split(",", 1)[1])
        assert b"Vector title" in safe and b"data:image/jpeg" in safe
        assert b"script" not in safe and b"invalid.example" not in safe


def test_fallback_and_explicit_unsupported_placeholder(tmp_path, caplog):
    archive, notices = prepare(tmp_path, additions='<item id="foreign" href="chart.bin" media-type="application/x-example" fallback="chapter"/><item id="unknown" href="unknown.bin" media-type="application/x-unknown"/>', spine='<itemref idref="foreign"/><itemref idref="unknown"/>', files={"OEBPS/chart.bin": b'foreign', "OEBPS/unknown.bin": b'unknown'})
    with archive:
        assert b"Unsupported reading resource" in archive.read("book/text/chapter-0001.xhtml")
        assert b"Fixture chapter" in archive.read("book/text/chapter-0000.xhtml")
    assert any("fallback" in notice for notice in notices)
    assert "declared=" in caplog.text and "detected=" in caplog.text and "unknown.bin" in caplog.text


@pytest.mark.parametrize("fallback", ["foreign", "missing"])
def test_invalid_fallback_chain_has_specific_error(tmp_path, fallback):
    with pytest.raises(InvalidDocument, match="fallback"):
        prepare(tmp_path, additions=f'<item id="foreign" href="chart.bin" media-type="application/x-example" fallback="{fallback}"/>', spine='<itemref idref="foreign"/>', files={"OEBPS/chart.bin": b'foreign'})


def test_encoded_paths_html_and_nested_navigation(tmp_path):
    archive, _ = prepare(tmp_path, additions='<item id="special" href="Text/Part%20%26%20One.html" media-type="text/html"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>', spine='<itemref idref="chapter"/><itemref idref="special"/><itemref idref="nav"/>', files={"OEBPS/Text/Part & One.html": b'<!doctype html><html><body><h1 id="a:b">HTML chapter</h1></body></html>', "OEBPS/nav.xhtml": b'<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">Parent</a><ol><li><a href="Text/Part%20%26%20One.html#a%3Ab">Child</a></li></ol></li></ol></nav></body></html>'})
    with archive:
        nav = ET.fromstring(archive.read("book/nav.xhtml"))
        assert nav.find(f".//{{{XHTML}}}li/{{{XHTML}}}ol/{{{XHTML}}}li/{{{XHTML}}}a").text == "Child"
        assert b"#a%3Ab" in archive.read("book/nav.xhtml")


def test_legacy_doctype_is_permitted_without_external_resolution(tmp_path):
    from app.documents import read_xml
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("toc.ncx", b'<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "https://invalid.example/ncx.dtd"><ncx/>')
    with ZipFile(buffer) as archive:
        assert read_xml(archive, "toc.ncx").tag == "ncx"


def test_text_pdf_remains_importable(tmp_path):
    from app.documents import inspect_document
    from book_fixtures import text_pdf_bytes
    import pypdfium2 as pdfium
    source = tmp_path / "text.pdf"
    source.write_bytes(text_pdf_bytes())
    metadata = inspect_document(source, tmp_path, "Text fixture")
    assert metadata["format"] == "pdf" and metadata["page_count"] == 1 and metadata["has_cover"]
    with pdfium.PdfDocument(source) as document:
        page = document[0]
        try:
            text = page.get_textpage()
            try:
                assert "Original text PDF fixture" in text.get_text_range()
            finally:
                text.close()
        finally:
            page.close()
