"""Bounded document inspection. Runs only inside an isolated worker process.

Original publications are never extracted to a public directory or executed.
This is ingestion validation, not a complete EPUBCheck/PDF conformance validator.
"""

from html.parser import HTMLParser
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
import posixpath
import stat
from urllib.parse import unquote, urlsplit
import warnings
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED, ZIP_STORED

from defusedxml import ElementTree as XML
from defusedxml.common import DefusedXmlException
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 20_000_000
MAX_ENTRIES = 5000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_COVER_BYTES = 20 * 1024 * 1024
OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
OCF = "{urn:oasis:names:tc:opendocument:xmlns:container}"
ENC = "{http://www.w3.org/2001/04/xmlenc#}"


class InvalidDocument(Exception):
    def __init__(self, message: str, code: str = "invalid_document"):
        super().__init__(message)
        self.code = code


def clean_text(value: str | None, maximum: int = 500) -> str:
    value = value or ""
    return " ".join("".join(c for c in value if c.isprintable() or c.isspace()).split())[:maximum]


class PlainDescription(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, _attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def description_text(value: str) -> str | None:
    parser = PlainDescription()
    parser.feed(value[:MAX_XML_BYTES])
    return clean_text(" ".join(parser.parts), 20_000) or None


def save_cover(image: Image.Image, output: Path) -> None:
    image = ImageOps.exif_transpose(image)
    image.thumbnail((512, 768))
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    # Re-encoding strips original metadata and never returns active SVG content.
    background.convert("RGB").save(output, "JPEG", quality=85)


def raster_cover(data: bytes, output: Path) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                    return False
                image.load()
                save_cover(image, output)
        return True
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        return False


def safe_member(name: str) -> str:
    trimmed = name.removesuffix("/")
    parts = trimmed.split("/")
    if (not trimmed or "\\" in name or ":" in name or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(part in {"", ".", ".."} for part in parts)
            or PurePosixPath(trimmed).is_absolute()):
        raise InvalidDocument("The EPUB contains an unsafe archive path.")
    return trimmed


def referenced_member(base: str, href: str) -> str:
    uri = urlsplit(href)
    decoded = unquote(uri.path)
    if uri.scheme or uri.netloc or uri.query or decoded.startswith("/") or "\\" in decoded:
        raise InvalidDocument("The EPUB references an unsupported external or unsafe resource.")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
    return safe_member(resolved)


def read_xml(archive: ZipFile, name: str):
    if archive.getinfo(name).file_size > MAX_XML_BYTES:
        raise InvalidDocument("An EPUB XML document exceeds the processing limit.")
    return XML.fromstring(archive.read(name), forbid_dtd=True)


def inspect_epub(source: Path, output: Path, fallback: str) -> dict:
    with ZipFile(source) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ENTRIES:
            raise InvalidDocument("The EPUB has too many archive entries or is empty.")
        names: set[str] = set()
        expanded = 0
        for entry in entries:
            # ZipInfo.filename is normalized on Windows (and truncated at NUL).
            # Validate the original central-directory spelling first.
            canonical = safe_member(entry.orig_filename).casefold()
            if canonical in names:
                raise InvalidDocument("The EPUB has ambiguous duplicate archive entries.")
            names.add(canonical)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                raise InvalidDocument("The EPUB contains unsupported special files.")
            if entry.flag_bits & 1:
                raise InvalidDocument("Encrypted EPUB archives are not supported.", "encrypted_document")
            if entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise InvalidDocument("The EPUB uses an unsupported compression method.")
            expanded += entry.file_size
            if (entry.file_size > MAX_MEMBER_BYTES or expanded > MAX_EXPANDED_BYTES
                    or entry.file_size > max(entry.compress_size, 1) * 1000):
                raise InvalidDocument("The EPUB exceeds archive expansion limits.")
        if archive.getinfo("mimetype").file_size != 20 or archive.read("mimetype") != b"application/epub+zip":
            raise InvalidDocument("This ZIP file is not an EPUB publication.")
        if "META-INF/rights.xml" in archive.namelist():
            raise InvalidDocument("DRM-protected EPUBs are not supported.", "encrypted_document")

        # Stream every member to validate actual expansion and CRC, without extraction.
        actual_total = 0
        for entry in entries:
            count = 0
            with archive.open(entry) as member:
                while chunk := member.read(1024 * 1024):
                    count += len(chunk)
                    actual_total += len(chunk)
                    if count > MAX_MEMBER_BYTES or actual_total > MAX_EXPANDED_BYTES:
                        raise InvalidDocument("The EPUB exceeds archive expansion limits.")

        container = read_xml(archive, "META-INF/container.xml")
        rootfiles = container.findall(f"{OCF}rootfiles/{OCF}rootfile")
        rootfile = next((item for item in rootfiles if item.get("media-type") == "application/oebps-package+xml"), None)
        if rootfile is None:
            raise InvalidDocument("The EPUB has no supported package document.")
        package_name = referenced_member("", rootfile.get("full-path", ""))
        package = read_xml(archive, package_name)
        if package.tag != OPF + "package" or package.get("version", "").split(".")[0] not in {"2", "3"}:
            raise InvalidDocument("Only EPUB 2 and EPUB 3 publications are supported.")
        metadata = package.find(OPF + "metadata")
        manifest = package.find(OPF + "manifest")
        spine = package.find(OPF + "spine")
        if metadata is None or manifest is None or spine is None or not len(spine):
            raise InvalidDocument("The EPUB is missing metadata, a manifest, or reading order.")
        items = {}
        for item in manifest.findall(OPF + "item"):
            identifier = item.get("id")
            if not identifier or identifier in items:
                raise InvalidDocument("The EPUB manifest contains missing or duplicate identifiers.")
            member_name = referenced_member(package_name, item.get("href", ""))
            if member_name not in archive.namelist():
                raise InvalidDocument("The EPUB references a missing resource.")
            items[identifier] = (member_name, item)
        for itemref in spine.findall(OPF + "itemref"):
            if itemref.get("idref") not in items:
                raise InvalidDocument("The EPUB reading order references a missing resource.")

        if "META-INF/encryption.xml" in archive.namelist():
            encrypted = read_xml(archive, "META-INF/encryption.xml")
            font_methods = {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}
            for record in encrypted.findall(".//" + ENC + "EncryptedData"):
                method = record.find(ENC + "EncryptionMethod")
                target = record.find(f"{ENC}CipherData/{ENC}CipherReference")
                if method is None or method.get("Algorithm") not in font_methods or target is None:
                    raise InvalidDocument("DRM-protected EPUBs are not supported.", "encrypted_document")
                name = referenced_member("", target.get("URI", ""))
                font_types = {"application/vnd.ms-opentype", "application/font-sfnt", "application/font-woff", "application/x-font-ttf", "application/x-font-opentype"}
                if not any(path == name and (item.get("media-type", "").startswith("font/") or item.get("media-type") in font_types) for path, item in items.values()):
                    raise InvalidDocument("The EPUB has unsupported encrypted resources.", "encrypted_document")

        def values(tag: str) -> list[str]:
            return [text for element in metadata.findall(DC + tag) if (text := clean_text(" ".join(element.itertext())))]

        cover_id = next((item.get("content") for item in metadata.findall(OPF + "meta") if item.get("name") == "cover"), None)
        cover = next((pair for pair in items.values() if "cover-image" in pair[1].get("properties", "").split()), items.get(cover_id))
        has_cover = False
        if cover is not None and archive.getinfo(cover[0]).file_size <= MAX_COVER_BYTES:
            has_cover = raster_cover(archive.read(cover[0]), output / "cover.jpg")
        raw_description = " ".join(" ".join(item.itertext()) for item in metadata.findall(DC + "description"))
        return dict(
            format="epub", title=(values("title") or [fallback])[0], authors=values("creator")[:100],
            publisher=next(iter(values("publisher")), None), description=description_text(raw_description),
            language=next(iter(values("language")), "")[:64] or None,
            page_count=None, has_cover=has_cover,
        )


def inspect_pdf(source: Path, output: Path, fallback: str) -> dict:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    try:
        document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as error:
        if error.err_code == raw.FPDF_ERR_PASSWORD:
            raise InvalidDocument("Encrypted PDFs are not supported.", "encrypted_document") from error
        raise InvalidDocument("The PDF could not be opened.") from error
    with document:
        if raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
            raise InvalidDocument("Encrypted PDFs are not supported.", "encrypted_document")
        count = len(document)
        if not 1 <= count <= 20_000:
            raise InvalidDocument("The PDF has no pages or exceeds the page limit.")
        metadata = document.get_metadata_dict()
        has_cover = False
        # Failure to create a thumbnail does not discard an otherwise readable PDF.
        try:
            page = document[0]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(size) and size > 0 for size in (width, height)):
                    raise ValueError("Invalid page dimensions")
                bitmap = page.render(scale=min(512 / width, 768 / height), may_draw_forms=False)
                try:
                    save_cover(bitmap.to_pil(), output / "cover.jpg")
                    has_cover = True
                finally:
                    bitmap.close()
            finally:
                page.close()
        except (pdfium.PdfiumError, OSError, ValueError, OverflowError):
            pass
        return dict(
            format="pdf", title=clean_text(metadata.get("Title")) or fallback,
            authors=[author] if (author := clean_text(metadata.get("Author"))) else [],
            publisher=None, description=clean_text(metadata.get("Subject"), 20_000) or None,
            language=None, page_count=count, has_cover=has_cover,
        )


def inspect_document(source: Path, output: Path, fallback: str) -> dict:
    with source.open("rb") as stream:
        signature = stream.read(8)
    if signature.startswith(b"%PDF-"):
        return inspect_pdf(source, output, fallback)
    if signature.startswith(b"PK\x03\x04"):
        try:
            return inspect_epub(source, output, fallback)
        except (BadZipFile, KeyError, DefusedXmlException, XML.ParseError, UnicodeError, ValueError) as error:
            raise InvalidDocument("The EPUB archive or publication XML is invalid.") from error
    raise InvalidDocument("Upload a DRM-free EPUB or PDF document.", "unsupported_format")


def process_document(source: str, directory: str, fallback: str) -> None:
    """Multiprocessing entry point. Return only bounded JSON and a raster cover."""
    output = Path(directory)
    try:
        metadata = inspect_document(Path(source), output, fallback)
        result = {"ok": True, "metadata": metadata}
    except InvalidDocument as error:
        result = {"ok": False, "code": error.code, "message": str(error)}
    except Exception:
        # Parser internals and document paths never become client-facing errors.
        result = {"ok": False, "code": "invalid_document", "message": "The document could not be processed safely."}
    (output / "result.json").write_text(json.dumps(result), encoding="utf-8")
