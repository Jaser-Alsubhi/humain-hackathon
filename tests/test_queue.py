from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import messages, models  # noqa: F401
from backend.db import Base, get_db
from backend.main import app


def make(monkeypatch, depth, overflow):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(messages, "SessionLocal", Session)
    monkeypatch.setenv("QUEUE_MAX_DEPTH", str(depth))
    monkeypatch.setenv("QUEUE_OVERFLOW", overflow)
    return TestClient(app)


def send(client, ref, cents=100):
    return client.post("/queue/messages", json={"msg_ref": ref, "amount_cents": cents})


def test_message_is_journaled_and_queued_and_repeat_is_ignored(monkeypatch):
    c = make(monkeypatch, 10, "reject")
    assert send(c, "m1").status_code == 202
    assert send(c, "m1").status_code == 202
    s = c.get("/queue/summary").json()
    assert (s["journal"], s["queued"], s["done"], s["lost"]) == (1, 1, 0, 0)


def test_reject_policy_tells_the_sender_and_keeps_nothing_it_refused(monkeypatch):
    c = make(monkeypatch, 2, "reject")
    assert [send(c, "m%d" % i).status_code for i in range(3)] == [202, 202, 429]
    s = c.get("/queue/summary").json()
    assert (s["journal"], s["queued"], s["lost"]) == (2, 2, 0)


def test_drop_policy_accepts_everything_and_loses_the_overflow_silently(monkeypatch):
    c = make(monkeypatch, 2, "drop")
    assert [send(c, "m%d" % i).status_code for i in range(5)] == [202] * 5
    s = c.get("/queue/summary").json()
    assert (s["journal"], s["queued"], s["lost"]) == (5, 2, 3)


def test_replay_under_the_same_bad_policy_loses_them_again(monkeypatch):
    c = make(monkeypatch, 2, "drop")
    for i in range(5):
        send(c, "m%d" % i)
    assert c.post("/queue/replay").json() == {"queued": 0, "dropped": 3, "full": 0}
    assert c.get("/queue/summary").json()["lost"] == 3


def test_replay_under_a_good_policy_recovers_every_message_once(monkeypatch):
    c = make(monkeypatch, 2, "drop")
    for i in range(5):
        send(c, "m%d" % i)
    monkeypatch.setenv("QUEUE_MAX_DEPTH", "1000")
    monkeypatch.setenv("QUEUE_OVERFLOW", "reject")
    assert c.post("/queue/replay").json() == {"queued": 3, "dropped": 0, "full": 0}
    while c.get("/queue/summary").json()["queued"]:
        messages.work_once()
    s = c.get("/queue/summary").json()
    assert (s["journal"], s["queued"], s["done"], s["lost"]) == (5, 0, 5, 0)
    assert c.post("/queue/replay").json() == {"queued": 0, "dropped": 0, "full": 0}
