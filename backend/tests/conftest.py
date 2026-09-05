"""Test fixtures. Tests run against a throwaway SQLite database so they need no services."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

TMP_DB = os.path.join(tempfile.gettempdir(), "grandmasterai_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TMP_DB}")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-hs256")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6399/0")  # unreachable on purpose: exercise the memory fallback

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402,F401
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    """Rate-limit counters must not leak between tests."""
    from app.core.cache import get_cache

    get_cache().clear()
    yield


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client: TestClient) -> Iterator[TestClient]:
    """A client already registered and carrying a bearer token."""
    res = client.post(
        "/api/auth/signup",
        json={
            "email": "learner@example.com",
            "password": "correct-horse-battery",
            "display_name": "Learner",
            "preferred_language": "Tamil",
            "goal": "Reach 1500",
        },
    )
    assert res.status_code == 201, res.text
    client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
    yield client
