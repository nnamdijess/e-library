# Ebook Library

A personal, self-hosted EPUB and PDF library, developed incrementally.

**Completed scope: library, EPUB/PDF reading, and durable progress.** The application has owner login,
revocable cookie sessions, SQLite metadata, validated EPUB/PDF uploads, private
file storage, metadata extraction, covers/placeholders, and a unified library
grid, plus an EPUB reader with pagination, chapter/contents navigation, internal
links, PDF.js page rendering, and confirmed server-side progress with CFI/page restoration. Ubuntu Compose deployment and backup/recovery tooling are prepared; actual server
deployment and container build validation remain operator steps. See the guides below.

## Prerequisites

- Node.js 22.13+ or 24 LTS with npm (tested with Node 24.13.0).
- Python 3.12 or 3.13 (tested with Python 3.13.15).
- Git.

No Docker, WSL, external database, or cloud service is required for development.
The commands below start from the repository root unless stated otherwise.

When updating an existing checkout, install the updated Python requirements and
run `npm.cmd ci` in `frontend/`. Stop the backend, back up `data/`, and run
`python -m app.cli migrate` from `backend/` to add revisioned reading progress.
Existing books get version 2 reading copies lazily; originals remain unchanged.

Reader **Settings** now provides EPUB fonts, size, spacing, margins, and
light/dark/sepia themes saved to your account. PDFs default to **Fit page** and
offer **Fit width** plus 50%–300% zoom. Apply migration 0003 when upgrading.
See [reader preferences](docs/reader-preferences.md) for behavior and verification.

Use **Rename** under a book to edit its displayed title. The top-right account
circle on the home page contains sign-in details, Sign out, and an app-wide
theme selector. PDFs also support arrow/Page Up/Down keys and horizontal page
swipes when the page fits horizontally; wide zoomed pages retain panning.
See [library and navigation controls](docs/library-and-navigation.md).

## Ubuntu deployment and recovery

- [Ubuntu deployment guide](docs/ubuntu-deployment.md): isolated Compose stack,
  private HTTPS/Tailscale access, first installation or Windows-library transfer,
  and upgrades alongside your existing services.
- [Backup and recovery](docs/backup-recovery.md): verified offline archives,
  empty-directory restores, automatic session revocation and restore drills.

The stack is prepared rather than deployed. Docker image builds cannot be run in
this Windows environment; a manual Linux validation workflow is provided. No
server configuration or existing services have been changed. Git transfers source
code; transfer your existing library separately using a verified backup archive.

## Windows setup (PowerShell)

Create an isolated Python environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
Set-Location frontend
npm.cmd ci
Set-Location ../backend
..\.venv\Scripts\python.exe -m app.cli migrate
..\.venv\Scripts\python.exe -m app.cli create-owner --username owner
```

The owner command prompts twice for a password of at least 12 characters. Input
is hidden; never put your password in command arguments, environment files, or
Git. There is no default password or public registration. The command refuses
to replace an existing owner. The username is case-insensitive and accepts
letters, digits, dots, underscores, and hyphens.

Run initial setup only once. Before starting an updated backend, run `migrate`
again; it applies only missing migrations. Back up existing data before future
schema upgrades. Do not overwrite local configuration or recreate the owner.
Using the virtual environment's executable directly avoids PowerShell activation
policy changes. `npm.cmd` avoids the corresponding PowerShell script-policy issue.

In terminal 1, from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

In terminal 2, from the repository root:

```powershell
Set-Location frontend
npm.cmd run dev
```

Open <http://127.0.0.1:3000> and sign in with the owner credentials you chose.
You should see your library and **API connected**. New libraries start empty.
Use **Add a book** to upload one DRM-free EPUB or PDF. Reloading the page or
restarting both services preserves your login until the session expires or you
sign out. Do not interchange `localhost` and `127.0.0.1`; browser cookies and
trusted origins are specific to the address you use.
The API alone responds at <http://127.0.0.1:8000/api/v1/health> with
`{"status":"ok"}`. Interactive API documentation is at
<http://127.0.0.1:8000/docs>.

Stop either service with Ctrl+C. Stop the backend and press **Check again** to
verify the page reports an unavailable connection; restart it and retry to recover.

## Linux development

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
cd frontend
npm ci
cd ../backend
../.venv/bin/python -m app.cli migrate
../.venv/bin/python -m app.cli create-owner --username owner
```

Then, in two separate terminals starting from the repository root:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev
```

Linux execution has not been verified on your server. These are portable local
development instructions, not deployment instructions.

## Verification

Windows, starting at the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ../frontend
npm.cmd run typecheck
npm.cmd run build
```

On Linux use `../.venv/bin/python`, and `npm` instead of `npm.cmd`.
The backend tests use temporary SQLite databases and an in-process HTTPX ASGI
client. They cover the health contract, authentication, CSRF, session rotation
and expiry, throttling, simultaneous logins, catalog constraints, migrations,
and restart persistence. Upload tests additionally cover generated EPUB/PDF
fixtures, metadata and JPEG covers, unsafe archives, actual-byte limits,
timeouts, failed-write cleanup, and storage auditing. They never modify your
real catalog. Type checking and a
production build validate the frontend scaffold; type checking first generates
Next.js route declarations so it also works before the first build. These checks
do not establish reader
or older-iPad compatibility.

### Repeatable reader browser tests

The reader has Playwright checks for desktop Chromium, an Android-style touch
viewport, and an iPhone-style WebKit viewport. From `frontend/` on Windows:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = [System.IO.Path]::GetFullPath('../.cache/ms-playwright')
npx.cmd playwright install chromium webkit
npm.cmd run test:e2e
```

On Linux, use `PLAYWRIGHT_BROWSERS_PATH="$(pwd)/../.cache/ms-playwright" npx playwright install chromium webkit`
then `npm run test:e2e`. Browser system libraries may be required on Linux;
installation on your Ubuntu server has not been performed.

The tests start a disposable API on loopback port 8001 and a Next.js development
server on port 3001. Those ports must be free; tests refuse to reuse another
service. They seed generated test content and a test-only account in a temporary
database, independent of your library on port 8000. Screenshots/traces go into
ignored `.cache/playwright-results/`. An interrupted process can leave a temporary
test directory under `.cache/`; it is not part of your library.

Tests verify real rendering, images, pagination, table-of-contents jumps,
internal links using touch on mobile layouts, resizing, return navigation,
authentication rejection, no external book requests, and blocked document scripts.
WebKit emulation is not a physical iPhone or a test of iPadOS 12.5.8.

After building, `npm.cmd start` starts the production frontend on loopback at
port 3000. Stop the frontend development process first. The backend must still
be running. This is a local production-build check, not a server deployment.

## Configuration

| Setting | Location | Meaning |
| --- | --- | --- |
| `EBOOK_APP_NAME` | `backend/.env` or environment | API title; validated at application startup |
| `EBOOK_DATA_DIR` | Backend configuration | Private data directory, default `data/` at repository root; contains `library.sqlite3` |
| `EBOOK_TRUSTED_ORIGINS` | Backend configuration | JSON array of exact browser origins; defaults to `["http://127.0.0.1:3000"]` |
| `EBOOK_SESSION_COOKIE_SECURE` | Backend configuration | Defaults to `false` for loopback HTTP only; non-loopback access requires `true` and HTTPS |
| `EBOOK_SESSION_DAYS` | Backend configuration | Absolute session lifetime, default 7 days, range 1–30 |
| `EBOOK_MAX_UPLOAD_BYTES` | Backend configuration and frontend `.env.local` | File limit, default 104857600 (100 MiB); keep both values aligned |
| `EBOOK_PROCESSING_TIMEOUT_SECONDS` | Backend configuration | Worker timeout, default 30 seconds, range 1–120 |
| `BACKEND_URL` | `frontend/.env.local` or environment | Server-only upstream API origin; defaults to `http://127.0.0.1:8000` |
| `NEXT_TELEMETRY_DISABLED` | Frontend environment | Set to `1` to disable Next.js telemetry |

The backend always resolves its `.env` relative to `backend/`, not the shell's
working directory. Relative data paths resolve from the repository root.
Unknown dotenv keys and invalid values fail early. Configuration loading creates
no files. The migration command creates the data directory and database. The
backend refuses to start if the database is missing or migrations are pending.

The browser requests `/api/v1/health`; Next.js forwards it to FastAPI. This avoids
cross-origin browser configuration. `BACKEND_URL` accepts an HTTP(S) origin with
no credentials, path, query, or fragment. Restart development after changing it;
production rewrites require a rebuild. Do not put credentials in this setting.

The frontend also uses Next.js's experimental `proxyClientMaxBodySize` and
`proxyTimeout` settings for upload forwarding. The clone buffer is the file limit
plus 64 KiB of multipart overhead; the upstream timeout is three minutes. A
12 MiB generated EPUB was verified through the production proxy. Next.js can
buffer substantial request data in memory, so the eventual production reverse
proxy should route `/api` directly to FastAPI and apply its own body/time limits.
This local configuration is not a replacement for that deployment work.
See [Next.js proxy body limits](https://nextjs.org/docs/app/api-reference/config/next-config-js/proxyClientMaxBodySize).

If port 8000 is occupied, select another backend port with `--port` and update
`BACKEND_URL`. If port 3000 is occupied, use `npm.cmd run dev -- --port 3001`.
Also add that exact frontend origin to `EBOOK_TRUSTED_ORIGINS` and restart the
backend. Do not stop unrelated services to free ports.

Dependencies are local to `.venv/` and `frontend/node_modules/`. npm's lockfile
and the fully pinned Python `requirements.txt` capture the tested versions.
`backend/requirements.in` lists intentional direct dependencies; changing it
alone does not update the installed or locked environment. Dependency updates
must regenerate the lock from a clean environment and rerun checks.

## Authentication and catalog

Passwords are hashed with Argon2id. Random session secrets live in HttpOnly,
SameSite=Strict cookies scoped to `/api`; only SHA-256 token hashes are stored in
SQLite. Sessions expire after an absolute lifetime and are revoked immediately
on logout. There are no tokens in localStorage.

Login begins with a short-lived anonymous session and a CSRF token fetched with
an application-specific header. Login and logout require both an exact trusted
Origin and the session-bound CSRF header. Successful login rotates the session.
All API responses use `Cache-Control: no-store`. CORS is not enabled.

Login verification is limited to 10 attempts per fixed five-minute window across
the application. This deliberately simple global throttle persists in SQLite
and counts successful attempts too. A burst can temporarily block the owner;
wait up to five minutes. It does not rely on spoofable forwarded IP headers.

Public endpoints are health, CSRF bootstrap, login, and API documentation.
`GET /api/v1/auth/me`, `POST /api/v1/auth/logout`, `GET /api/v1/books`, and
`GET /api/v1/books/{id}` require authentication. Book queries filter by owner;
responses exclude storage paths and hashes. Catalog listing supports `limit`
(1–100, default 20) and `offset` (default 0).

`GET /api/v1/upload-policy` reports the authenticated upload limit.
`POST /api/v1/books` accepts a multipart field named `file` and requires the same
Origin and CSRF protections as logout. It returns HTTP 201 for a new book or 200
with `duplicate: true` for an existing file hash. `GET /api/v1/books/{id}/cover`
serves only a generated JPEG after an ownership check. EPUB reading uses separate
authorized routes described below; original document access remains unexposed.
No demo books are added to your real library.

## Upload validation and storage

Files are detected by signature and document structure, independently of their
name or supplied MIME type. The original filename is display metadata only;
filesystem names are generated by the application. Each API process permits
one active upload/inspection, returning a retryable 503 for another upload.

The transport counts actual body bytes, including chunked requests, before
multipart processing. A separate streamed file check enforces the configured
file limit. Only one file is accepted; extra multipart fields/files are rejected.

EPUB inspection checks ZIP paths, duplicate names, special files, encryption,
CRC integrity, container/package XML, manifest resources, and reading order.
Missing manifest IDs and ambiguous duplicate IDs are rejected. Duplicate IDs
used only for raster cover images are tolerated with an upload warning when no
spine, TOC, fallback, or media-overlay reference uses that ID. The first listed
cover supplies the thumbnail; the original EPUB is not rewritten.
Entity definitions and external manifest resources are rejected. Legacy DOCTYPE
declarations are allowed without fetching their external DTDs. Archive limits
are 5,000 entries, 64 MiB per member, 512 MiB expanded total, a 1,000:1 expansion
ratio, and 2 MiB per parsed XML file. Known font obfuscation is distinguished
from unsupported DRM. This is a bounded ingestion validator, not full EPUBCheck.

EPUB metadata includes available title, creators, publisher, description, and
language. Covers are recognized through EPUB 3 `cover-image` or EPUB 2 cover
metadata. Supported raster covers are re-encoded as JPEG; missing, oversized,
SVG-only, or unusable covers get a placeholder. Image decoding is limited to
20 million pixels, and cover input to 20 MiB. XHTML guide-only covers are not
extracted yet. Filename and unknown-author fallbacks handle incomplete metadata.

PDFium opens PDFs, rejects encrypted documents, reads available title/author/
subject metadata and page count, and attempts a first-page JPEG thumbnail.
PDFs with no pages or over 20,000 pages are rejected. PDF metadata does not have
a reliable standard publisher field; producer/software names are not substituted.
Image-only scanned PDFs are accepted, without OCR or searchable-text claims.
Not every page is rendered during validation; a successful upload is not a
guarantee that a future reader will render every unusual page correctly.

Both formats are inspected in an owned subprocess with a deadline. PDFium is
never called concurrently from multiple API threads. This process boundary
provides crash/time isolation, not an OS security sandbox or a hard memory cap.
Linux deployment resource restrictions and parser dependency updates remain
important. No book scripts, external resource downloads, or active covers are
used by the library. The reader uses a separate sanitized artifact rather than
serving original EPUB content directly.

```text
data/
├── library.sqlite3
├── staging/                       # Temporary, generated upload directories
└── books/
    └── <generated-book-id>/
        ├── original.epub          # Or original.pdf, preserved byte-for-byte
        ├── cover.jpg              # Present only when generation succeeds
        ├── reader-v2.epub         # Generated when an EPUB is first opened
        └── reader-v2.json         # Version, source hash, and notices
```

Files are staged and flushed, inspected, then moved into their final directory
before the metadata transaction commits. Rejected uploads and normal failed
writes clean up their generated files. Cleanup checks for database references
before deleting published files; if a commit succeeded but its acknowledgement
failed, those files are preserved and a duplicate retry recovers the book.
If the database cannot be checked, cleanup is deferred rather than risking data
loss. SQLite and filesystem moves cannot share
one atomic transaction: a crash between the move and commit can leave an
unreferenced directory. No partial catalog record is published in that case.
This is not a guarantee against disk failure or sudden power loss.

With the backend stopped, run this read-only check from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m app.cli audit-storage
```

It reports missing originals/covers, unreferenced book directories, and leftover
staging entries, returning a nonzero exit status if issues exist. It does not
delete or repair anything. Preserve flagged data for investigation or restore
from a known backup; automated deletion is deliberately not implemented.

## Manual acceptance check

1. Create the owner using the terminal command above.
2. Open the frontend, enter a wrong password, and check the generic error.
3. Sign in correctly and confirm the empty catalog.
4. Reload and confirm you remain signed in.
5. Stop and restart both services, then reload and confirm the session persists.
6. Sign out and confirm the sign-in form returns.
7. Open `/api/v1/books` in a private browser window; expect HTTP 401.
8. Upload a small DRM-free EPUB and PDF. Both should appear with metadata and
   covers, or an explicit placeholder when a cover is unavailable.
9. Re-upload one file; confirm an already-in-library message and no extra card.
10. Try a text file renamed to `.pdf`; confirm rejection without an extra card.
11. Reload and restart both services; confirm the books and covers remain.
12. Select **Read book** on an EPUB. Use Previous/Next, Contents, and an internal
    chapter link if present, then return with **Library**.
13. Resize the desktop browser or rotate a phone and check that the page remains
    usable. Test the actual iPhone Safari and Android browser when private HTTPS
    access is configured; the loopback URL is local to Windows.

The grid is paginated once there are more than 20 books. Refresh library retrieves
the current page; successful uploads return to the first page. Uploads show a
processing state rather than an estimated percentage. If a connection times out,
refresh before retrying: the server may already have saved the book, and the hash
check makes retrying identical bytes safe. Both formats have a Read book link;
the matching reader opens automatically. Navigate, wait for **Synced**, and
reopen/refresh to verify restoration. Repeat with a PDF page and scroll position.
Cross-device conflicts offer **Load saved position** or **Keep this position**.

The backend cookie is scoped to `/api`, so test authenticated API access through
the frontend origin, not a different hostname. Tests passed on Windows; Android
and iPadOS 12.5.8 have not been verified. Core reading development now prioritizes
Windows, Android, and modern iPhone Safari; dedicated older-iPad compatibility work follows the usable
online MVP. See the development plan for the retained compatibility requirements.

A private HTTPS test-access procedure is prepared in
[docs/private-test-access.md](docs/private-test-access.md). It has not been
activated and is not a prerequisite for local reader development.

## EPUB reader and content boundary

Opening an EPUB first checks authentication and builds a versioned reading copy
in a bounded subprocess. The original file's SHA-256 must match the catalog.
The copy contains semantic XHTML, locally re-encoded JPEG images, generated
navigation, and a controlled serif layout. Publisher scripts, event attributes,
forms, frames, external links/resources, and embedded fonts are omitted. Safe
publisher CSS and static SVG are retained through explicit allowlists. GIFs become
static images. MathML and interactive content remain unsupported. Fixed-layout EPUBs are rejected with an explanatory error.

Existing EPUB 3 navigation or EPUB 2 NCX supplies the contents list when readable;
otherwise chapter headings provide a fallback. Source chapter paths and internal
fragment links are mapped to generated paths. Nested contents entries are preserved. Manifest fallback chains are followed;
unsupported spine items have visible notice chapters rather than silently disappearing.

`GET /api/v1/books/{id}/epub` prepares or retrieves metadata for the authorized
reading copy. `GET /api/v1/books/{id}/epub/2/content` returns only that generated
EPUB. Invalid artifact versions and non-EPUB books do not fall back to originals.
The interface checks the expected versioned URL before loading EPUB.js. Reading
copies are private, have no-store responses, and are cached beside the original
for subsequent opens. Preparation and uploads share a processing gate.

Each chapter has a strict CSP including `script-src 'none'`, no connections,
no forms or child frames, and only local generated blob/data images. EPUB.js's
iframe sandbox retains navigation restrictions. Its `allowScriptedContent` flag
is enabled **only for our generated content** because WebKit otherwise blocks
even parent-managed input handlers. This flag is not permission to load raw
EPUBs: enabling it for unsanitized books is unsafe. The sanitizer, controlled
artifact route, and script-blocking CSP are required parts of the boundary.
Browser tests attempt script insertion and confirm it does not execute, while
verifying in-book touch links still work.

The EPUB.js adapter exposes page/chapter navigation, cleanup, and versioned CFI
location events independently of the React library interface. Resize observation
begins after the first reported CFI, avoiding a blank-view initialization race.
Within an open reader, the engine reflows and repositions content on resize.
Displayed page numbers belong to the current chapter and change with viewport
size; they are not stable book-wide page numbers.

**Reading progress is saved after server confirmation.** EPUB CFI and PDF page/
normalized offset persist in SQLite per owner/book. A debounced local journal
retries unavailable-server saves. Revision conflicts require an explicit choice.
See [progress design and verification](docs/reading-progress.md) for details.
This is progress retry support, not offline book downloading or a PWA cache.

Reading-copy version 2 must remain structurally stable once CFIs are persisted.
Sanitizer/parser changes that alter the document tree require a new artifact
version and an explicit location migration strategy. Preserve reading copies in
backups, particularly after progress and annotations are added. The initial
generated-content limit is 64 MiB and the chapter limit is 2,000.

## Database and recovery

The initial migration creates `users`, `sessions`, `login_throttle`, and `books`,
plus Alembic's schema-version table. The database enforces one owner, foreign
keys, valid book formats, nonnegative sizes, positive PDF page counts when
present, and per-owner file-hash uniqueness. Migration 0002 adds `reading_progress`
with locations, percentages, operation IDs, revisions, and server timestamps.

SQLite currently uses its default rollback journal, five-second lock timeout,
and short transactions. Password hashing runs outside database transactions.
WAL is not needed for this milestone; we can evaluate it with real upload and
reading traffic later.

Use the offline backup/verification/restore CLI in [backup and recovery](docs/backup-recovery.md).
The API must be stopped; a cross-process data lease enforces this for current
versions. Run one API worker per data directory. Restores require an empty
destination and revoke restored sessions while preserving owner credentials,
books, progress, preferences and reading copies. Archives are private, unencrypted
data; keep an independent protected copy outside this server disk. Do not delete
the database to reset a password; password-reset recovery remains separate work.

## Files to explore

- `backend/app/main.py`: application factory, startup schema check, health response,
  and private response defaults.
- `backend/app/config.py`: environment settings and validation.
- `backend/app/models.py`: SQLAlchemy mappings and data-integrity constraints.
- `backend/app/database.py`: connections, foreign keys, and explicit migrations.
- `backend/migrations/versions/0001_catalog_and_auth.py`: initial schema change.
- `backend/app/security.py`: password hashing, token derivation, owner provisioning.
- `backend/app/api.py`: session endpoints, CSRF, throttle, and owner-scoped catalog.
- `backend/app/cli.py`: terminal migration and owner-creation commands.
- `backend/app/body_limits.py`: pre-parser transport limits using Starlette.
- `backend/app/documents.py`: bounded EPUB/PDF inspection and raster covers.
- `backend/app/storage.py`: staging, process deadlines, hash deduplication,
  filesystem/database coordination, and a read-only storage audit.
- `backend/app/workers.py`: owned process startup, deadline, and termination.
- `backend/app/epub_artifact.py`: versioned sanitization, image conversion, TOC,
  and stable chapter mapping for the reading copy.
- `backend/app/reader_service.py`: private cache creation and retrieval.
- `backend/tests/`: isolated HTTP, integrity, and persistence checks.
- `frontend/next.config.ts`: same-origin API forwarding and upstream validation.
- `frontend/src/app/page.tsx`: server-rendered foundation page.
- `frontend/src/components/backend-status.tsx`: browser health request, timeout,
  retry, and cleanup when the component unmounts.
- `frontend/src/components/library-access.tsx`: login/logout and catalog states.
- `frontend/src/components/book-upload.tsx`: file selection, upload, and feedback.
- `frontend/src/components/book-grid.tsx`: cover cards and missing-cover fallback.
- `frontend/src/components/epub-reader.tsx`: reader UI, loading/errors, and controls.
- `frontend/src/readers/epub/adapter.ts`: EPUB.js lifecycle and location events.
- `frontend/src/readers/types.ts`: reader and location contracts.
- `frontend/tests/e2e/reader.spec.ts`: isolated browser acceptance workflow.
- `frontend/src/lib/api.ts`: same-origin API client with timeouts and error handling.
- `docs/development-plan.md`: scope, learning checkpoints, and compatibility decision.

## Git

The repository uses `main`, with one commit per completed milestone. Review
future changes with `git status` and `git diff`. Before committing, inspect the
staged file list:

```text
git add .
git diff --cached --stat
git commit -m "Describe the completed change"
```

Local environment files, dependencies, caches, and future `data/` are ignored.
The source repository is https://github.com/nnamdijess/e-library. Books, databases,
backups, credentials and reading history remain outside version control.
