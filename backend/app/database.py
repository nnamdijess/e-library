"""SQLite connections and explicit Alembic migrations; never create_all()."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine

from app.config import Settings


def make_engine(settings: Settings) -> Engine:
    engine = create_engine(
        URL.create("sqlite", database=str(settings.data_dir / "library.sqlite3")),
        connect_args={"check_same_thread": False, "timeout": 5, "autocommit": False},
    )

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _record):
        previous = connection.autocommit
        connection.autocommit = True
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
        finally:
            connection.autocommit = previous

    return engine


def migration_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    return config


def migrate(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings)
    try:
        with engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def require_current_schema(engine: Engine) -> None:
    expected = ScriptDirectory.from_config(migration_config()).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        raise RuntimeError("Database migration required. From backend run: python -m app.cli migrate")
