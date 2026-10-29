"""Dev-extra faults: realistic failures the scripted runbook has no rule for.
Designed knowing the runbook's rules, so this set shows what needs diagnosis. It is not an unbiased test; the locked held-out set is.
python -m recovery.faults_extra --oracle     check every fault breaks the stack and its scripted fix repairs it (no LLM)
Agent runs: python -m recovery.evaluate --set extra --methods naive,runbook,agent"""
import sys
import time

from recovery import fuzz, ops

FLAG = ops.OPS / "extra.flag"
MEMORY = "24m"


def _cid(service):
    return ops.compose("ps", "-a", "-q", service)[1].split()[-1]


def _unplug(service):
    """Detach a container from the compose network, as a network fault would."""
    cid = _cid(service)
    fmt = "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}"
    net = ops.sh(["docker", "inspect", "-f", fmt, cid])[1].split()[0]
    ops.sh(["docker", "network", "disconnect", net, cid])


def _hang():
    """Freeze the backend process. The container still reports running."""
    ops.compose("kill", "-s", "SIGSTOP", "backend")


def _oom():
    """Give the backend container a memory limit it cannot live within."""
    cid = _cid("backend")
    ops.compose("stop", "backend")
    ops.sh(["docker", "update", "--memory", MEMORY, "--memory-swap", MEMORY, cid])
    ops.compose("start", "backend")


def _both(first, second):
    def run():
        first()
        second()
    return run


# name: (inject, the actions that genuinely fix it, in order)
EXTRA = {
    "hung_backend": (_hang, ["restart_service:backend"]),
    "backend_unplugged": (lambda: _unplug("backend"), ["recreate_service:backend"]),
    "backend_oom": (_oom, ["recreate_service:backend"]),
    "db_unplugged": (lambda: _unplug("db"), ["recreate_service:db"]),
    "hung_exhaust": (_both(fuzz._exhaust, _hang), ["restart_service:db", "restart_service:backend"]),
    "unplugged_exhaust": (_both(fuzz._exhaust, lambda: _unplug("backend")), ["restart_service:db", "recreate_service:backend"]),
}


def names():
    return list(EXTRA)


def correct(name):
    return set(EXTRA[name][1])


def inject(name):
    ops.OPS.mkdir(exist_ok=True)
    FLAG.write_text("1", encoding="utf-8")
    EXTRA[name][0]()


def oracle():
    from recovery import scenarios
    bad = 0
    for name in names():
        scenarios.reset()
        scenarios.inject(name)
        time.sleep(6)
        broken = ops.check_health()["ready"][0] != 200
        for action in EXTRA[name][1]:
            act, _, service = action.partition(":")
            getattr(ops, act)(service)
        fixed = ops.wait_ready(90)
        ok = broken and fixed
        bad += not ok
        print("%-18s broken=%-5s fixed=%-5s %s" % (name, broken, fixed, "OK" if ok else "CHECK"))
    scenarios.reset()
    print("%d faults, %d need attention" % (len(EXTRA), bad))


if __name__ == "__main__":
    if "--oracle" in sys.argv:
        oracle()
    else:
        print(__doc__)
