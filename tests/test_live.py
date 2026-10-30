import time

import pytest

from live import server
from recovery import break_it


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "COUNTS", tmp_path / "counts.json")
    monkeypatch.setattr(server, "KILL", tmp_path / "off")
    monkeypatch.setattr(server.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})())
    server.IP_HITS.clear()
    server.RUN.update(state="idle", scenario=None, events=[], recovered=None, started=0.0, ended=0.0)


def test_every_live_fault_is_a_real_scenario():
    assert set(server.SCENARIOS) <= set(break_it.names())


def test_unknown_fault_is_refused():
    assert server.try_start("rm_rf", "1.2.3.4")[0] == 400


def test_one_run_at_a_time_then_a_cooldown():
    assert server.try_start("db_down", "1.1.1.1")[0] == 200
    assert server.try_start("db_down", "2.2.2.2")[0] == 409
    server.RUN.update(state="done", ended=time.time())
    assert server.try_start("db_down", "2.2.2.2")[0] == 429
    server.RUN["ended"] = time.time() - 60
    assert server.try_start("db_down", "2.2.2.2")[0] == 200


def test_a_visitor_has_an_hourly_limit():
    for _ in range(server.PER_IP_HOUR):
        assert server.try_start("db_down", "9.9.9.9")[0] == 200
        server.RUN.update(state="done", ended=0.0)
    assert server.try_start("db_down", "9.9.9.9")[0] == 429
    assert server.try_start("db_down", "8.8.8.8")[0] == 200


def test_the_daily_cap_and_the_kill_switch(monkeypatch):
    monkeypatch.setattr(server, "DAILY_CAP", 1)
    assert server.try_start("db_down", "1.1.1.1")[0] == 200
    server.RUN.update(state="done", ended=0.0)
    assert server.try_start("db_down", "2.2.2.2")[0] == 429
    monkeypatch.setattr(server, "DAILY_CAP", 99)
    server.KILL.write_text("x")
    assert server.try_start("db_down", "3.3.3.3")[0] == 503


def test_status_returns_only_new_events():
    server.RUN.update(state="running", started=time.time())
    server.add("one")
    server.add("two")
    first = server.status(0)
    assert [e["text"] for e in first["events"]] == ["one", "two"] and first["next"] == 2
    assert server.status(2)["events"] == []
