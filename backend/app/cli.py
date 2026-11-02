"""Local-only administration. Passwords are prompted, never command arguments."""

import argparse
from getpass import getpass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import make_engine, migrate, require_current_schema
from app.security import provision_owner
from app.storage import audit_storage


def main():
    parser = argparse.ArgumentParser(description="Manage the local ebook library")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply versioned database migrations")
    commands.add_parser("audit-storage", help="Report missing files and crash leftovers; stop the backend first")
    owner = commands.add_parser("create-owner", help="Provision the single owner interactively")
    owner.add_argument("--username", required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "migrate":
        migrate(settings)
        print("Database migrations applied.")
        return

    engine = make_engine(settings)
    try:
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
    except (ValueError, IntegrityError) as error:
        message = str(error) if isinstance(error, ValueError) else "An owner already exists."
        parser.exit(1, message + "\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
