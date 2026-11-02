"""Small, original fixtures generated locally; no copyrighted books or downloads."""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image


def epub_bytes(*, title="An EPUB fixture", cover=True, changes=None, extras=None):
    image = BytesIO()
    Image.new("RGB", (120, 180), "#425e4a").save(image, "PNG")
    entries = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": b'''<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''',
        "OEBPS/package.opf": f'''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">urn:uuid:original-test-fixture</dc:identifier><dc:title>{escape(title)}</dc:title><dc:creator>Test Author</dc:creator><dc:publisher>Fixture Press</dc:publisher><dc:language>en</dc:language><dc:description>&lt;p&gt;An original test book.&lt;/p&gt;</dc:description></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>{'<item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>' if cover else ''}</manifest><spine><itemref idref="chapter"/></spine></package>'''.encode(),
        "OEBPS/chapter.xhtml": b'''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Fixture</title></head><body><h1>Fixture chapter</h1><p>Original content for automated testing.</p></body></html>''',
    }
    if cover:
        entries["OEBPS/cover.png"] = image.getvalue()
    entries.update(changes or {})
    entries.update(extras or {})
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            if content is not None:
                info = ZipInfo("fixture")
                # Preserve hostile names exactly, even on Windows where the
                # ZipInfo constructor otherwise normalizes backslashes.
                info.filename = name
                archive.writestr(info, content, compress_type=0 if name == "mimetype" else ZIP_DEFLATED)
    return buffer.getvalue()


def pdf_bytes(*, title="A PDF fixture", author="PDF Test Author"):
    buffer = BytesIO()
    first = Image.new("RGB", (160, 240), "#eee0cb")
    second = Image.new("RGB", (160, 240), "#d8e1d2")
    first.save(buffer, "PDF", save_all=True, append_images=[second], title=title, author=author, subject="An image-only fixture; OCR is not required.")
    return buffer.getvalue()


def duplicate_cover_epub(*, structural_reference=False, second_type="image/jpeg"):
    """Original regression fixture for EPUB 2 exports with reused cover IDs."""
    with ZipFile(BytesIO(epub_bytes())) as archive:
        package = archive.read("OEBPS/package.opf")
        cover = archive.read("OEBPS/cover.png")
    package = package.replace(b'version="3.0"', b'version="2.0"')
    package = package.replace(b"</metadata>", b'<meta name="cover" content="cover"/></metadata>')
    package = package.replace(b'properties="cover-image"', b'')
    duplicate = f'<item id="cover" href="second-cover.jpg" media-type="{second_type}"/>'.encode()
    package = package.replace(b"</manifest>", duplicate + b"</manifest>")
    if structural_reference:
        package = package.replace(b"</spine>", b'<itemref idref="cover"/></spine>')
    return epub_bytes(changes={"OEBPS/package.opf": package}, extras={"OEBPS/second-cover.jpg": cover})
