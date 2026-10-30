"""Silent-failure scenarios: the site is up and /ready is green, but orders or payments are no longer stored.
The fault is a table switched to MySQL's BLACKHOLE engine, which accepts every write and keeps nothing.
sync_corruption is different: a sync job (a trigger) copies every new order into a ledger. Then a bug starts nudging
rows that were already correct, a cent at a time, so good records turn bad over time. The site stays ready.
Designed knowing the fix, so these are dev scenarios, not an unbiased test.
python -m recovery.silent --oracle   (no model, no tokens)"""
import json
import re
import subprocess  # nosec B404
import sys
import urllib.request

from recovery import ops

FLAG = ops.OPS / "silent.flag"
TABLES = ("orders", "payments")
TARGET = {"silent_drop_payments": "payments", "silent_drop_orders": "orders"}
SEED, LOST = 20, 15
PROBE = "__probe__"
SYNC = "sync_corruption"
TARGET[SYNC] = "ledger"
LEDGER_TABLE = ("CREATE TABLE ledger (id INT AUTO_INCREMENT PRIMARY KEY, order_ref VARCHAR(64) NOT NULL, "
                "amount_cents INT NOT NULL, created DATETIME NULL, KEY ix_ledger_ref (order_ref));")
_SYNC_HEAD = "CREATE TRIGGER sync_job AFTER INSERT ON orders FOR EACH ROW INSERT INTO ledger (order_ref, amount_cents, created) "
SYNC_GOOD = _SYNC_HEAD + "VALUES (NEW.order_ref, NEW.amount_cents, NEW.created);"
# The bug: every new order also nudges some older ledger rows by one cent, so rows that were correct turn wrong.
SYNC_DRIFT = ("CREATE TRIGGER sync_job_drift AFTER INSERT ON orders FOR EACH ROW FOLLOWS sync_job "
              "UPDATE ledger SET amount_cents = amount_cents + 1 WHERE MOD(id, 4) = MOD(NEW.id, 4);")
LEDGER_PROBE = ("DELETE FROM orders WHERE order_ref = '%(p)s';DELETE FROM ledger WHERE order_ref = '%(p)s';"
                "INSERT INTO orders (order_ref, amount_cents, status, created) VALUES ('%(p)s', 1, 'paid', NOW());"
                "SELECT COALESCE(MAX(amount_cents), -1) FROM ledger WHERE order_ref = '%(p)s';"
                "DELETE FROM orders WHERE order_ref = '%(p)s';DELETE FROM ledger WHERE order_ref = '%(p)s';") % {"p": PROBE}
_TABLE_ERR = "unknown table, choose one of %s" % (TABLES,)


def names():
    return list(TARGET)


def correct(name):
    if name == SYNC:
        return {"restore_sync_job", "resync_ledger"}
    return {"restore_table:" + TARGET[name], "reconcile_from_journal"}


def run_sql(query, timeout=60):
    cmd = ops.BASE + ["exec", "-T", "db", "sh", "-c", 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B hackdb 2>&1']
    try:
        p = subprocess.run(cmd, cwd=ops.ROOT, input=query, capture_output=True, text=True,  # nosec B603
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    lines = [x for x in (p.stdout or "").splitlines() if "Using a password" not in x]
    return p.returncode, "\n".join(lines).strip("\r\n")


def _rows(out):
    """Parse 'label<TAB>value' lines. Anything else is an error message from MySQL."""
    got = {}
    for line in out.splitlines():
        if "\t" not in line:
            return None
        k, v = line.split("\t", 1)
        got[k] = v
    return got


def _missing(t):
    return "FROM order_journal j LEFT JOIN %s t ON t.order_ref = j.order_ref WHERE t.order_ref IS NULL" % t


def ledger_exists():
    rc, out = run_sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'hackdb' AND table_name = 'ledger';")
    return rc == 0 and out.strip() == "1"


def ledger_checks():
    """Compare orders with their ledger copies: a sample (every third order) and the full set."""
    both = "FROM orders o JOIN ledger l ON l.order_ref = o.order_ref"
    sample = ("FROM order_journal j JOIN orders o ON o.order_ref = j.order_ref "
              "LEFT JOIN ledger l ON l.order_ref = o.order_ref WHERE MOD(j.id, 3) = 0")
    q = (
        "SELECT 'ledger_rows', COUNT(*) FROM ledger;"
        "SELECT 'ledger_missing', COUNT(*) FROM orders o LEFT JOIN ledger l ON l.order_ref = o.order_ref WHERE l.order_ref IS NULL;"
        "SELECT 'ledger_mismatch', COUNT(*) " + both + " WHERE l.amount_cents <> o.amount_cents;"
        "SELECT 'ledger_drift_cents', COALESCE(SUM(l.amount_cents - o.amount_cents), 0) " + both + ";"
        "SELECT 'ledger_sample_checked', COUNT(*) " + sample + ";"
        "SELECT 'ledger_sample_wrong', COUNT(*) " + sample + " AND (l.order_ref IS NULL OR l.amount_cents <> o.amount_cents);"
    )
    rc, out = run_sql(q)
    got = _rows(out)
    if rc != 0 or got is None:
        return {"error": out[-300:] or "ledger query failed"}
    return {k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in got.items()}


def invariants():
    """Compare the intake journal with the orders and payments tables. clean is True only when nothing is missing or wrong."""
    q = (
        "SELECT 'journal', COUNT(*) FROM order_journal;"
        "SELECT 'orders', COUNT(*) FROM orders;"
        "SELECT 'payments', COUNT(*) FROM payments;"
        "SELECT 'orders_missing', COUNT(*) " + _missing("orders") + ";"
        "SELECT 'payments_missing', COUNT(*) " + _missing("payments") + ";"
        "SELECT 'unbooked_cents', COALESCE(SUM(j.amount_cents), 0) " + _missing("payments") + ";"
        "SELECT 'amount_mismatch', COUNT(*) FROM order_journal j "
        "JOIN orders o ON o.order_ref = j.order_ref JOIN payments p ON p.order_ref = j.order_ref "
        "WHERE o.amount_cents <> j.amount_cents OR p.amount_cents <> j.amount_cents;"
        "SELECT 'sample_orders_missing', COALESCE(GROUP_CONCAT(x.r), '') FROM "
        "(SELECT j.order_ref r " + _missing("orders") + " ORDER BY j.id LIMIT 5) x;"
        "SELECT 'sample_payments_missing', COALESCE(GROUP_CONCAT(x.r), '') FROM "
        "(SELECT j.order_ref r " + _missing("payments") + " ORDER BY j.id LIMIT 5) x;"
    )
    rc, out = run_sql(q)
    got = _rows(out)
    if rc != 0 or got is None:
        return {"error": out[-300:] or "query failed", "clean": False}
    r = {k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in got.items()}
    r["clean"] = not (r["orders_missing"] or r["payments_missing"] or r["amount_mismatch"])
    if ledger_exists():
        led = ledger_checks()
        if "error" in led:
            return {"error": led["error"], "clean": False}
        r.update(led)
        r["clean"] = r["clean"] and not (led["ledger_missing"] or led["ledger_mismatch"])
    return r


def probe_writes():
    """Write one marked row into each table and read it back. Accepted but not stored means the table drops writes."""
    result = {}
    for t in TABLES:
        extra_cols, extra_vals = (", status", ", 'paid'") if t == "orders" else ("", "")
        q = ("DELETE FROM %s WHERE order_ref = '%s';"
             "INSERT INTO %s (order_ref, amount_cents%s, created) VALUES ('%s', 1%s, NOW());"
             "SELECT COALESCE(MAX(amount_cents), -1) FROM %s WHERE order_ref = '%s';"
             "DELETE FROM %s WHERE order_ref = '%s';") % (t, PROBE, t, extra_cols, PROBE, extra_vals, t, PROBE, t, PROBE)
        rc, out = run_sql(q)
        last = out.splitlines()[-1] if out else ""
        if last == "1":
            result[t] = "stored"
        elif last in ("0", "-1"):
            result[t] = "LOST: the write was accepted but the row was not stored"
        elif last.lstrip("-").isdigit():
            result[t] = "CORRUPTED: wrote 1 cent but the table stored %s" % last
        else:
            result[t] = "error: " + out[-200:]
    if ledger_exists():
        rc, out = run_sql(LEDGER_PROBE)
        last = out.splitlines()[-1] if out else ""
        if last == "1":
            result["ledger"] = "stored"
        elif last == "-1":
            result["ledger"] = "LOST: the order was stored but the sync job did not copy it into the ledger"
        elif last.lstrip("-").isdigit():
            result["ledger"] = "CORRUPTED: wrote 1 cent but the ledger stored %s" % last
        else:
            result["ledger"] = "error: " + out[-200:]
    return result


def table_info(table):
    if table not in TABLES:
        return _TABLE_ERR
    rc, out = run_sql("SELECT 'engine', engine FROM information_schema.tables "
                      "WHERE table_schema = 'hackdb' AND table_name = '%s';"
                      "SELECT 'rows', COUNT(*) FROM %s;" % (table, table))
    return _rows(out) if rc == 0 and _rows(out) is not None else out[-300:]


def restore_table(table):
    if table not in TABLES:
        return _TABLE_ERR
    rc, out = run_sql("ALTER TABLE %s ENGINE=InnoDB;" % table)
    return ("table %s rebuilt on InnoDB" % table) if rc == 0 and not out else out[-300:]


def reconcile_from_journal():
    """Replay every journal entry that is missing from orders or payments. Rows that already exist are left alone."""
    before = invariants()
    rc, out = run_sql(
        "INSERT IGNORE INTO orders (order_ref, amount_cents, status, created) "
        "SELECT order_ref, amount_cents, 'paid', created FROM order_journal;"
        "INSERT IGNORE INTO payments (order_ref, amount_cents, created) "
        "SELECT order_ref, amount_cents, created FROM order_journal;")
    after = invariants()
    if rc != 0 or out or "error" in before or "error" in after:
        return out[-300:] or "replay failed"
    return {"orders_replayed": before["orders_missing"] - after["orders_missing"],
            "payments_replayed": before["payments_missing"] - after["payments_missing"],
            "orders_still_missing": after["orders_missing"], "payments_still_missing": after["payments_missing"]}


def list_sync_jobs():
    """List database triggers: code that runs on every write and can change what is stored."""
    rc, out = run_sql("SELECT trigger_name, event_object_table, action_timing, event_manipulation, action_statement "
                      "FROM information_schema.triggers WHERE trigger_schema = 'hackdb';")
    if rc != 0:
        return out[-300:]
    return out[-600:] or "no sync jobs or triggers found"


def restore_sync_job():
    """Replace whatever sync job is installed with the standard one: it copies each new order into the ledger unchanged."""
    if not ledger_exists():
        return "there is no ledger table, nothing to restore"
    rc, out = run_sql("DROP TRIGGER IF EXISTS sync_job_drift;DROP TRIGGER IF EXISTS sync_job;"
                      "DROP TRIGGER IF EXISTS sync_job_bug;" + SYNC_GOOD)
    return "sync job restored" if rc == 0 and not out else out[-300:]


def resync_ledger():
    """Make every ledger row match its order: fix wrong amounts and add missing rows."""
    if not ledger_exists():
        return "there is no ledger table, nothing to resync"
    before = ledger_checks()
    rc, out = run_sql(
        "UPDATE ledger l JOIN orders o ON o.order_ref = l.order_ref SET l.amount_cents = o.amount_cents "
        "WHERE l.amount_cents <> o.amount_cents;"
        "INSERT INTO ledger (order_ref, amount_cents, created) SELECT o.order_ref, o.amount_cents, o.created "
        "FROM orders o LEFT JOIN ledger l ON l.order_ref = o.order_ref WHERE l.order_ref IS NULL;")
    after = ledger_checks()
    if rc != 0 or out or "error" in before or "error" in after:
        return out[-300:] or "resync failed"
    return {"ledger_mismatch_before": before["ledger_mismatch"], "ledger_mismatch_after": after["ledger_mismatch"],
            "ledger_missing_after": after["ledger_missing"]}


def healthy():
    """The truth for these scenarios: the site is ready AND no data is missing AND every table really stores writes."""
    inv = invariants()
    return (ops.http("/ready")[0] == 200 and inv.get("clean") is True
            and all(v == "stored" for v in probe_writes().values()))


def clean():
    run_sql("DROP TRIGGER IF EXISTS sync_job_bug;DROP TRIGGER IF EXISTS sync_job_drift;DROP TRIGGER IF EXISTS sync_job;DROP TABLE IF EXISTS ledger;ALTER TABLE orders ENGINE=InnoDB;ALTER TABLE payments ENGINE=InnoDB;"
            "TRUNCATE TABLE orders;TRUNCATE TABLE payments;TRUNCATE TABLE order_journal;")


def post_order(ref, cents):
    req = urllib.request.Request(ops.API + "/orders", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"order_ref": ref, "amount_cents": cents}).encode())
    with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310
        return r.status


def inject(name):
    t = TARGET[name]
    ops.OPS.mkdir(exist_ok=True)
    FLAG.write_text("1", encoding="utf-8")
    clean()
    if name == SYNC:
        run_sql(LEDGER_TABLE + SYNC_GOOD)
    for i in range(SEED):
        assert post_order("SEED-%03d" % i, 1000 + 7 * i) == 201
    if name == SYNC:
        run_sql(SYNC_DRIFT)
    else:
        run_sql("ALTER TABLE %s ENGINE=BLACKHOLE;" % t)
    for i in range(LOST):
        assert post_order("LOST-%03d" % i, 2000 + 13 * i) == 201


def reset_state():
    if FLAG.exists():
        clean()
        FLAG.unlink()


def oracle():
    """Zero-token check of everything the scenarios claim."""
    from recovery import baseline, scenarios
    scenarios.reset()
    bad = 0

    def check(label, ok, want=True):
        nonlocal bad
        flag = "OK" if ok == want else "CHECK"
        bad += flag != "OK"
        print("   %-5s %s" % (flag, label))

    for name in [n for n in names() if n != SYNC]:
        t = TARGET[name]
        print(name)
        clean()
        inject(name)
        inv = invariants()
        check("site still reports ready (the fault is silent)", ops.http("/ready")[0] == 200)
        check("journal has %d entries, %s is missing them" % (SEED + LOST, t),
              inv.get("journal") == SEED + LOST and inv.get("%s_missing" % t) == SEED + LOST)
        probes = probe_writes()
        other = [x for x in TABLES if x != t][0]
        check("write probe sees the loss on %s only" % t, probes[t].startswith("LOST") and probes[other] == "stored")
        for label, fn in (("naive restart", baseline.naive), ("runbook", baseline.runbook)):
            clean()
            inject(name)
            fn()
            check("%s does not fix it" % label, healthy(), want=False)
        clean()
        inject(name)
        reconcile_from_journal()
        restore_table(t)
        check("wrong order leaves the data missing", healthy(), want=False)
        clean()
        inject(name)
        restore_table(t)
        reconcile_from_journal()
        check("restore then replay fixes it", healthy())
    print(SYNC)
    clean()
    inject(SYNC)
    inv = invariants()
    check("site still reports ready (the fault is silent)", ops.http("/ready")[0] == 200)
    check("orders, payments and journal agree: the damage is only in the ledger",
          inv.get("amount_mismatch") == 0 and inv.get("orders_missing") == 0 and inv.get("payments_missing") == 0)
    check("rows that were correct have turned wrong (%d of %d ledger rows differ)" % (SEED + LOST, SEED + LOST),
          inv.get("ledger_mismatch") == SEED + LOST)
    check("the sampled check catches it", inv.get("ledger_sample_wrong", 0) > 0 and inv.get("clean") is False)
    check("write probe sees the drift on the ledger", probe_writes().get("ledger", "").startswith("CORRUPTED"))
    for label, fn in (("naive restart", baseline.naive), ("runbook", baseline.runbook)):
        clean()
        inject(SYNC)
        fn()
        check("%s does not fix it" % label, healthy(), want=False)
    clean()
    inject(SYNC)
    resync_ledger()
    check("resyncing without fixing the job does not hold", healthy(), want=False)
    clean()
    inject(SYNC)
    restore_sync_job()
    check("restoring the job without resyncing leaves the old drift", healthy(), want=False)
    clean()
    inject(SYNC)
    restore_sync_job()
    resync_ledger()
    check("restore the job, then resync the ledger, fixes it", healthy())
    clean()
    scenarios.reset()
    print("ORACLE", "PASS" if not bad else "%d CHECK" % bad)
    return bad


if __name__ == "__main__":
    if "--oracle" in sys.argv:
        sys.exit(1 if oracle() else 0)
    print(json.dumps({"invariants": invariants(), "probe": probe_writes()}, indent=2))
