from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models  # noqa: F401
from backend.db import Base, get_db
from backend.main import app


def make_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_crud_roundtrip():
    client = make_client()
    try:
        r = client.post("/items", json={"text": "hello", "label": "a"})
        assert r.status_code == 201
        item_id = r.json()["id"]
        assert client.get(f"/items/{item_id}").json()["text"] == "hello"
        assert len(client.get("/items").json()) == 1
        assert client.delete(f"/items/{item_id}").status_code == 204
        assert client.get(f"/items/{item_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()
