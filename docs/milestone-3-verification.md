# Milestone 3 verification

Completed scope: authenticated EPUB/PDF ingestion, available metadata, JPEG
covers/placeholders, private original storage, deduplication, and a unified grid.
Readers, progress, metadata editing, deletion, offline mode, and collections
remain planned. No database schema change was needed; migration 0001 already
contained the catalog fields. Existing owner credentials and sessions are retained.

## Automated and live checks

Final results on Windows: **49 backend tests passed**, Python dependency checking
passed, and frontend route generation, type checking, and production build passed.

The backend suite uses generated original EPUBs and image-only PDFs in temporary
databases. It covers authentication and catalog behavior from earlier milestones,
plus both upload formats, metadata, JPEG dimensions, safe filenames, exact
original-byte preservation, duplicate hashes, and restart persistence.

Negative tests cover malformed documents, empty files, missing EPUB resources,
ZIP traversal/drive/backslash/NUL paths, ambiguous names, excessive compression,
symlinks, XML external entities, unsupported EPUB encryption, PDF encryption error
handling, and unusable covers. Known EPUB font obfuscation is accepted. PDF
encryption tests exercise PDFium's password/security results through mocks rather
than a downloaded encrypted fixture.

Transport tests include file-size enforcement, chunked requests without a
Content-Length, extra multipart files, CSRF rejection, and an overlapping upload.
Failure tests verify worker termination on timeout, cleanup after a database
commit failure, preservation after a successful commit with a failed acknowledgement,
and read-only crash-leftover auditing.

The frontend passed route generation, TypeScript checking, and a production build.
The live Next.js production proxy and a real Uvicorn process were exercised with
an isolated test owner/database. Checks passed for EPUB and PDF uploads, generated
JPEG retrieval, a >10 MiB EPUB upload, duplicate detection, malformed-file
rejection, and persistence after terminating/restarting the backend process.
The temporary library was removed after the test; no test books were added to
the owner's real catalog.

## Responsibilities and tradeoffs

- `documents.py` validates document internals and creates bounded raster covers.
- `storage.py` coordinates private staging, worker lifecycle, final file moves,
  metadata commits, and cleanup. SQLite and the filesystem are separate systems;
  moving files first avoids publishing a row before its files exist, at the cost
  of possible crash leftovers that `audit-storage` reports without deletion.
- `api.py` authenticates and checks CSRF before manually parsing multipart data.
- `body_limits.py` uses Starlette's request-byte counter before form parsing.
- The frontend separately handles upload feedback, paginated catalog refresh,
  cover loading, and missing-image fallbacks.

This milestone practices defensive parsing, resource lifecycles, streaming I/O,
idempotent retries through content hashes, failure recovery, and the boundary
between database transactions and filesystem operations.

The current Next.js upload forwarding depends on its experimental proxy body-size
and timeout settings. Production should route API traffic directly to FastAPI
through an isolated reverse proxy, with independent ingress limits. Worker
timeouts do not provide an OS security sandbox or a portable hard memory cap.
The original EPUB is intentionally not yet served as browser content; reader
sanitization and stable anchor versioning must be resolved in the reader milestone.

## Manual verification still required

Browser automation reports that its access host is unavailable. The rendered
upload form, grid, responsive layout, and client hydration have not been visually
verified. Follow the README's manual upload/reload/restart sequence on Windows.
Android, iPadOS 12.5.8, and Linux/server execution remain unverified. The iPad
compatibility decision is still required before reader implementation.
