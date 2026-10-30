from recovery import ops


def _fake(top):
    def compose(*args, **k):
        if args[:2] == ("ps", "-q"):
            return 0, "cid-" + args[2]
        return 0, "backend: running (Up 2 minutes)"

    def sh(cmd, *a, **k):
        svc = cmd[2].replace("cid-", "")
        return 0, top.get(svc, "PID STAT COMMAND\n1 Ss init")
    return compose, sh


def test_frozen_processes_finds_stopped_blocked_and_zombie(monkeypatch):
    top = {"backend": "PID STAT COMMAND\n7 Tsl uvicorn\n8 Ssl python", "db": "PID STAT COMMAND\n3 Dsl mysqld\n4 Z+ sh"}
    monkeypatch.setattr(ops, "compose", _fake(top)[0])
    monkeypatch.setattr(ops, "sh", _fake(top)[1])
    found = ops.frozen_processes()
    assert ("backend", "7", "uvicorn", "Tsl") in found
    assert [f[0] for f in found].count("db") == 2
    assert not any(f[0] == "frontend" for f in found)


def test_service_status_warns_about_a_frozen_process(monkeypatch):
    top = {"backend": "PID STAT COMMAND\n7 Tsl uvicorn"}
    monkeypatch.setattr(ops, "compose", _fake(top)[0])
    monkeypatch.setattr(ops, "sh", _fake(top)[1])
    out = ops.service_status()
    assert out.startswith("WARNING: backend has a frozen process")
    assert "Restart only the service" in ops.find_frozen_processes()


def test_service_status_has_no_warning_when_everything_runs(monkeypatch):
    monkeypatch.setattr(ops, "compose", _fake({})[0])
    monkeypatch.setattr(ops, "sh", _fake({})[1])
    assert "WARNING" not in ops.service_status()
    assert ops.find_frozen_processes() == "no stopped, blocked or zombie processes found"
