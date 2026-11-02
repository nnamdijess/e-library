"""Disposable browser-test backend. Never opens the real library database."""

from io import BytesIO
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import make_engine, migrate
from app.main import create_app
from app.security import provision_owner
from app.storage import ingest_book
from test_epub_reader import reading_fixture


def main():
    cache = Path(__file__).resolve().parents[2] / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reader-e2e-", dir=cache) as directory:
        assert Path(directory).resolve().is_relative_to(cache.resolve())
        settings = Settings(_env_file=None, data_dir=Path(directory), trusted_origins=["http://127.0.0.1:3001"])
        migrate(settings)
        engine = make_engine(settings)
        try:
            with Session(engine) as db:
                provision_owner(db, "testowner", "local-reader-test-only")
            ingest_book(BytesIO(reading_fixture(hostile=True)), "reader-fixture.epub", 1, settings, engine)
            uvicorn.run(create_app(settings), host="127.0.0.1", port=8001, access_log=False)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
