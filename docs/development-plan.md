# Incremental development plan

Milestones 1 and 2 are approved and implemented. Each later milestone needs
review before work starts. Uploads, readers, and progress remain future scope.

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
and controlled file access. SQLite will store metadata and user state; a private
filesystem directory will store documents and generated covers. Milestone 2 adds
the database and an empty read-only catalog; document storage is future work.
EPUB and PDF get separate engines with a shared progress API.

Progress will use EPUB CFI or a PDF page and normalized position. Server revisions
will reject stale writes, independent of client clocks. Full offline queuing and
cross-device conflict resolution come later.

## iPadOS 12.5.8 requirement

The owner reports an iPad running iPadOS 12.5.8. This is a required compatibility
target to investigate, not a supported platform claim for the current scaffold.
Windows and Android are the initially available test devices.

Current Next.js documentation specifies Safari 16.4+; the current PDF.js legacy
build lists Safari 18+ with qualifications. Therefore, current default builds
cannot be assumed to work on the older iPad. A lower TypeScript target alone
does not fix framework dependencies, browser APIs, or rendering-engine support.

Before reader implementation, review these options with the owner:

1. Investigate a separately bundled legacy reader/interface against the same
   REST API. This increases build and maintenance work and still needs device tests.
2. Reconsider the frontend/rendering approach if full iPad feature parity is
   mandatory. Propose tradeoffs and obtain approval before changing the stack.
3. Agree on a reduced iPad feature set if the owner prefers that compromise.

Do not silently drop the requirement, claim compatibility from browser emulation,
or pin unsupported old packages just to target the device. The modern scaffold
is a foundation for local development, not a final compatibility decision.

Sources checked during Milestone 1:

- [Next.js supported browsers](https://nextjs.org/docs/architecture/supported-browsers)
- [PDF.js browser support](https://github.com/mozilla/pdf.js/wiki/Frequently-Asked-Questions#which-browsersenvironments-are-supported)

## Operational boundaries

Local development binds to 127.0.0.1. Authentication and SQLite persistence exist;
production hardening, Docker, and Tailscale configuration remain future work. Never modify
Vaulted, Nextcloud, or other existing services as part of this project without
separate explicit authorization. No server access is assumed.
