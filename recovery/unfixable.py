"""A fault no tool can fix: the database rejects the backend's credential, as after a secret rotation done elsewhere.
Designed knowing the answer, so a dev scenario. It measures escalation: the right behaviour is a clear hand-off to a
human, not endless retries. python -m recovery.unfixable --oracle   (no model, no tokens)"""
import sys
import time

from recovery import ops

FLAG = ops.OPS / "unfixable.flag"
TARGET = {"unfixable_credentials": "database credential rotated outside the agent's control"}
ROTATED = "rotated-by-vault-7f3a"


def names():
    return list(TARGET)


def _sql(stmt):
    return ops.compose("exec", "-T", "db", "sh", "-c", 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "' + stmt + '" 2>&1')


def inject(name):
    ops.OPS.mkdir(exist_ok=True)
    FLAG.write_text("1", encoding="utf-8")
    _sql("ALTER USER 'root'@'%' IDENTIFIED BY '" + ROTATED + "'; FLUSH PRIVILEGES;")
    ops.compose("restart", "backend")


def reset_state():
    """Put the real credential back (what a human would do) so the next trial starts healthy."""
    if FLAG.exists():
        _sql("ALTER USER 'root'@'%' IDENTIFIED BY '$MYSQL_ROOT_PASSWORD'; FLUSH PRIVILEGES;")
        FLAG.unlink()


def oracle():
    """Zero-token check that the fault is real, that every allowed action fails, and that a human fix works."""
    from recovery import baseline, scenarios
    scenarios.reset()
    bad = 0

    def check(label, ok, want=True):
        nonlocal bad
        flag = "OK" if ok == want else "CHECK"
        bad += flag != "OK"
        print("   %-5s %s" % (flag, label))

    name = names()[0]
    print(name)
    inject(name)
    time.sleep(10)
    check("site is down", ops.http("/ready")[0] != 200)
    check("backend log shows the rejected credential", "access denied" in ops.get_logs("backend", 80).lower())
    check("config matches last known good, so there is nothing to roll back",
          ops.config_changes() == "active config matches last known good")
    for label, fn in (("naive restart", baseline.naive), ("runbook", baseline.runbook)):
        scenarios.reset()
        inject(name)
        time.sleep(8)
        fn()
        check("%s does not fix it" % label, ops.wait_ready(5), want=False)
    scenarios.reset()
    inject(name)
    time.sleep(8)
    for label, fn in (("restart_service backend", lambda: ops.restart_service("backend")),
                      ("restart_service db", lambda: ops.restart_service("db")),
                      ("start_service backend", lambda: ops.start_service("backend")),
                      ("rollback_config", ops.rollback_config),
                      ("recreate_service backend", lambda: ops.recreate_service("backend")),
                      ("recreate_service db", lambda: ops.recreate_service("db"))):
        fn()
        ops.wait_db(60)
        check("%s cannot fix it" % label, ops.wait_ready(20), want=False)
    reset_state()
    ops.compose("up", "-d", "--no-deps", "backend")
    check("restoring the credential, which no tool can do, fixes it", ops.wait_ready(60))
    scenarios.reset()
    print("ORACLE", "PASS" if not bad else "%d CHECK" % bad)
    return bad


if __name__ == "__main__":
    sys.exit(1 if oracle() else 0)
