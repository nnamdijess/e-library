"""Local-only administration. Passwords are prompted, never command arguments."""

import argparse
from getpass import getpass
import json
from pathlib import Path
import sqlite3

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import make_engine, migrate, require_current_schema
from app.security import provision_owner
from app.storage import audit_storage
from app.backups import create_backup, verify_backup, restore_backup, BackupError
from app.maintenance import data_lease, DataBusy


def main():
    parser = argparse.ArgumentParser(description="Manage the local ebook library")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply versioned database migrations")
    commands.add_parser("audit-storage", help="Report missing files and crash leftovers; stop the backend first")
    backup = commands.add_parser("backup", help="Create an offline backup; stop the backend first")
    backup.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-backup", help="Verify a backup without changing the live library")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--work-dir", type=Path)
    restore = commands.add_parser("restore", help="Restore into an empty directory; never overwrite existing data")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    owner = commands.add_parser("create-owner", help="Provision the single owner interactively")
    owner.add_argument("--username", required=True)
    args = parser.parse_args()
    settings = Settings()
    try:
        if args.command == "backup":
            print(json.dumps(create_backup(settings.data_dir, args.output)))
            return
        if args.command == "verify-backup":
            print(json.dumps(verify_backup(args.archive, args.work_dir)))
            return
        if args.command == "restore":
            print(json.dumps(restore_backup(args.archive, args.destination)))
            print("Restored. Existing sessions were revoked; sign in again. Run migrate before starting the API.")
            return
        if args.command == "migrate":
            migrate(settings)
            print("Database migrations applied.")
            return
    except (BackupError, DataBusy, OSError, sqlite3.Error) as error:
        parser.exit(1, str(error) + "\n")

    engine = make_engine(settings)
    try:
        with data_lease(settings.data_dir):
            require_current_schema(engine)
            if args.command == "audit-storage":
                issues = audit_storage(settings, engine)
                for issue in issues:
                    print(issue)
                print(f"Storage audit: {len(issues)} issue(s). No files changed.")
                if issues:
                    parser.exit(1)
                return
            password = getpass("Owner password (at least 12 characters): ")
            if password != getpass("Confirm password: "):
                parser.exit(1, "Passwords did not match.\n")
            with Session(engine) as db:
                provision_owner(db, args.username, password)
            print("Owner created. Sign in through the local frontend.")
    except (ValueError, IntegrityError, DataBusy) as error:
        message = "An owner already exists." if isinstance(error, IntegrityError) else str(error)
        parser.exit(1, message + "\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
