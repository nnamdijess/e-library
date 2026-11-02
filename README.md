# Ebook Library

A personal, self-hosted EPUB and PDF library, developed incrementally.

**Completed scope: Milestone 1 foundation.** The Next.js page checks a FastAPI
health endpoint through a same-origin API proxy. There is no database, login,
upload, reader, or reading-progress storage yet. Keep this unauthenticated
scaffold on loopback; remote access and deployment belong to later milestones.

## Prerequisites

- Node.js 22 or 24 LTS with npm (tested with Node 24.13.0).
- Python 3.12 or 3.13 (tested with Python 3.13.15).
- Git.

No Docker, WSL, external database, or cloud service is required for development.
The commands below start from the repository root unless stated otherwise.

## Windows setup (PowerShell)

Create an isolated Python environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
Set-Location frontend
npm.cmd ci
```

Run setup only once. Do not overwrite your local configuration when updating.
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

Open <http://127.0.0.1:3000>. The page should report **API connected**.
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
The backend test verifies the health endpoint's HTTP status, content type, and
JSON contract using an in-process HTTPX ASGI client. Type checking and a
production build validate the frontend scaffold; type checking first generates
Next.js route declarations so it also works before the first build. These checks
do not establish reader
or older-iPad compatibility.

After building, `npm.cmd start` starts the production frontend on loopback at
port 3000. Stop the frontend development process first. The backend must still
be running. This is a local production-build check, not a server deployment.

## Configuration

| Setting | Location | Meaning |
| --- | --- | --- |
| `EBOOK_APP_NAME` | `backend/.env` or environment | API title; validated at application startup |
| `BACKEND_URL` | `frontend/.env.local` or environment | Server-only upstream API origin; defaults to `http://127.0.0.1:8000` |
| `NEXT_TELEMETRY_DISABLED` | Frontend environment | Set to `1` to disable Next.js telemetry |

The backend always resolves its `.env` relative to `backend/`, not the shell's
working directory. Unknown dotenv keys and invalid values fail early. No data
directories are created by configuration loading.

The browser requests `/api/v1/health`; Next.js forwards it to FastAPI. This avoids
cross-origin browser configuration. `BACKEND_URL` accepts an HTTP(S) origin with
no credentials, path, query, or fragment. Restart development after changing it;
production rewrites require a rebuild. Do not put credentials in this setting.

If port 8000 is occupied, select another backend port with `--port` and update
`BACKEND_URL`. If port 3000 is occupied, use `npm.cmd run dev -- --port 3001`.
Do not stop unrelated services to free ports.

Dependencies are local to `.venv/` and `frontend/node_modules/`. npm's lockfile
and the fully pinned Python `requirements.txt` capture the tested versions.
`backend/requirements.in` lists intentional direct dependencies; changing it
alone does not update the installed or locked environment. Dependency updates
must regenerate the lock from a clean environment and rerun checks.

## Files to explore

- `backend/app/main.py`: application factory and typed health response.
- `backend/app/config.py`: environment settings and validation.
- `backend/tests/test_health.py`: isolated HTTP contract test.
- `frontend/next.config.ts`: same-origin API forwarding and upstream validation.
- `frontend/src/app/page.tsx`: server-rendered foundation page.
- `frontend/src/components/backend-status.tsx`: browser health request, timeout,
  retry, and cleanup when the component unmounts.
- `docs/development-plan.md`: scope, learning checkpoints, and compatibility decision.

## Git

The repository starts on `main`. Review changes with `git status` and `git diff`.
Before the initial commit, inspect the staged file list:

```text
git add .
git diff --cached --stat
git commit -m "Add local frontend and API foundation"
```

Local environment files, dependencies, caches, and future `data/` are ignored.
No remote repository is configured automatically. Future books, credentials,
and reading history must remain outside version control.
