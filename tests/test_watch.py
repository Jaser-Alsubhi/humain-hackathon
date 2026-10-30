import inspect

from recovery import agent, break_it, scenarios, watch


def test_healthy_site_raises_no_alert():
    assert watch.assess({"ready": 200, "data": {"clean": True, "orders_missing": 0}}) is None


def test_failing_readiness_is_an_outage_alert_without_hints():
    text, data_mode = watch.assess({"ready": 503})
    assert data_mode is False and "readiness check is failing (HTTP 503)" in text
    assert "no response" in watch.assess({"ready": 0})[0]
    for word in ("database", "config", "frozen", "ledger", "payments"):
        assert word not in text.lower()


def test_unclean_data_is_a_data_alert_with_the_measured_counts_only():
    sig = {"ready": 200, "data": {"clean": False, "orders_missing": 15, "payments_missing": 0, "ledger_mismatch": 35}}
    text, data_mode = watch.assess(sig)
    assert data_mode is True
    assert "orders_missing=15" in text and "ledger_mismatch=35" in text and "payments_missing" not in text


def test_a_data_check_that_cannot_run_is_reported():
    text, data_mode = watch.assess({"ready": 200, "data": {"error": "boom", "clean": False}})
    assert data_mode is True and "could not run" in text and "boom" in text


def test_agent_run_accepts_the_monitors_alert():
    params = inspect.signature(agent.run).parameters
    assert "alert" in params and "data_mode" in params


def test_break_it_lists_every_scenario_once():
    names = break_it.names()
    assert len(names) == len(set(names)) and set(scenarios.NAMES) <= set(names) and "sync_corruption" in names
    assert break_it.main(["no_such_scenario"]) == 1
