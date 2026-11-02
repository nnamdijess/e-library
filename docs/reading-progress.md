# Reading positions and synchronization

## Components

- `backend/app/progress.py`: validated format-specific locations and atomic
  revision checks. `api.py` keeps owner authorization and CSRF at the boundary.
- Migration `0002` adds `reading_progress`, keyed by user and book, with a JSON
  location, percentage, revision, last operation UUID, and server timestamp.
- `frontend/src/readers/progress.ts`: shared serial save queue, local retry
  journal, acknowledged status, polling and explicit conflict resolution.
- The EPUB.js adapter generates character-based locations (1,600 characters)
  for approximate percentages and restores an artifact-versioned CFI. Page
  numbers are local to a chapter/view size, not durable position identifiers.
- `pdf-reader.tsx`: PDF.js canvas rendering, previous/next pages, fit width/zoom,
  and page/normalized vertical offset restoration. One page/canvas is rendered
  at a time; the canvas backing store is capped at six million pixels.

## Protocol

`GET /api/v1/books/{id}/progress` returns revision zero when no position exists.
`PUT` requires the session, exact trusted Origin and CSRF token, plus
`base_revision`, a fresh `update_id`, location, and percentage. Format, artifact
version, finite percentage/offset and PDF page bounds are checked. A PDF's
percentage is calculated on the server from its page and offset.

SQLite insert-on-conflict/update-with-revision makes acceptance atomic. A stale
write receives HTTP 409 with the current snapshot. Retries of the last accepted
operation and identical payload return that same revision. A lost response
cannot cause the client to label an unconfirmed position synchronized.

The browser journals each pending position before attempting a save, debounces
for 1.2 seconds (maximum five seconds during continuous changes), sends one save
at a time, and retries unavailable-server saves. Hidden/page-exit saves use
best-effort keepalive; journal recovery is still required because mobile browsers
can terminate tabs without delivering lifecycle events. Confirmed state lives on
the server and survives browser/server restarts. Browser storage can be evicted;
unsynchronized data is not a backup, and storage failures are displayed.

Opening a book fetches server progress before displaying content. A compatible
pending local position can be restored and retried. The reader checks for newer
server progress on reconnect/focus and every 15 seconds. It offers **Load saved
position** or **Keep this position** for conflicts. Keeping local data rebases a
fresh operation on the observed server revision; another intervening update can
still conflict. Clock skew and reading backwards do not decide winners. This is
polling-based cross-device synchronization, not simultaneous collaborative reading.

EPUB artifact version 2 is part of the position contract. A future tree-changing
reader preparation algorithm must migrate positions explicitly or show an
incompatibility notice, rather than reuse a CFI against a different document.

## PDF and device scope

PDF.js, its worker, CMaps, fonts and WASM files are served locally. The portable
`scripts/copy-pdf-assets.mjs` predev/prebuild hook copies versioned assets from
the installed package; a deployment must include `public/pdfjs`. No CDN is used.
PDF bytes are owner-authenticated and delivered as attachments with restrictive
CSP. The app renders canvas content only, without a scripting manager, XFA,
annotation actions, external links, or attachment execution.

The current PDF.js legacy build targets Safari 18+; the Next.js interface's
baseline is Safari 16.4+. These are different compatibility boundaries. Actual
iPhone testing remains required and older-iPad support is not claimed. The PDF
reader currently downloads the whole PDF into the worker; large/scanned books
can consume significant memory. Search/text layers, continuous multi-page
scrolling, bookmarks, highlights and annotations are future stages. Scanned
PDFs render but OCR is not implemented. Full offline book caching/PWA installation
is also future work; the current journal handles progress connectivity failures.

## Upgrade and review

Stop the backend, back up the complete `data/` directory, install locked Python
requirements and frontend packages, run `python -m app.cli migrate` from backend,
then rebuild/restart. Do not recreate the owner or overwrite configuration.
Migration 0002 adds a table; it does not rewrite books, users, or existing metadata.

Review both supplied EPUBs, navigate and wait for **Synced**, reopen/refresh, and
repeat on another signed-in device. Try an uploaded PDF, change page/scroll,
wait for confirmation and reopen. Private HTTPS/Tailscale deployment remains a
separate networking stage; no server services were modified.

Learning objectives: resource resolution and content trust boundaries; format
adapters; schema migrations; atomic compare-and-set; idempotent requests; durable
local queues; lifecycle cleanup; and browser tests that distinguish a displayed
status from an actual server acknowledgement.

## Verification results

- 69 backend tests pass, including schema/model agreement, EPUB 2/3 and PDF
  ingestion, hostile XML/content, source preservation, fallbacks, nested TOCs,
  protected delivery, restart persistence, simultaneous saves and stale revisions.
- Nine browser checks pass: EPUB reading/security, PDF page/offset restoration,
  and CFI refresh/retry/conflict recovery, each in desktop Chromium,
  Android-style Chromium, and iPhone-style WebKit.
- Frontend type checking and the production build pass; the runtime npm audit
  reports zero known vulnerabilities. Production health, local PDF worker delivery,
  and anonymous denial for reading/progress endpoints were checked after restart.
- Both owner-supplied EPUBs prepare successfully (24 and 13 documents); source
  hashes remain unchanged. Private publications are not committed as fixtures.
- The local database was backed up before migration 0002. Integrity checks and
  existing user/book/session counts were unchanged after migration.

Automated browser layouts are not physical-device verification. User review on
the actual iPhone and Android remains the next acceptance step.
