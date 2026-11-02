"""Bounded, passive EPUB resources. No publisher code or network references."""

import base64
import logging
import re
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as XML
import tinycss2

from app.documents import InvalidDocument, MAX_XML_BYTES, referenced_member

log = logging.getLogger(__name__)
HTML_TYPES = {"application/xhtml+xml", "text/html"}
SVG = "http://www.w3.org/2000/svg"
CSS_PROPERTIES = set("color background-color font-family font-size font-style font-weight font-variant text-align text-indent text-decoration text-transform line-height letter-spacing word-spacing white-space vertical-align margin margin-top margin-right margin-bottom margin-left padding padding-top padding-right padding-bottom padding-left border border-width border-style border-color border-top border-bottom border-collapse border-spacing width height max-width max-height min-width list-style-type list-style-position break-before break-after break-inside page-break-before page-break-after page-break-inside orphans widows display float clear".split())


def safe_tokens(tokens):
    for token in tokens:
        if token.type in {"url", "error", "at-keyword"}:
            return False
        if token.type == "function":
            if token.lower_name not in {"rgb", "rgba", "hsl", "hsla", "calc", "min", "max", "clamp"} or not safe_tokens(token.arguments):
                return False
        if hasattr(token, "content") and not safe_tokens(token.content):
            return False
    return True


def safe_declarations(css):
    declarations = []
    for item in tinycss2.parse_declaration_list(css[:MAX_XML_BYTES], skip_comments=True, skip_whitespace=True):
        if item.type == "declaration" and item.lower_name in CSS_PROPERTIES and safe_tokens(item.value):
            # Do not carry priority into the app's future reading preferences.
            declarations.append(item.lower_name + ":" + tinycss2.serialize(item.value))
    return ";".join(declarations)


def safe_stylesheet(css):
    rules = []
    for item in tinycss2.parse_stylesheet(css[:MAX_XML_BYTES], skip_comments=True, skip_whitespace=True):
        # @import, fonts, animations, and all nested at-rules are intentionally absent.
        if item.type != "qualified-rule" or not safe_tokens(item.prelude):
            continue
        selector = tinycss2.serialize(item.prelude)
        # Simple publisher selectors; disallow namespace/CSS escape tricks.
        if not re.fullmatch(r"[\w\s.#,:>+~*\[\]=\"'()|-]+", selector):
            continue
        declarations = safe_declarations(tinycss2.serialize(item.content))
        if declarations:
            rules.append(selector + "{" + declarations + "}")
    return "\n".join(rules)


def detected_type(data):
    try:
        root = XML.fromstring(data, forbid_dtd=False, forbid_entities=True, forbid_external=True)
        name = root.tag.rsplit("}", 1)[-1].lower()
        return "image/svg+xml" if name == "svg" else "application/xhtml+xml" if name == "html" else "xml:" + name
    except Exception:
        return "text/html" if re.search(br"<(?:!doctype\s+html|html)(?:\s|>)", data[:4096], re.I) else "unknown"


def reading_plan(archive, package_name, manifest, refs):
    by_id = {item.get("id"): item for item in reversed(manifest)}
    kinds, paths = {}, {}
    for item in manifest:
        path = referenced_member(package_name, item.get("href", ""))
        paths[item.get("id")] = path
        declared = item.get("media-type", "").split(";", 1)[0].strip().lower()
        if declared not in HTML_TYPES | {"image/svg+xml"}:
            continue
        if archive.getinfo(path).file_size > MAX_XML_BYTES:
            continue
        detected = detected_type(archive.read(path))
        if (declared in HTML_TYPES and detected in HTML_TYPES) or declared == detected == "image/svg+xml":
            kinds[path] = "svg" if declared == "image/svg+xml" else "html"
    spine, aliases, notices = [], {}, []
    for index, ref in enumerate(refs):
        identifier = ref.get("idref")
        first = identifier
        seen = set()
        while identifier not in seen:
            seen.add(identifier)
            item = by_id.get(identifier)
            if item is None:
                raise InvalidDocument(f"Spine item {index + 1} ({first}) has a missing fallback reference: {identifier}.", "malformed_fallback")
            path = paths[identifier]
            if path in kinds:
                aliases[paths[first]] = path
                spine.append((path, ref.get("linear", "yes")))
                if identifier != first:
                    notices.append(f"Reading order item {index + 1} uses fallback {path} for {paths[first]}.")
                break
            detected = detected_type(archive.read(path)) if archive.getinfo(path).file_size <= MAX_XML_BYTES else "oversized"
            log.warning("EPUB spine resource: index=%s idref=%r path=%r declared=%r detected=%r fallback=%r", index + 1, identifier, path, item.get("media-type"), detected, item.get("fallback"))
            fallback = item.get("fallback")
            if fallback:
                identifier = fallback
                continue
            # Keep an explicit, navigable place in the reading order. Never
            # silently drop real content because another chapter is readable.
            kinds[path] = "unsupported"
            notices.append(f"Cannot render spine item {index + 1}: {path} (declared {item.get('media-type')}, detected {detected}); no supported fallback. A notice marks its position.")
            spine.append((path, ref.get("linear", "yes")))
            break
        else:
            raise InvalidDocument(f"Spine item {index + 1} ({first}) has a cyclic fallback chain.", "malformed_fallback")
    if not any(kind != "unsupported" for kind in kinds.values()):
        raise InvalidDocument("No supported EPUB reading content. " + " ".join(notices)[:3000], "unsupported_content")
    return kinds, spine, aliases, notices


def passive_svg(data, source_name, images, image_bytes):
    """SVG inside an image context: allowlisted static shapes and local raster images."""
    root = data if isinstance(data, ET.Element) else XML.fromstring(data, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    tags = set("svg g defs symbol use path rect circle ellipse line polyline polygon text tspan title desc image linearGradient radialGradient stop clipPath".split())
    attrs = set("id viewBox width height x y x1 y1 x2 y2 cx cy r rx ry d points transform fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin opacity font-family font-size font-weight text-anchor dominant-baseline dx dy offset stop-color stop-opacity gradientUnits gradientTransform clip-path preserveAspectRatio".split())

    def copy(node):
        local = node.tag.rsplit("}", 1)[-1] if isinstance(node.tag, str) else ""
        if local not in tags:
            return None
        out = ET.Element(f"{{{SVG}}}" + local)
        for key, value in node.attrib.items():
            key = key.rsplit("}", 1)[-1]
            if key in attrs and len(value) <= 20000:
                if "url(" in value.lower() and not re.fullmatch(r"url\(#[\w.-]+\)", value):
                    continue
                out.set(key, value)
            elif key == "href":
                if local == "use" and re.fullmatch(r"#[\w.-]+", value):
                    out.set("href", value)
                elif local == "image":
                    try:
                        target = referenced_member(source_name, value)
                        if target in images:
                            out.set("href", "data:image/jpeg;base64," + base64.b64encode(image_bytes[images[target]]).decode())
                    except (InvalidDocument, ValueError):
                        pass
        out.text = node.text
        out.tail = node.tail
        for child in node:
            result = copy(child)
            if result is not None:
                out.append(result)
        return out

    safe = copy(root)
    if safe is None or safe.tag != f"{{{SVG}}}svg":
        raise InvalidDocument(f"Invalid SVG document: {source_name}.")
    return "data:image/svg+xml;base64," + base64.b64encode(ET.tostring(safe, encoding="utf-8")).decode()
