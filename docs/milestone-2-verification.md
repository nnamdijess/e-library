# Milestone 2 verification

Verified locally on Windows with Node.js 24.13.0 and Python 3.13.15.

## Automated checks

- 20 backend tests passed against temporary SQLite databases.
- Python dependency consistency check passed.
- Frontend route generation, TypeScript check, and production build passed.

The backend suite verifies:

- Anonymous catalog requests are rejected; health remains public.
- Correct login, case-insensitive username, session rotation, and hashed storage.
- Generic credential errors and validation responses that do not echo passwords.
- Login/logout Origin and CSRF enforcement, including pre-login protection.
- Server-enforced expiry and logout revocation, including replay of an old cookie.
- Persistent global login throttling and separate concurrent sign-in sessions.
- Catalog detail/list access, pagination validation, and private-field exclusion.
- Catalog and session survival across new app instances and repeated migrations.
- Migration/model consistency and enabled SQLite foreign keys.
- Invalid owners, formats, sizes, and page counts rejected by the database.
- Secure-cookie configuration, unsafe-origin rejection, and explicit startup migration requirements.

## Live process check

A disposable database and test-only owner were used with the real Next.js
production proxy and a real Uvicorn process. HTTP checks passed for cookie
forwarding, login, protected catalog access, persistence after terminating and
restarting the backend process, and logout. The verification process confirmed
the backend port was released before restarting. The disposable database was
removed afterward.

The default library database was migrated but no owner or demo records were
created in it. The owner must run the documented interactive command to choose
their own credentials.

## Remaining checks

Browser visual/hydration testing remains manual. Browser automation was
unavailable during Milestone 1 and was not retried here. Use the README's manual
acceptance sequence. No Android, older-iPad, or server deployment test is claimed.
Uploads, book content, readers, and progress storage are not implemented.
