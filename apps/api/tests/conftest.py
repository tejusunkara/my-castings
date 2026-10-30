import os
from argparse import Namespace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

API_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get(
    "MY_CASTINGS_TEST_DATABASE_URL",
    "postgresql+psycopg://my_castings:my_castings@localhost:5432/my_castings_test",
)


@pytest.fixture(scope="session")
def engine():
    """Migrates the test database from scratch once per run, through the real migration."""
    config = Config(API_DIR / "alembic.ini")
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.cmd_opts = Namespace(x=[f"url={TEST_DATABASE_URL}"])
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A session whose work is rolled back after each test, commits included."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture
def login_password() -> str:
    return TEST_PASSWORD


@pytest.fixture(scope="session")
def settings():
    from pydantic import SecretStr

    from app.config import Settings
    from app.services.auth import hash_password

    return Settings(
        database_url=TEST_DATABASE_URL,
        auth_password_hash=SecretStr(hash_password(TEST_PASSWORD)),
        jwt_secret=SecretStr("test-secret-" + "x" * 32),
        cookie_secure=False,  # TestClient talks plain http
    )


@pytest.fixture
def app(db, settings):
    from app.config import get_settings
    from app.deps import get_db
    from app.main import create_app

    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    return app


@pytest.fixture
def anon_client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def client(anon_client):
    response = anon_client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 204
    return anon_client
