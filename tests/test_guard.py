from recovery.agent import Guard, redact


def make(**kw):
    calls = []

    def act(service="backend"):
        calls.append(service)
        return "done"

    return Guard({"look": lambda: "seen", "act": act}, {"act"}, **kw), calls


def test_unknown_tool_is_blocked():
    g, _ = make()
    out, blocked = g.dispatch("rm_everything", {})
    assert blocked and "unknown tool" in out


def test_action_budget_stops_actions():
    g, calls = make(max_actions=1)
    g.dispatch("act", {})
    out, blocked = g.dispatch("act", {})
    assert blocked and len(calls) == 1


def test_step_budget_stops_everything():
    g, _ = make(max_steps=1)
    g.dispatch("look", {})
    _, blocked = g.dispatch("look", {})
    assert blocked


def test_dry_run_executes_nothing():
    g, calls = make(dry_run=True)
    out, blocked = g.dispatch("act", {})
    assert calls == [] and "dry-run" in out and not blocked


def test_unexpected_arguments_are_dropped():
    g, calls = make()
    g.dispatch("act", {"service": "db", "evil": "rm -rf /"})
    assert calls == ["db"]


def test_redaction_removes_credentials():
    assert "devpassword" not in redact("mysql+pymysql://root:devpassword@db:3306/hackdb")
    assert "hunter2" not in redact("DB_PASSWORD=hunter2")
    assert "abcdefghijk123" not in redact("key gsk_abcdefghijk123")
    assert "abcdefghijklmnop" not in redact("Authorization: Bearer abcdefghijklmnop")


def test_reserved_steps_block_observation_but_allow_actions():
    from recovery.agent import Guard
    reg = {"look": lambda: "x", "fix": lambda: "ok", "check_health": lambda: "ready"}
    g = Guard(reg, {"fix"}, max_steps=3, reserve=2, always={"check_health"})
    assert g.dispatch("look", {}) == ("x", False)
    assert g.dispatch("look", {})[1] is True
    assert g.dispatch("fix", {}) == ("ok", False)
    assert g.dispatch("check_health", {}) == ("ready", False)


def test_reserve_is_off_by_default():
    from recovery.agent import Guard
    g = Guard({"look": lambda: "x"}, set(), max_steps=2)
    assert g.dispatch("look", {})[1] is False
    assert g.dispatch("look", {})[1] is False


def test_clip_keeps_head_and_tail():
    from recovery.agent import _clip
    out = _clip("A" * 1000 + "B" * 2000)
    assert out.startswith("A" * 300) and out.endswith("B" * 1200) and "trimmed" in out and len(out) < 1600


def test_compact_trims_only_older_tool_outputs():
    from recovery.agent import _compact
    msgs = [{"role": "tool", "content": "x" * 1000} for _ in range(6)]
    _compact(msgs, keep=4)
    assert all(len(m["content"]) < 500 for m in msgs[:2])
    assert all(len(m["content"]) == 1000 for m in msgs[2:])


def test_fuzz_split_is_deterministic_and_disjoint():
    from recovery import fuzz
    every = set(fuzz.FIX)
    dev = fuzz.make(1, 8, every - fuzz.HELDOUT_ONLY)
    assert dev == fuzz.make(1, 8, every - fuzz.HELDOUT_ONLY)
    held = fuzz.make(2, 12, every, need_heldout=True, exclude={fuzz.key(s) for s in dev})
    assert not {fuzz.key(s) for s in dev} & {fuzz.key(s) for s in held}
    assert all(not {f["p"] for f in s["faults"]} & fuzz.HELDOUT_ONLY for s in dev)
    assert all({f["p"] for f in s["faults"]} & fuzz.HELDOUT_ONLY for s in held)


def test_wilson_interval():
    from recovery.fuzz import wilson
    lo, hi = wilson(17, 18)
    assert 0.70 < lo < 0.78 and 0.98 < hi <= 1.0


def test_hint_seconds_parses_the_server_message():
    from recovery.agent import _hint_seconds

    class E(Exception):
        pass

    assert abs(_hint_seconds(E("Please try again in 16m6.384s.")) - 966.384) < 0.01
    assert _hint_seconds(E("try again in 2m25.584s")) > 140
    assert _hint_seconds(E("nothing to see here")) is None


def settle_guard(ready_after):
    clock = {"t": 0.0}
    calls = []

    def restart_service(service):
        calls.append(service)
        return "ok"

    def wait(seconds):
        if clock["t"] >= ready_after:
            return True
        clock["t"] += seconds
        return clock["t"] >= ready_after

    g = Guard({"restart_service": restart_service}, {"restart_service"}, depends={"backend": {"db"}, "frontend": {"backend"}},
              settle=12, wait=wait, clock=lambda: clock["t"])
    return g, calls, clock


def test_settle_blocks_a_dependent_when_the_site_recovers_by_itself():
    g, calls, clock = settle_guard(ready_after=5)
    g.dispatch("restart_service", {"service": "db"})
    clock["t"] = 1
    out, blocked = g.dispatch("restart_service", {"service": "backend"})
    assert blocked and "not needed" in out and calls == ["db"]


def test_settle_allows_the_dependent_if_the_site_stays_down():
    g, calls, clock = settle_guard(ready_after=1000)
    g.dispatch("restart_service", {"service": "db"})
    clock["t"] = 1
    out, blocked = g.dispatch("restart_service", {"service": "backend"})
    assert not blocked and calls == ["db", "backend"]


def test_settle_ignores_services_that_do_not_depend_on_the_one_just_changed():
    g, calls, clock = settle_guard(ready_after=5)
    g.dispatch("restart_service", {"service": "db"})
    out, blocked = g.dispatch("restart_service", {"service": "frontend"})
    assert not blocked and calls == ["db", "frontend"]


def test_dependencies_are_read_from_the_compose_file():
    from recovery import ops
    assert ops.dependencies() == {"backend": {"db"}, "frontend": {"backend"}}
