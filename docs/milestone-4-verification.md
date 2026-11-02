# Milestone 4: EPUB reading

Historical checkpoint. The later compatibility/progress stage supersedes the
limitations below; see [current progress design](reading-progress.md).

Implemented: open an EPUB from the library, paginated reading, previous/next
controls, contents navigation, internal chapter/fragment links, resizing, keyboard
arrows, and returning to the library. The reading engine reports versioned EPUB
CFIs behind an adapter. PDF reading and saved progress remain future scope.

Windows, Android, and modern iPhone Safari are primary targets. Only dedicated
compatibility work for the iPad running 12.5.8 is deferred.

## Validation

- All 59 backend regression and reader tests pass, including EPUB 2/3 contents,
  generated XHTML/JPEG output, preserved internal links, removed active content,
  source integrity, fixed-layout rejection, authorization, version checks,
  cache reuse across restarts, and reproducible chapter trees.
- Frontend type checking and production build pass.
- Three Playwright projects pass: desktop Chromium, Android-style touch layout,
  and iPhone-style WebKit layout. They render a generated test book, load images,
  paginate, jump via contents, resize, follow an internal link, return to the
  library, and reject an anonymous reopen. They also confirm no external book
  requests, no uncaught page errors, and CSP blocking of inserted document scripts.
- The runtime npm dependency audit reported zero known vulnerabilities after
  overriding EPUB.js's obsolete XML parser range with @xmldom/xmldom 0.9.12.
- The EPUB previously supplied by the owner successfully prepared 13 chapters
  and two images in a disposable cache, with the original unchanged. No private
  content, source paths, or reading images were committed to Git.

Headless screenshots were inspected during browser QA. Automated WebKit runs on
Windows and a mobile viewport do not establish physical iPhone/Android behavior,
older Safari support, VoiceOver behavior, or iPadOS 12.5.8 compatibility. Actual
device reading and orientation checks remain manual. The owner's iPhone iOS
version has been requested; no historical Safari version is claimed as tested.

## Decisions and learning objectives

The backend generates a controlled reading artifact rather than handing the
uploaded ZIP to the browser. It removes publisher CSS/scripts/forms/frames and
external resources, re-encodes supported images, creates well-formed XHTML, maps
internal links, and emits a unique generated package and contents document.
This standardizes reflowable book typography at the cost of complex publisher
layouts, custom fonts, SVG/MathML, animation, and interactive features.

The artifact is generated in an owned, time-limited process, cached under a fixed
version, and served only after ownership checks. Originals stay byte-for-byte
unchanged. Body structure must not silently change after location persistence is
introduced, because CFIs identify nodes and text offsets in that structure.

WebKit testing exposed two lifecycle details. Calling resize before EPUB.js's
first CFI report could clear the reading view without restoring it, so observation
now starts after relocation. WebKit also blocks parent event handlers in an
iframe that disallows all scripts. The controlled reading iframe permits engine
handlers while the chapter CSP explicitly prohibits document scripts; publisher
code is removed before delivery. This configuration must never be reused to
render original unsanitized EPUBs. Parent-managed links validate the target
against the known spine and never navigate to external URLs.

This milestone practices safe rendering boundaries, immutable derived artifacts,
browser resource cleanup, responsive layout, asynchronous lifecycle handling,
format adapters, and browser-level acceptance testing. Database schema changes,
new accounts, remote exposure, and server-service changes were not required.

## Manual review

1. Refresh the running library and choose Read book on an EPUB.
2. Check text, images, Next/Previous, Contents, and an internal link if present.
3. Resize the desktop window. On a privately connected phone, test portrait and
   landscape and verify controls remain usable.
4. Return to Library and reopen. Expect the beginning: persistence is not yet
   implemented, and the reader displays that limitation.
5. Confirm existing PDF cards remain in the unified library, without claiming a
   working PDF reader yet.
