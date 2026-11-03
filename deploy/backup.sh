#!/bin/sh
# Use from cron/systemd or manually. No automatic deletion/retention pruning.
set -eu
deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
deploy_env=${EBOOK_DEPLOY_ENV:-"$deploy_dir/.env"}
dc() { docker compose --env-file "$deploy_env" -f "$deploy_dir/compose.yaml" "$@"; }
api_was_running=$(dc ps --status running --services api)
restart_api() {
    if [ "$api_was_running" = "api" ]; then dc start api; fi
}
trap restart_api EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$api_was_running" = "api" ]; then dc stop -t 30 api; fi
backup_name="library-$(date -u +%Y%m%dT%H%M%SZ).elbackup.zip"
dc run --rm -T --no-deps maintenance python -m app.cli backup --output "/backups/$backup_name"
dc run --rm -T --no-deps maintenance python -m app.cli verify-backup "/backups/$backup_name" --work-dir /backups
printf 'Verified backup: %s\n' "$backup_name"
