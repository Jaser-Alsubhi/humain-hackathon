"""Automatic monitor: it watches the stack, notices a failure without being told, and starts the agent by itself.
python -m recovery.watch [--once] [--dry-run] [--interval 5]
Break something from a second terminal: python -m recovery.break_it <scenario>
The alert is built only from the monitor's own measurements. It carries no scenario name and no hint about the cause."""
import sys
import time
from datetime import datetime

from recovery import agent, escalation, ops, silent

CONFIRM = 2        # consecutive failing checks before the agent starts, so a restart in progress is not an incident
MAX_ATTEMPTS = 2   # agent attempts per incident, then the monitor leaves it to a human
DATA_KEYS = ("orders_missing", "payments_missing", "amount_mismatch", "ledger_missing", "ledger_mismatch")


def sense():
    """One round of checks: is the site ready, and if it is, do the data checks pass."""
    sig = {"ready": ops.http("/ready", timeout=5)[0]}
    if sig["ready"] == 200:
        sig["data"] = silent.invariants()
    return sig


def assess(sig):
    """None when healthy, else (alert text, data_mode). data_mode is True when the readiness check passes but the data is wrong."""
    if sig["ready"] != 200:
        return ("ALERT (automated monitor): the readiness check is failing (%s). Investigate and fix it."
                % ("HTTP %s" % sig["ready"] if sig["ready"] else "no response"), False)
    inv = sig.get("data") or {}
    if inv.get("clean") is True:
        return None
    if "error" in inv:
        detail = "the data check could not run: " + str(inv["error"])[:120]
    else:
        bad = ["%s=%s" % (k, inv[k]) for k in DATA_KEYS if inv.get(k)]
        detail = "the data checks fail (%s)" % (", ".join(bad) or "see check_invariants")
    return ("ALERT (automated monitor): the readiness check passes, but %s. Investigate and fix it." % detail, True)


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def main(argv):
    once, dry = "--once" in argv, "--dry-run" in argv
    interval = float(argv[argv.index("--interval") + 1]) if "--interval" in argv else 5.0
    log("monitor started: checking /ready and the data checks every %gs. Press Ctrl+C to stop." % interval)
    bad, attempts, announced, healthy_logged = 0, 0, False, True
    while True:
        found = assess(sense())
        if found is None:
            if not healthy_logged:
                log("healthy again")
                if once and attempts:
                    return 0
            bad, attempts, announced, healthy_logged = 0, 0, False, True
            time.sleep(interval)
            continue
        healthy_logged = False
        bad += 1
        log("check failing (%d/%d): %s" % (min(bad, CONFIRM), CONFIRM, found[0].split(": ", 1)[1].split(" Investigate")[0]))
        if bad < CONFIRM:
            time.sleep(interval)
            continue
        if attempts >= MAX_ATTEMPTS:
            if not announced:
                log("paused: the agent could not fix this. A human is needed.")
                announced = True
            time.sleep(interval)
            continue
        attempts += 1
        log("incident detected, starting the agent (attempt %d of %d)" % (attempts, MAX_ATTEMPTS))
        r = agent.run("live", dry_run=dry, alert=found[0], data_mode=found[1])
        log("agent finished: recovered=%s steps=%d actions=%d %.0fs tokens=%d" % (
            r["recovered"], r["steps"], r["actions"], r["seconds"], r["tokens"]))
        if str(r.get("final", "")).startswith("escalated to a human"):
            log("handed over to a human. Ticket: %s" % (escalation.LAST.get("path") or "see results/tickets"))
            attempts = MAX_ATTEMPTS
            if once:
                return 0
        elif r["recovered"]:
            bad = 0
            if once:
                return 0
        elif once and attempts >= MAX_ATTEMPTS:
            return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        log("monitor stopped")
