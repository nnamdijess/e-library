# Ubuntu deployment alongside existing services

This is a prepared deployment, not a change made to your server. Docker/container
builds have not been run in the Windows development environment. The Compose
configuration has been validated locally; run the manual Linux check below and
review the server's actual environment before relying on a deployment.

The stack has a nonroot FastAPI API, a standalone Next.js frontend, and an Nginx
gateway. Only the gateway publishes a host port, bound to `127.0.0.1`. Tailscale
Serve supplies private HTTPS. `/api` routes directly to FastAPI, avoiding Next.js
upload buffering. Books/database are a dedicated bind mount; backups use another
dedicated bind mount. The API and frontend have no public host ports.

## 1. Inspect and clone

On Ubuntu, check the existing installation without stopping anything:

```bash
uname -m
docker version
docker compose version
tailscale status
tailscale serve status
ss -ltnp
```

Docker with the Compose plugin and an authenticated Tailscale installation are
prerequisites. If absent, use the [official Ubuntu Docker instructions](https://docs.docker.com/engine/install/ubuntu/)
or ask for help with that separate installation. Do not replace an existing
Docker/Tailscale installation used by other services. This initial target is a
current Ubuntu system; the Linux workflow uses amd64, and ARM builds are unverified.

Choose unused ports for this app. Examples below use local HTTP 8787 and private
HTTPS 8443; neither is assumed free. Preserve existing Serve routes for Vaulted,
Nextcloud or any other service. If 8443 is already assigned, choose another
supported Serve port or review a dedicated hostname/service setup first.

```bash
git clone https://github.com/nnamdijess/e-library.git
cd e-library
test -e deploy/.env || cp deploy/.env.example deploy/.env
```

Use your existing Git authentication for a private repository. Edit private
`deploy/.env`, supplying:

- The exact `https://SERVER.TAILNET.ts.net:8443` browser origin, with no trailing
  slash. Get your actual server DNS name from Tailscale; do not use the example.
- Dedicated absolute `EBOOK_DATA_PATH` and `EBOOK_BACKUP_PATH` paths, such as
  `/srv/ebook-library/data` and `/srv/ebook-library/backups`.
- `EBOOK_UID` and `EBOOK_GID` of the account that owns those directories. Check
  them with `id -u` / `id -g`; do not assume the example numeric IDs match.
- The chosen unused `EBOOK_HTTP_PORT`. Keep secure cookies enabled for HTTPS.

Create only those dedicated directories, privately, owned by that account.
For a **new, unused** example location owned by your current login:

```bash
sudo install -d -m 0700 -o "$(id -u)" -g "$(id -g)" /srv/ebook-library/data /srv/ebook-library/backups
```

If those paths exist, inspect them first; do not change ownership/permissions of
an existing service's storage. Bind sources must exist: Compose refuses to
silently create missing host paths. API/maintenance containers use the configured
numeric IDs. Code images and gateway remain nonroot with read-only roots,
dropped capabilities, bounded process/memory use and an isolated internal network.
The initial memory ceilings are API 1 GiB, frontend 512 MiB and gateway 128 MiB;
check available RAM and tune only this stack if necessary.

## 2. Build and choose new library versus transfer

From the clone root, define this convenience function in your current shell:

```bash
dc() { docker compose --env-file deploy/.env -f deploy/compose.yaml "$@"; }
dc config --quiet
dc build
```

Do not start the API before database initialization. For a **new empty library**:

```bash
dc run --rm --no-deps maintenance python -m app.cli migrate
dc run --rm --no-deps maintenance python -m app.cli create-owner --username owner
```

The second command prompts for the password. Never put it in `.env`, shell
arguments or Git.

To **transfer your current Windows library**, use the backup/recovery CLI described
in [backup and recovery](backup-recovery.md): stop the Windows API, create and
verify an archive, then copy it to the Ubuntu backup directory through your
existing trusted file-transfer method. For example, use SCP only if SSH is
already configured, or transfer it using a local drive. Do not add it to Git.
Once the archive is present on Ubuntu, restore into the initially empty data mount:

```bash
dc run --rm -T --no-deps maintenance python -m app.cli verify-backup /backups/NAME.elbackup.zip --work-dir /backups
dc run --rm -T --no-deps maintenance python -m app.cli restore /backups/NAME.elbackup.zip --destination /data
dc run --rm -T --no-deps maintenance python -m app.cli migrate
dc run --rm -T --no-deps maintenance python -m app.cli audit-storage
```

Keep your existing owner account/password when transferring. Restore revokes
login sessions but preserves books, reading positions and account preferences.

## 3. Start and enable private HTTPS

```bash
dc up -d --wait --wait-timeout 120
dc ps
curl --fail http://127.0.0.1:8787/api/v1/health
```

Substitute the chosen HTTP port if different. Health should return `{"status":"ok"}`.
For first-run failures, use `dc logs --tail 100 api web gateway`; do not delete
the database to make the API start. Missing/outdated schema requires the explicit
migration command while the API is stopped.

After confirming your chosen HTTPS listener is unused, set only this Serve route:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8787
tailscale serve status
```

Tailnet HTTPS support and permission may require an authorization flow from
Tailscale. Use the URL printed by Serve and make `EBOOK_PUBLIC_ORIGIN` match it
exactly. If you edit the origin, recreate the API with `dc up -d --force-recreate`.
Use HTTPS for sign-in; secure cookies intentionally do not support logging in
through ordinary host-loopback HTTP in this profile.

Access remains subject to your tailnet rules and the app's owner login. Configure
tailnet access for only the intended devices/users. Serve is private sharing;
public Funnel exposure is outside this setup. To remove only this HTTPS listener:

```bash
sudo tailscale serve --https=8443 off
```

Do not reset Serve globally. The gateway is exclusively for a trusted host-side
HTTPS terminator and sets the forwarded protocol to HTTPS. The API trusts proxy
headers only because it is isolated behind that gateway with no host port.

## 4. Acceptance, backups and updates

On Windows/Android/iPhone, open the exact private HTTPS URL and sign in. Verify:

1. Existing library, edited titles, covers and preferences.
2. EPUB and PDF rendering, a navigation change, and **Synced** before closing.
3. Reopening and switching devices restores the saved position.
4. `dc restart` preserves books and positions.
5. `sh deploy/backup.sh` creates a verified archive and restarts this API.
6. A restore drill into a separate data directory succeeds before relying on it.

The current Next.js and PDF.js browser baselines still apply; deployment does not
add older-iPad compatibility. Test the actual iPhone rather than relying solely
on viewport emulation.

For an upgrade, record the current Git revision and create a verified backup
**before** changing code/images. Then update only this clone/stack:

```bash
sh deploy/backup.sh
git rev-parse HEAD
git pull --ff-only
dc build
dc stop gateway web api
dc run --rm -T --no-deps maintenance python -m app.cli migrate
dc up -d --force-recreate --wait --wait-timeout 120
```

Explicit recreation refreshes the gateway's upstream service addresses after
container replacement. Data bind mounts stay in place. Avoid global Docker
prunes, stopping all containers, or changing another project's Compose files.
For recovery/rollback, preserve the old data and restore into a fresh directory
using matching code, as described in the recovery guide.

## Optional manual Linux validation

The repository includes **Manual Linux deployment checks** under GitHub Actions.
It runs only with **Run workflow**; pushing does not automatically start it.
It uses generated test content and an isolated ephemeral stack, tests the backend,
builds the images, checks health/auth denial, and runs the backup helper.
It uploads no personal books, data or backups. Check your account's Actions
availability/quota before choosing to run it. This Windows session has not run
that workflow or verified the images on your Ubuntu server.

References: [Compose services](https://docs.docker.com/reference/compose-file/services/),
[Nginx proxy behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve),
[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve).
