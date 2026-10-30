import pytest

from recovery import agent, scenarios, silent


def test_scenarios_know_the_silent_faults():
    for name, table in silent.TARGET.items():
        if name == silent.SYNC:
            continue
        assert scenarios.correct(name) == {"restore_table:" + table, "reconcile_from_journal"}


def test_sync_corruption_has_its_own_fix():
    assert scenarios.correct(silent.SYNC) == {"restore_sync_job", "resync_ledger"}


def test_probe_flags_corrupted_amounts(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, "2"))
    assert all(v.startswith("CORRUPTED") for v in silent.probe_writes().values())


def test_table_arguments_are_allowlisted(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: pytest.fail("SQL must not run for an unknown table"))
    assert "unknown table" in silent.restore_table("orders; DROP TABLE items")
    assert "unknown table" in silent.table_info("items")


def test_invariants_parse_and_flag_missing_rows(monkeypatch):
    out = "\n".join(["journal\t5", "orders\t5", "payments\t0", "orders_missing\t0", "payments_missing\t5",
                     "unbooked_cents\t5000", "amount_mismatch\t0", "sample_orders_missing\t",
                     "sample_payments_missing\tA,B,C"])
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, out))
    r = silent.invariants()
    assert r["payments_missing"] == 5 and r["unbooked_cents"] == 5000 and r["clean"] is False
    clean_out = out.replace("payments_missing\t5", "payments_missing\t0")
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, clean_out))
    assert silent.invariants()["clean"] is True


def test_invariants_report_an_error_instead_of_clean(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (1, "ERROR 1146 Table doesn't exist"))
    r = silent.invariants()
    assert r["clean"] is False and "error" in r


def test_probe_distinguishes_stored_lost_and_error(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, "1"))
    assert set(silent.probe_writes().values()) == {"stored"}
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, "0"))
    assert all(v.startswith("LOST") for v in silent.probe_writes().values())
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (1, "ERROR 1054"))
    assert all(v.startswith("error") for v in silent.probe_writes().values())


def test_run_sql_keeps_the_tab_of_a_final_empty_value(monkeypatch):
    class Done:
        returncode = 0
        stdout = "journal\t3\nsample_payments_missing\t\n"

    monkeypatch.setattr(silent.subprocess, "run", lambda *a, **k: Done())
    rc, out = silent.run_sql("SELECT 1")
    assert silent._rows(out) == {"journal": "3", "sample_payments_missing": ""}


def test_agent_has_the_data_tools_and_marks_the_changing_ones_as_actions():
    names = {t["function"]["name"] for t in agent.TOOLS}
    assert {"check_invariants", "probe_writes", "table_info", "restore_table", "reconcile_from_journal"} <= names
    assert {"restore_table", "reconcile_from_journal"} <= agent.ACT
    assert not {"check_invariants", "probe_writes", "table_info"} & agent.ACT
    assert names <= set(agent.REGISTRY)
    assert "check_invariants" in agent.SYSTEM


def test_table_tools_only_accept_the_two_tables():
    for t in agent.TOOLS:
        if t["function"]["name"] in ("table_info", "restore_table"):
            assert t["function"]["parameters"]["properties"]["table"]["enum"] == list(silent.TABLES)


def test_data_actions_are_guarded_and_dry_run_touches_nothing():
    guard = agent.Guard(agent.REGISTRY, agent.ACT, dry_run=True)
    text, blocked = guard.dispatch("restore_table", {"table": "payments"})
    assert text.startswith("dry-run") and not blocked
    assert guard.action_count == 1


def test_action_labels_include_the_table_and_alerts_differ():
    assert agent._label("restore_table", {"table": "payments"}) == "restore_table:payments"
    assert agent._label("restart_service", {"service": "db"}) == "restart_service:db"
    assert agent._label("reconcile_from_journal", {}) == "reconcile_from_journal"
    assert agent.ALERT_DATA != agent.ALERT


_BASE = "\n".join(["journal\t5", "orders\t5", "payments\t5", "orders_missing\t0", "payments_missing\t0",
                   "unbooked_cents\t0", "amount_mismatch\t0", "sample_orders_missing\t", "sample_payments_missing\t"])


def _ledger_sql(rows, mismatch, probe):
    ledger_out = "\n".join(["ledger_rows\t%d" % rows, "ledger_missing\t0", "ledger_mismatch\t%d" % mismatch,
                            "ledger_drift_cents\t%d" % (mismatch * 5), "ledger_sample_checked\t2",
                            "ledger_sample_wrong\t%d" % (1 if mismatch else 0)])

    def fake(q, *a, **k):
        if "information_schema.tables" in q:
            return 0, "1"
        if "ledger_missing" in q:
            return 0, ledger_out
        if "ledger" in q:
            return 0, probe
        if "INSERT INTO" in q:
            return 0, "1"
        return 0, _BASE
    return fake


def test_invariants_compare_the_ledger_when_it_exists(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", _ledger_sql(5, 3, "1"))
    r = silent.invariants()
    assert r["ledger_mismatch"] == 3 and r["ledger_sample_wrong"] == 1 and r["clean"] is False
    monkeypatch.setattr(silent, "run_sql", _ledger_sql(5, 0, "1"))
    assert silent.invariants()["clean"] is True


def test_probe_checks_what_the_ledger_stored(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", _ledger_sql(5, 0, "8"))
    assert silent.probe_writes()["ledger"].startswith("CORRUPTED")
    monkeypatch.setattr(silent, "run_sql", _ledger_sql(5, 0, "-1"))
    assert silent.probe_writes()["ledger"].startswith("LOST")
    monkeypatch.setattr(silent, "run_sql", _ledger_sql(5, 0, "1"))
    assert silent.probe_writes()["ledger"] == "stored"


def test_ledger_tools_do_nothing_without_a_ledger(monkeypatch):
    monkeypatch.setattr(silent, "run_sql", lambda *a, **k: (0, "0"))
    assert "no ledger" in silent.restore_sync_job()
    assert "no ledger" in silent.resync_ledger()


def test_the_bug_is_a_second_trigger_that_rewrites_existing_ledger_rows():
    assert "UPDATE ledger" in silent.SYNC_DRIFT and "FOLLOWS sync_job" in silent.SYNC_DRIFT
    assert "UPDATE" not in silent.SYNC_GOOD and "INSERT INTO ledger" in silent.SYNC_GOOD
