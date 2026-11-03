# Backup and recovery

The server's data directory is authoritative. Backups contain a SQLite snapshot
(owner account, metadata, reading positions, preferences), original books, covers
and generated reading copies. They exclude temporary ingestion files, lock files,
local `.env` configuration and browser-only unsynchronized positions. Wait for
**Synced** before a planned transfer. Preserve configuration separately, privately.

Archives contain private books, reading history and password hashes. They are
not encrypted. Store them in a private directory and copy verified backups to a
separate device/disk; a copy on the same server disk does not protect against
that disk failing. Git is for source code, not library backups.

## Windows backup and restore drill

Stop the backend with Ctrl+C first, including old versions without the new lock.
The frontend may remain open; it queues progress while the API is unavailable.
From the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.cli backup --output ../backups/library-transfer.elbackup.zip
..\.venv\Scripts\python.exe -m app.cli verify-backup ../backups/library-transfer.elbackup.zip
..\.venv\Scripts\python.exe -m app.cli restore ../backups/library-transfer.elbackup.zip --destination ../.cache/recovery-drill
```

Choose a new archive filename and empty drill directory each time. Existing
backups and existing data are never overwritten. Restart the normal backend
after the backup. A drill in a separate directory does not replace the live
library. The restore summary reports revoked sessions; use the original owner
password when signing into a recovered library. Do not create a replacement owner.

`verify-backup` extracts into a disposable system temporary directory; use
`--work-dir PATH` if that filesystem is too small. Backup creation temporarily
needs space for an uncompressed snapshot plus the archive and published copy.
Verification/restore need space for the uncompressed library. Large collections
can require a longer maintenance window and significant free disk space.

## Ubuntu Compose backups

After following [Ubuntu deployment](ubuntu-deployment.md), run:

```bash
sh deploy/backup.sh
```

The helper stops only this project's API, creates a timestamped archive under
the configured backup bind mount, verifies it, and restarts the API if it was
running. An exit trap also attempts restart when creation or verification fails.
The frontend/gateway and other projects are untouched. A forced kill/power loss
cannot run that trap: check `docker compose ... ps` and start this API manually.
No backup retention/deletion runs automatically.

For an optional daily schedule, use your existing scheduler and absolute paths:

```text
15 3 * * * /bin/sh /absolute/path/e-library/deploy/backup.sh >> /private/path/ebook-backup.log 2>&1
```

The scheduler's account must have Docker access. Confirm a scheduled run creates
a verified archive and the API is healthy afterward. Keep a sensible retention
set (for example daily and weekly snapshots), inspect before pruning, and maintain
an independent copy. Scheduling does not replace periodic restore drills.

## Restore into a separate Ubuntu directory

Use the Compose command prefix from the deployment guide. Create a new empty
directory owned by the configured EBOOK_UID/GID. Bind it as `/data` for this
one operation; the original live directory remains unchanged:

```bash
# Example destination only: choose an unused path and create it with the same
# owner/permissions as the live data directory before running this command.
EBOOK_DATA_PATH=/srv/ebook-library/recovery-test \
  docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm -T --no-deps maintenance \
  python -m app.cli restore /backups/NAME.elbackup.zip --destination /data

EBOOK_DATA_PATH=/srv/ebook-library/recovery-test \
  docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm -T --no-deps maintenance \
  python -m app.cli migrate

EBOOK_DATA_PATH=/srv/ebook-library/recovery-test \
  docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm -T --no-deps maintenance \
  python -m app.cli audit-storage
```

To promote recovered data: stop this stack, preserve the old data directory,
change only `EBOOK_DATA_PATH` in private `deploy/.env` to the recovered directory,
and recreate the stack. Check health, sign in again, open both formats, and verify
saved positions and preferences. The first install on Ubuntu can restore directly
into its initially empty data directory using the same procedure.

The restore tool is deliberately not an in-place rollback button. For an older
schema backup, install compatible application code and run its migrations before
starting the API. The manifest records application version and schema revision.
For rollback after a failed upgrade, restore the pre-upgrade archive to a fresh
directory and use the matching old source revision/image. Existing data stays
available for investigation.

## Guarantees and limits

- `app/maintenance.py` holds a cross-process lease for the API lifetime. Backup,
  restore, migration and owner administration refuse to run on the same data while
  the API holds it. Run exactly one API worker. The lock file remains on disk;
  the OS releases its lock when the process exits, so do not delete it to bypass
  a busy error. Stop older pre-lease installations explicitly before upgrading.
- `app/backups.py` uses SQLite's backup API, checks database integrity/foreign
  keys and original-book catalog hashes, and includes a versioned SHA-256 file
  manifest. Unfinished staging entries and unknown data-root files require review.
- Verification rejects corrupt/truncated archives, unsupported entries, duplicate
  names, unsafe paths, hash/size mismatches and missing catalog files. Only trust
  archives from your own protected backups: checksums detect corruption, not
  an attacker who can replace both payload and manifest.
- Restore verifies in staging, revokes sessions in the restored copy, then
  publishes files before the database. A partial restore cannot start a usable
  partial catalog. Preserve a destination left by an interruption and choose a
  fresh empty destination for retry; do not automatically delete it.
- Limits are 100,000 files, a 16 MiB manifest and 128 GiB expanded data. These
  are initial protective limits, not promises about disk space or throughput.
- Output creation is exclusive. A crash during archive publication can leave an
  incomplete file; verification rejects it and older archives remain available.

The automated drill uses generated EPUB/PDF content, recorded progress, edited
metadata and preferences. It verifies preserved originals/reading copies and
successful sign-in after restoration, and tests that old sessions cannot return.
Cross-process locking is tested separately from the in-process API tests.

Validation in Windows: 92 backend tests pass, including the complete recovery
drill and malformed-backup cases. Frontend type checking/production build pass;
Compose 5.7.0 configuration and the helper shell syntax were checked without
starting containers. Linux image execution remains an explicit operator check.

Reference: [Python SQLite backup API](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup).
