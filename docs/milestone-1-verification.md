# Milestone 1 verification

Verified locally on Windows using Node.js 24.13.0 and Python 3.13.15.

| Check | Result |
| --- | --- |
| Backend health contract (`python -m pytest -q`) | 1 passed |
| Python dependency consistency (`python -m pip check`) | Passed |
| Frontend route generation and TypeScript check | Passed |
| Next.js production build | Passed |
| Live backend health request | HTTP 200, `{"status":"ok"}` |
| Live frontend page request | HTTP 200, expected page content |
| Live same-origin `/api/v1/health` proxy request | HTTP 200, matching backend JSON |
| Request through proxy while backend stopped | HTTP 500 from Next.js; the client handles any non-success response as unavailable |
| Private/generated file exclusions | Environment files, dependencies, caches, and generated declarations ignored by Git |

The sandbox initially blocked a Next.js worker and pytest cache creation.
Both checks passed when rerun with the necessary process/filesystem permissions.

The UI automation browser host was unavailable, and native browser access timed
out. The rendered page, client hydration, retry button, and responsive layout
were not visually verified. Use the README's manual check to confirm the
connection indicator and stop/restart recovery in a browser.

No EPUB/PDF engines, database, authentication, offline behavior, Android test,
older-iPad test, or Linux/server deployment are covered by this milestone.
