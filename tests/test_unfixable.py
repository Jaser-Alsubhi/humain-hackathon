import json

import pytest

from recovery import agent, escalation, scenarios, unfixable


def test_escalate_is_a_tool_but_not_an_action():
    names = {t["function"]["name"] for t in agent.TOOLS}
    assert "escalate" in names and "escalate" in agent.REGISTRY
    assert "escalate" not in agent.ACT
    assert "escalate" in agent.SYSTEM


def test_unfixable_scenario_has_no_correct_action():
    assert scenarios.correct("unfixable_credentials") == set()
    assert "unfixable_credentials" in unfixable.TARGET


def test_ticket_is_written_redacted_and_judged(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation, "DIR", tmp_path)
    text = escalation.escalate("backend cannot log in", "Access denied for user root, password=hunter2secret",
                               "restarted backend", "rotate the credential")
    assert text.startswith("escalated")
    path = escalation.LAST["path"]
    ticket = json.loads(open(path, encoding="utf-8").read())
    assert "hunter2secret" not in json.dumps(ticket)
    assert escalation.handled(path) is True


def test_a_ticket_that_misses_the_cause_is_not_handled(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation, "DIR", tmp_path)
    escalation.escalate("something is wrong", "the site is slow", "nothing", "look at it")
    assert escalation.handled(escalation.LAST["path"]) is False
    assert escalation.handled(None) is False
    assert escalation.handled(str(tmp_path / "missing.json")) is False


def test_escalate_is_allowed_in_the_reserved_last_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(escalation, "DIR", tmp_path)
    guard = agent.Guard(agent.REGISTRY, agent.ACT, max_steps=12, reserve=2,
                        always={"check_health", "check_invariants", "escalate"})
    guard.steps = 11
    args = {"summary": "s", "findings": "f", "tried": "t", "recommendation": "r"}
    text, blocked = guard.dispatch("escalate", args)
    assert not blocked and text.startswith("escalated")
    guard2 = agent.Guard(agent.REGISTRY, agent.ACT, max_steps=12, reserve=2, always={"check_health"})
    guard2.steps = 11
    assert guard2.dispatch("get_metrics", {})[1] is True
