import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import make_engine, migrate
from app.security import provision_owner

PASSWORD = "test-only long passphrase"
ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture
def settings(tmp_path):
    config = Settings(_env_file=None, data_dir=tmp_path, trusted_origins=[ORIGIN])
    migrate(config)
    engine = make_engine(config)
    try:
        with Session(engine) as db:
            provision_owner(db, "owner", PASSWORD)
    finally:
        engine.dispose()
    return config
