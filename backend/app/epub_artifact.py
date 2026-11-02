"""Version 1 reading copy: semantic XHTML, local JPEGs, and controlled typography.

Never change this output algorithm in place once CFIs are persisted: a changed
document tree needs a new artifact version and explicit anchor handling.
"""

import hashlib
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import posixpath
from urllib.parse import quote, unquote, urlsplit
import warnings
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
from xml.etree import ElementTree as ET

import html5lib
import nh3
from PIL import Image, ImageOps

from app.documents import DC, OCF, OPF, MAX_XML_BYTES, MAX_COVER_BYTES, InvalidDocument, clean_text, inspect_epub, read_xml, referenced_member

ARTIFACT_VERSION = 1
XHTML = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
ET.register_namespace("", XHTML)
MAX_OUTPUT = 64 * 1024 * 1024
MAX_PAGES = 2000
CSP = "default-src 'none'; script-src 'none'; img-src blob: data:; style-src 'unsafe-inline'; font-src 'none'; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"
READER_CSS = """
html { color: #282b26; background: #faf8f2; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 19px; line-height: 1.65; overflow-wrap: break-word; }
p { margin: 0 0 1em; } h1,h2,h3 { line-height: 1.25; break-after: avoid; }
img { max-width: 100%; max-height: 75vh; object-fit: contain; }
pre { white-space: pre-wrap; } table { max-width: 100%; border-collapse: collapse; }
td,th { padding: .25em; border: 1px solid #ccc; } a { color: #315d43; }
blockquote { margin: 1em 1.25em; } .reader-image { text-align: center; }
"""
TAGS = {
    "a", "abbr", "b", "bdi", "bdo", "blockquote", "br", "caption", "cite", "code", "col", "colgroup",
    "dd", "del", "dfn", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "rp", "rt", "ruby", "s", "samp",
    "section", "small", "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var",
}


def xhtml_document(title: str, body, *, navigation=False) -> bytes:
    root = ET.Element(f"{{{XHTML}}}html", {"lang": "en"})
    head = ET.SubElement(root, f"{{{XHTML}}}head")
    ET.SubElement(head, f"{{{XHTML}}}meta", {"http-equiv": "Content-Security-Policy", "content": CSP})
    ET.SubElement(head, f"{{{XHTML}}}title").text = title
    ET.SubElement(head, f"{{{XHTML}}}style").text = READER_CSS
    root.append(body)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def target_href(base: str, value: str, pages: dict[str, str]) -> str | None:
    try:
        parsed = urlsplit(value)
        target = base if not parsed.path and not parsed.scheme and not parsed.netloc and not parsed.query else referenced_member(base, value)
    except (InvalidDocument, ValueError):
        return None
    if target not in pages:
        return None
    fragment = "#" + quote(unquote(parsed.fragment), safe="-._~") if parsed.fragment else ""
    return pages[target] + fragment


def sanitized_chapter(data: bytes, source_name: str, output_name: str, pages: dict, images: dict, title: str) -> bytes:
    # nh3's HTML5 parser does not fetch external DTDs. html5lib's byte parser
    # handles BOMs/named HTML entities, then serialization creates valid XHTML.
    parsed = html5lib.parse(data, override_encoding="utf-8")
    source_body = parsed.find(f"{{{XHTML}}}body")
    # Normalize namespace spellings before the HTML sanitizer, so SVG/script
    # nodes cannot hide behind serializer-generated prefixes such as ns1:svg.
    for node in source_body.iter():
        if isinstance(node.tag, str):
            node.tag = node.tag.rsplit("}", 1)[-1]
    body_html = ET.tostring(source_body, encoding="unicode", method="html")

    def filter_attribute(tag: str, attribute: str, value: str):
        if attribute == "href":
            target = target_href(source_name, value, pages)
            if target is None:
                return None
            path, marker, fragment = target.partition("#")
            return posixpath.relpath(path, posixpath.dirname(output_name)) + (marker + fragment if marker else "")
        if attribute == "src":
            try:
                target = referenced_member(source_name, value)
            except (InvalidDocument, ValueError):
                return None
            return posixpath.relpath(images[target], posixpath.dirname(output_name)) if target in images else None
        if attribute in {"colspan", "rowspan", "start", "value"}:
            return value if value.isdigit() and 0 < int(value) <= 1000 else None
        return value[:2000]

    cleaned = nh3.clean(
        body_html, tags=TAGS,
        clean_content_tags={"script", "style", "head", "iframe", "object", "embed", "svg", "math", "form", "template", "noscript"},
        attributes={"*": {"id", "title", "lang", "dir"}, "a": {"href"}, "img": {"src", "alt"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan", "scope"}, "ol": {"start"}, "li": {"value"}},
        attribute_filter=filter_attribute, url_schemes=set(), link_rel=None, strip_comments=True,
    )
    fragment = html5lib.parseFragment(cleaned)
    body = ET.Element(f"{{{XHTML}}}body")
    body.text = fragment.text
    body.extend(list(fragment))
    return xhtml_document(title, body)


def jpeg_image(data: bytes) -> bytes | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG", "GIF", "WEBP"}:
                    return None
                original.load()
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1600, 1600))
                rgba = image.convert("RGBA")
                white = Image.new("RGBA", rgba.size, "white")
                white.alpha_composite(rgba)
                result = BytesIO()
                white.convert("RGB").save(result, "JPEG", quality=88)
                return result.getvalue()
    except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        return None


def table_of_contents(archive, package, package_name, manifest, pages, page_titles, spine_paths):
    entries = []
    nav_item = next((item for item in manifest if "nav" in item.get("properties", "").split()), None)
    if nav_item is not None:
        name = referenced_member(package_name, nav_item.get("href", ""))
        if archive.getinfo(name).file_size > MAX_XML_BYTES:
            raise InvalidDocument("The EPUB table of contents exceeds the processing limit.")
        nav = html5lib.parse(archive.read(name), override_encoding="utf-8")
        toc = next((node for node in nav.iter(f"{{{XHTML}}}nav") if "toc" in (node.get("epub:type", "") + " " + node.get(f"{{{EPUB_NS}}}type", "")).split()), None)
        if toc is not None:
            for anchor in toc.iter(f"{{{XHTML}}}a"):
                target = target_href(name, anchor.get("href", ""), pages)
                if target:
                    entries.append((clean_text(" ".join(anchor.itertext())) or "Chapter", target))
    if not entries:
        ncx_id = package.find(OPF + "spine").get("toc")
        ncx_item = next((item for item in manifest if item.get("id") == ncx_id and item.get("media-type") == "application/x-dtbncx+xml"), None)
        if ncx_item is not None:
            name = referenced_member(package_name, ncx_item.get("href", ""))
            ncx = read_xml(archive, name)
            ncx_ns = "{http://www.daisy.org/z3986/2005/ncx/}"
            for point in ncx.iter(ncx_ns + "navPoint"):
                content = point.find(ncx_ns + "content")
                label = point.find(ncx_ns + "navLabel/" + ncx_ns + "text")
                target = target_href(name, content.get("src", ""), pages) if content is not None else None
                if target:
                    entries.append((clean_text(" ".join(label.itertext())) if label is not None else "Chapter", target))
    if not entries:
        entries = [(page_titles[path], pages[path]) for path in spine_paths]
    return entries[:MAX_PAGES]


def build_reading_copy(source: Path, output: Path, expected_hash: str) -> list[str]:
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_hash:
        raise InvalidDocument("The stored book failed its integrity check. Restore it from a backup.", "book_integrity_failed")
    metadata = inspect_epub(source, output, "Untitled book")
    notices = list(metadata.get("warnings", []))
    with ZipFile(source) as original, ZipFile(output / "reader.epub", "w", compression=ZIP_DEFLATED) as result:
        total = 0

        def write(name: str, data: bytes, *, stored=False):
            nonlocal total
            total += len(data)
            if total > MAX_OUTPUT:
                raise InvalidDocument("The reading copy exceeds its processing limit.")
            result.writestr(name, data, compress_type=ZIP_STORED if stored else ZIP_DEFLATED)

        write("mimetype", b"application/epub+zip", stored=True)
        write("META-INF/container.xml", b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        container = read_xml(original, "META-INF/container.xml")
        rootfile = next(node for node in container.findall(f"{OCF}rootfiles/{OCF}rootfile") if node.get("media-type") == "application/oebps-package+xml")
        package_name = referenced_member("", rootfile.get("full-path", ""))
        package = read_xml(original, package_name)
        package_metadata = package.find(OPF + "metadata")
        if any(item.get("property") == "rendition:layout" and clean_text(item.text) == "pre-paginated" for item in package_metadata.findall(OPF + "meta")):
            raise InvalidDocument("This first EPUB reader supports reflowable books; fixed-layout books are not supported yet.", "unsupported_layout")
        manifest = package.findall(OPF + "manifest/" + OPF + "item")
        by_id = {}
        pages = {}
        for item in manifest:
            by_id.setdefault(item.get("id"), item)
            if item.get("media-type") in {"application/xhtml+xml", "text/html"} and "nav" not in item.get("properties", "").split():
                path = referenced_member(package_name, item.get("href", ""))
                if path not in pages:
                    pages[path] = f"text/chapter-{len(pages):04d}.xhtml"
        if not pages or len(pages) > MAX_PAGES:
            raise InvalidDocument("The EPUB has no supported text chapters or exceeds the chapter limit.")
        spine = []
        for ref in package.findall(OPF + "spine/" + OPF + "itemref"):
            item = by_id[ref.get("idref")]
            path = referenced_member(package_name, item.get("href", ""))
            if path not in pages:
                raise InvalidDocument("The EPUB reading order contains an unsupported content type.", "unsupported_layout")
            spine.append((path, ref.get("linear", "yes")))
        images = {}
        skipped_image = False
        for item in manifest:
            if not item.get("media-type", "").startswith("image/"):
                continue
            path = referenced_member(package_name, item.get("href", ""))
            if path in images:
                continue
            image = jpeg_image(original.read(path)) if original.getinfo(path).file_size <= MAX_COVER_BYTES else None
            if image is None:
                skipped_image = True
                continue
            images[path] = f"images/image-{len(images):04d}.jpg"
            write("book/" + images[path], image)
        if skipped_image:
            notices.append("Some unsupported or oversized images are omitted from this reading layout.")
        page_titles = {}
        for path, destination in pages.items():
            if original.getinfo(path).file_size > MAX_XML_BYTES:
                raise InvalidDocument("An EPUB chapter exceeds the processing limit.")
            data = original.read(path)
            chapter = sanitized_chapter(data, path, destination, pages, images, metadata["title"])
            parsed = ET.fromstring(chapter)
            heading = next((node for node in parsed.iter() if node.tag in {f"{{{XHTML}}}h1", f"{{{XHTML}}}h2"}), None)
            page_titles[path] = clean_text(" ".join(heading.itertext())) if heading is not None else f"Chapter {len(page_titles) + 1}"
            write("book/" + destination, chapter)
        toc = table_of_contents(original, package, package_name, manifest, pages, page_titles, [path for path, _ in spine])
        nav_body = ET.Element(f"{{{XHTML}}}body")
        nav = ET.SubElement(nav_body, f"{{{XHTML}}}nav", {"xmlns:epub": EPUB_NS, "epub:type": "toc", "id": "toc"})
        listing = ET.SubElement(nav, f"{{{XHTML}}}ol")
        for label, href in toc:
            ET.SubElement(ET.SubElement(listing, f"{{{XHTML}}}li"), f"{{{XHTML}}}a", {"href": href}).text = label
        write("book/nav.xhtml", xhtml_document("Contents", nav_body))

        opf = ET.Element("package", {"xmlns": OPF[1:-1], "version": "3.0", "unique-identifier": "book-id"})
        meta = ET.SubElement(opf, "metadata", {"xmlns:dc": DC[1:-1]})
        ET.SubElement(meta, "dc:identifier", {"id": "book-id"}).text = "urn:sha256:" + expected_hash
        ET.SubElement(meta, "dc:title").text = metadata["title"]
        ET.SubElement(meta, "dc:language").text = metadata.get("language") or "en"
        ET.SubElement(meta, "meta", {"property": "dcterms:modified"}).text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ET.SubElement(meta, "meta", {"property": "rendition:layout"}).text = "reflowable"
        for author in metadata["authors"]:
            ET.SubElement(meta, "dc:creator").text = author
        out_manifest = ET.SubElement(opf, "manifest")
        page_ids = {}
        for index, (path, href) in enumerate(pages.items()):
            page_ids[path] = f"chapter-{index}"
            ET.SubElement(out_manifest, "item", {"id": page_ids[path], "href": href, "media-type": "application/xhtml+xml"})
        for index, href in enumerate(images.values()):
            ET.SubElement(out_manifest, "item", {"id": f"image-{index}", "href": href, "media-type": "image/jpeg"})
        ET.SubElement(out_manifest, "item", {"id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav"})
        out_spine = ET.SubElement(opf, "spine")
        for path, linear in spine:
            ET.SubElement(out_spine, "itemref", {"idref": page_ids[path], "linear": "no" if linear == "no" else "yes"})
        spine_paths = {path for path, _ in spine}
        for path in pages:
            if path not in spine_paths:
                ET.SubElement(out_spine, "itemref", {"idref": page_ids[path], "linear": "no"})
        write("book/package.opf", ET.tostring(opf, encoding="utf-8", xml_declaration=True))
    return notices


def prepare_reading_copy(source: str, directory: str, expected_hash: str) -> None:
    output = Path(directory)
    try:
        notices = build_reading_copy(Path(source), output, expected_hash)
        result = {"ok": True, "warnings": notices, "source_hash": expected_hash, "artifact_version": ARTIFACT_VERSION}
    except InvalidDocument as error:
        result = {"ok": False, "message": str(error), "code": error.code}
    except Exception:
        result = {"ok": False, "message": "The EPUB reading copy could not be prepared safely.", "code": "reader_preparation_failed"}
    (output / "result.json").write_text(json.dumps(result), encoding="utf-8")
