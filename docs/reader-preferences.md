# Reader preferences and PDF zoom

Open **Settings** inside either reader. Light, sepia and dark themes apply to
the surrounding reader interface. EPUB settings additionally control font
family, font size (14–36px), line spacing and margins. Fonts are local system
fonts; availability and exact appearance differ between devices. Margins adapt
to narrow screens and are capped at 12% of viewport width per side.

PDF **Fit page** is the new default: it uses the smaller of the horizontal and
vertical scale factors so the whole page fits in the reading area. **Fit width**
remains available. Fixed 50%, 75%, 100%, 125%, 150%, 175%, 200%, 250% and 300%
options use PDF page dimensions at one CSS pixel per PDF point at 100%; they are
not multipliers of Fit width. High zoom requires scrolling. Changing zoom or
window size preserves the logical page/offset; clamping a fully visible page to
scroll position zero does not replace the saved reading position.

PDF pages retain their original colors, fonts and layout. The shared theme
changes the toolbar, background and controls rather than inverting documents.
The six-million-pixel canvas budget remains in place at high zoom.

## Files and persistence

- `backend/app/preferences.py` validates a bounded, allowlisted settings schema.
  `GET /api/v1/preferences` returns defaults or the owner's saved settings.
  `PATCH` requires owner authentication, trusted Origin and CSRF protection.
- Migration `0003` adds `reader_preferences`, keyed by user. Each changed field
  is written atomically with an upsert. Changes to different fields on different
  devices merge; the last server write wins when both change the same field.
- `frontend/src/readers/preferences.ts` loads account settings before displaying
  the reader, debounces saves for 500ms, serializes updates and retries failures.
  Opening a reader or returning focus retrieves the current account settings.
- `reader-settings.tsx` supplies the shared settings panel. The EPUB adapter
  applies controlled CSS without changing the underlying document tree, reflows
  at the current CFI, and retains that CFI until the reader navigates again.
- `pdf-reader.tsx` observes both viewport dimensions to support Fit page and
  distinguishes programmatic scroll changes from user reading movement.

Preference saves have their own status, separate from reading-progress sync.
Wait for **Preferences saved** before closing. Unconfirmed preference changes
are retried while the tab stays open; they do not yet have an offline durable
journal. This differs from the existing reading-progress retry journal.

## Upgrade and review

Stop the backend and back up `data/`. Run `python -m app.cli migrate` from
`backend/` before restarting the updated backend; rebuild the frontend. Migration
0003 does not modify books, original EPUBs/PDFs or existing reading progress.

Review a portrait PDF in a wide Windows window: Fit page should avoid vertical
scrolling. Try Fit width and a fixed zoom, move to another page, wait for sync,
and reopen. For EPUBs, navigate first, change settings, wait for preferences to
save, and refresh. Verify the passage and settings restore. Physical iPhone and
Android checks remain useful; older-iPad compatibility is still a separate stage.

Learning focus: presentation state versus content locations, validated preference
schemas, additive migrations, partial updates, asynchronous reflow, responsive
geometry and browser regression testing.

## Verification

78 backend tests pass, including preference authorization/CSRF, rejected values,
partial merges across independently authenticated sessions, schema/model agreement
and restart persistence. Browser acceptance covers EPUB rendering, all three
themes, font/spacing/margin changes, saved preferences after refresh, exact CFI
preservation, PDF Fit page/300% zoom and offset restoration, and the existing
progress retry/conflict checks on desktop, Android-style Chromium and iPhone-style
WebKit. WebKit serializes some fractional CSS values differently; spacing checks
use numeric tolerance rather than comparing equivalent pixel strings exactly.

The local database was backed up before applying 0003. Integrity checks passed,
and existing user/book/session/progress record counts were preserved.
All nine browser checks passed in the final suite. The Windows-sized Fit page
screenshot was visually inspected and shows the full portrait page inside the
available reading area.
