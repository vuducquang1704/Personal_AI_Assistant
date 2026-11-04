import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///" + str(Path(__file__).parent / "test.db"))
os.environ["REMINDER_POLL_SECONDS"] = "3600"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/api/auth/register", json={"email": "minh@example.com", "full_name": "Minh", "password": "secret123"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
