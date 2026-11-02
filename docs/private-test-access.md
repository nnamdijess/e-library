# Prepared private HTTPS test access

This is a reviewable procedure, not an enabled configuration. No Tailscale,
firewall, router, or Ubuntu service settings were changed during preparation.
Local reader development continues independently of remote access.

## Read-only inspection findings

- The Windows Tailscale service is running; the installed client is 1.104.2.
- The frontend, backend health endpoint, and same-origin API proxy return HTTP 200.
- `tailscale serve status --json` returned an empty object.
- An entry named `iPad` is listed, but was marked offline at inspection time.
  Other iOS peers are also present; their names alone do not identify the device.
- The service reported that it could not reach its coordination server and had
  not received a network map for more than nine hours. Cached peer connections
  may still work, but current reachability and certificate provisioning were not
  established. These are point-in-time findings; recheck before activation.

The exact device hostname and prepared backend profile are kept locally under
ignored `.cache/`, rather than committed to the repository.

## Proposed connection

```text
Tailnet browser
    -> https://<device>.<tailnet>.ts.net:8443
    -> Tailscale Serve
    -> http://127.0.0.1:3000 (Next.js)
    -> /api forwarded to http://127.0.0.1:8000 (FastAPI)
```

Both application services remain bound to loopback. Port 8443 provides a separate
test listener. Tailscale Serve is private to the tailnet and subject to its access
rules; Funnel is public sharing and is not part of this procedure. The app's
existing owner login remains required.

## Activation steps for a later approved test

1. Recheck `tailscale status` and `tailscale serve status`. Resolve the reported
   coordination problem and confirm the intended test device is connected.
   Do not reset Tailscale or clear other services to troubleshoot this app.
2. Confirm port 8443 has not acquired another Serve configuration since inspection.
3. Ensure HTTPS certificate support is enabled for the tailnet. Serve can present
   an authorization link if prerequisites are missing; this was not activated or
   accepted during preparation.
4. Stop the local backend, then start it in a fresh PowerShell terminal with the
   prepared temporary environment profile. From the repository root:

   ```powershell
   Set-Location backend
   ..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --env-file ../.cache/private-test-backend.env --host 127.0.0.1 --port 8000
   ```

   The profile sets the exact HTTPS origin and `EBOOK_SESSION_COOKIE_SECURE=true`.
   Other settings, the database, and the owner account remain in their existing
   locations. This profile is process-local; it does not edit `backend/.env`.
   Existing shell environment overrides take priority, hence the fresh terminal.
5. Keep the frontend running on loopback port 3000 using `npm.cmd start` after a
   build. In a separate terminal, the prepared Serve command is:

   ```powershell
   tailscale serve --https=8443 http://127.0.0.1:3000
   ```

   This runs in the foreground for the test. Keep the terminal open. It was not
   run during preparation.
6. Open the exact HTTPS URL recorded in `.cache/private-test-access.md`. Use that
   URL on Windows too during the HTTPS test; the temporary profile accepts that
   origin rather than the ordinary loopback HTTP origin. Sign in normally. Do
   not bypass certificate warnings. First confirm API health, login, and library
   access on a current Windows or Android browser.
7. An iPad test is optional later. Successful networking will not by itself prove
   Safari 12 supports the current interface. An older client that connects is
   useful evidence, not a maintained-client support guarantee.

## Return to ordinary development

Stop the foreground Serve command with Ctrl+C. Confirm removal with
`tailscale serve status`. If a route remains, remove only this test listener:

```powershell
tailscale serve --https=8443 http://127.0.0.1:3000 off
```

Do not use `tailscale serve reset`, which could clear unrelated configuration.
Stop the temporary backend, close its terminal, and start the normal backend
without `--env-file` using the README instructions. Return to
`http://127.0.0.1:3000`. No database or session-table reset is required.

Sources: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[Serve command reference](https://tailscale.com/docs/reference/tailscale-cli/serve).
