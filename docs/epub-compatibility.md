# EPUB compatibility investigation

The reported book failed because its valid XHTML navigation document also
appears in the spine. The reader preparation excluded all `nav` resources and
then rejected the spine reference. This was an application bug. The supplied
original prepared 24 documents after the fix; its SHA-256 stayed unchanged.

The frontend already uses EPUB.js. Retain that engine and fix the preparation
boundary rather than replace it. Version 2 reading copies include navigation
documents, checked HTML/XHTML, static allowlisted SVG images, safe publisher CSS,
nested EPUB 3 navigation/EPUB 2 NCX, and supported manifest fallback chains.
Internal targets are resolved once against archive paths, including percent
encoding. Fallback aliases preserve links to the original resource.

Unsupported spine resources have explicit notice chapters; they are never
silently discarded. Missing/cyclic fallback references are malformed input,
distinct from unsupported media. Server warnings include spine index, IDREF,
archive path, declared/detected types, and fallback. Imported originals and
metadata are preserved. The reader's Reopen button retries preparation.

CSS uses tinycss2 token parsing and a property/selector allowlist. Network URLs,
imports, fonts, animations and unknown functions are removed. SVG is filtered
into static shapes/text and embedded local raster images, then displayed in an
image context; scripts, event handlers, foreignObject, and remote links are
absent. Chapter CSP still forbids scripts and network requests. This preserves
more formatting, without claiming pixel-identical publishing layout. Fixed
layout, multimedia, MathML, and arbitrary SVG effects remain limitations.

The artifact version increased because document trees and spine indices changed.
Version 1 caches remain untouched; version 2 is generated lazily. No saved CFI
data existed before this change. Future structure changes require an explicit
position migration or a user-visible restart, never silent CFI reuse.
