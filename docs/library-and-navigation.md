# Library controls, app theme, and PDF navigation

## User-facing changes

- The mobile EPUB toolbar keeps **Contents** and **Settings** on one row,
  alongside the Library link. The title gets a separate truncated row.
- **Rename** under each library book opens a title editor. Save updates the
  catalog and reader heading, including after reload/server restart. This edits
  only SQLite display metadata; originals, filesystem names, hashes, generated
  reading copies, book IDs and saved positions remain unchanged.
- The home page's top-right account circle opens a panel with the current
  username, owner role, sign-in status, Sign out, and **Application theme**.
  The app does not collect email addresses or profile photos.
- Light/sepia/dark now cover the library, account panel, forms, notices and reader
  controls. The same theme is used by EPUB content; PDF page artwork remains
  unchanged. Signed-in themes use the existing authenticated preference API.
  Signed-out selection uses browser storage when available, and account settings
  take over after sign-in.
- PDFs respond to Left/Right arrows and Page Up/Down while reading. Form fields,
  links, settings and conflict controls retain their normal keyboard behavior.
  Up/Down arrows remain available for scrolling.
- A decisive horizontal swipe turns a PDF page when it fits horizontally.
  Vertical/diagonal drags, multitouch, browser-edge gestures and page/browsing
  zoom that needs horizontal panning do not turn pages. Zoomed wide pages retain
  native panning; Previous/Next buttons always remain available.

## Implementation

`BookTitleUpdate` and `PATCH /api/v1/books/{id}` in `backend/app/api.py` perform
owner-scoped updates with Origin/CSRF protection. Titles are trimmed, nonempty,
at most 500 characters, and cannot contain control characters. Only the title
field is accepted, preventing file-key or other metadata changes through this API.

`book-grid.tsx` owns the small editor and updates the parent catalog after an
acknowledged response. Failure keeps the draft available for retry. It does not
automatically strip text from titles, which could remove intentional punctuation.

`ReaderPreferencesProvider` now lives in the root layout. Readers and the account
panel consume the same state; route changes no longer create independent theme
stores. Sign-in/out refreshes that state. `globals.css` supplies application
palette variables and the mobile toolbar grid. `profile-menu.tsx` handles the
account popover, outside clicks, Escape and keyboard focus return.

`pdf-reader.tsx` routes keyboard and touch navigation through the existing page
function and progress service. An in-flight page guard prevents duplicate turns.
Touch classification uses one touch, a 64px horizontal threshold, directional
dominance, a short duration, safe edge spacing and a check for horizontal overflow.
It does not prevent native vertical scrolling or pinch-to-zoom events.

## Scope and validation

No dependencies or database migrations are needed. No original books are renamed
on disk. Existing EPUB content security and revisioned progress remain in place.
Physical-device gesture checks are still useful; browser tests simulate touch
events and do not establish real iPhone/iPad hardware behavior.

Backend regressions cover title authentication, CSRF, validation, restart
persistence, unchanged original/reading-copy bytes and a nonempty saved position.
Browser checks cover the aligned mobile buttons, account theme propagation,
title editing/reload, keyboard turns, horizontal swipes and guards for vertical
drags, multitouch and wide-page panning, alongside existing reader/sync tests.

Learning focus: editing metadata independently of source files, application-level
state providers, theme tokens, accessible popovers, and separating reading input
from native scrolling/zooming.

Verification: all 84 backend tests and nine browser checks pass across desktop
Chromium, Android-style Chromium and iPhone-style WebKit. The progress browser
test checks the stable CFI and overlapping visible passages after restoration;
page ordinals can change at a reflow boundary with large fonts. Mobile toolbar
alignment and account placement are checked geometrically; generated mobile and
full-library screenshots were inspected. Type checking and the production build
also pass.
