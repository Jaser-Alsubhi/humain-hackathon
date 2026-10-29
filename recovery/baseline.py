"""Baselines without a model: a naive restart, and a scripted runbook with fixed rules."""
import time

from recovery import ops


def naive():
    started = time.time()
    ops.restart_service("backend")
    ok = ops.wait_ready(20)
    return {"recovered": ok, "actions": 1, "seconds": time.time() - started,
            "sequence": ["restart_service:backend"]}


def runbook():
    """Rules: start exited containers, unpause paused ones, roll back a changed config."""
    started = time.time()
    actions = []
    for line in ops.service_status().lower().splitlines():
        svc = line.split(":")[0].strip()
        if svc not in ops.SERVICES:
            continue
        if "paused" in line:
            ops.unpause_service(svc)
            actions.append("unpause_service:" + svc)
        elif "exited" in line or "created" in line:
            ops.start_service(svc)
            actions.append("start_service:" + svc)
    if ops.config_changes() != "active config matches last known good":
        ops.rollback_config()
        actions.append("rollback_config")
    ok = ops.wait_ready(45)
    return {"recovered": ok, "actions": len(actions), "seconds": time.time() - started, "sequence": actions}
