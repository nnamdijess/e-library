# Incremental development plan

Milestones 1–3 are approved and implemented. Each later milestone needs review
before work starts. Readers and progress remain future scope.

The owner has prioritized a working, usable app on Windows and Android. Complete
the online EPUB/PDF reading and progress milestones before dedicated older-iPad
compatibility work. iPad compatibility remains a goal and is not a gate on the
next reader milestone. A separate legacy interface is an option, not an approved
implementation. Avoid adding offline, annotation, or statistics work ahead of
the online MVP.

| Milestone | Acceptance | Learning focus |
| --- | --- | --- |
| 1. Foundation | Frontend reaches local API; health test, type check, build, setup documentation | HTTP boundary, application factory, configuration, Git |
| 2. Authentication and catalog | Owner login, protected routes, SQLite, first migration, restart persistence | Sessions, relational design, schema migration |
| 3. Unified library | Validated EPUB/PDF ingestion, metadata, covers, persistent storage and library grid | Untrusted inputs, files and transactions |
| 4. EPUB reader | Pagination, chapter navigation, TOC, CFI reporting | Rendering lifecycle and stable anchors |
| 5. PDF reader | Page navigation, fit-to-width, range delivery, normalized positions | Workers, coordinates, memory budgets |
| 6. Durable progress | Save/restore both formats, stale-write rejection, restart and browser acceptance tests | Concurrency, idempotency, failure recovery |
| 7. Deployment | Isolated Compose setup, private HTTPS access, tested backup/restore | Containers, operations, recovery |

Milestone 6 completes the online local MVP. Collections, annotations, offline
reading, statistics, and advanced synchronization are future scope.

## Architecture boundaries

Next.js owns the interface. FastAPI owns authorization, ingestion, persistence,
and controlled file access. SQLite stores metadata and user state; a private
filesystem directory stores immutable originals and generated JPEG covers.
Milestone 3 adds staged ingestion, cover delivery, and a unified catalog grid.
EPUB and PDF get separate engines with a shared progress API.

Progress will use EPUB CFI or a PDF page and normalized position. Server revisions
will reject stale writes, independent of client clocks. Full offline queuing and
cross-device conflict resolution come later.

## iPadOS 12.5.8 requirement

The owner reports an iPad running iPadOS 12.5.8 and has connected it to Tailscale
using an older client. This observed connection is useful, but does not establish
browser/reader compatibility or continued network reachability. Windows and
Android are the first acceptance targets. Dedicated iPad compatibility testing
is deferred until the core online reading workflow is usable.

Current Next.js documentation specifies Safari 16.4+; the current PDF.js legacy
build lists Safari 18+ with qualifications. Therefore, current default builds
cannot be assumed to work on the older iPad. A lower TypeScript target alone
does not fix framework dependencies, browser APIs, or rendering-engine support.

Keep these options for the later compatibility review:

1. Investigate a separately bundled legacy reader/interface against the same
   REST API. This increases build and maintenance work and still needs device tests.
2. Reconsider the frontend/rendering approach if full iPad feature parity is
   mandatory. Propose tradeoffs and obtain approval before changing the stack.
3. Agree on a reduced iPad feature set if the owner prefers that compromise.

Do not silently drop the requirement, claim compatibility from browser emulation,
or pin unsupported old packages just to target the device. Do not rewrite the
current frontend or build a legacy client before that review. Continue to keep
reading engines separate from the library interface, use versioned EPUB/PDF
locations, and share server-side authorization and progress rules. This preserves
the option of a lightweight interface later without duplicating the library.

## Next implementation checkpoint

Proposed Milestone 4 scope: open a library EPUB in a browser reader, navigate
pages and chapters, show its table of contents, return to the library, and expose
CFI location events behind a reader adapter. Safe content delivery and script/
external-resource restrictions are prerequisites. Test on current Windows and
Android browsers. Durable progress belongs to Milestone 6; PDF rendering belongs
to Milestone 5. The next major implementation still needs the owner's approval.

Sources checked during Milestone 1:

- [Next.js supported browsers](https://nextjs.org/docs/architecture/supported-browsers)
- [PDF.js browser support](https://github.com/mozilla/pdf.js/wiki/Frequently-Asked-Questions#which-browsersenvironments-are-supported)

## Operational boundaries

Local development binds to 127.0.0.1. Authentication, SQLite persistence, and private file storage exist;
production hardening, Docker, and Tailscale configuration remain future work. Never modify
Vaulted, Nextcloud, or other existing services as part of this project without
separate explicit authorization. No server access is assumed.

A read-only Windows Tailscale inspection found no existing Serve configuration.
The service reported a stale network map and inability to reach its coordination
server, so a listed peer is not proof of current reachability. A private HTTPS
test-access procedure is prepared in `private-test-access.md`; it has not been
activated. This networking follow-up must not block local reader development.
