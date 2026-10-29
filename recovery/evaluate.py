"""Compare a naive restart, a scripted runbook and the LLM agent on every scenario.
python -m recovery.evaluate [--methods naive,runbook,agent] [--scenarios db_down,compound] [--repeats 3]
The agent model is read from .env (LLM_MODEL) and stored on every agent row.
Results are saved after every trial. Re-running a scenario, method and model replaces its earlier rows."""
import json
import os
import sys
import time
from pathlib import Path

from recovery import agent, baseline, scenarios

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "recovery_eval.json"


def arg(flag, default):
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1].split(",")
    return default


def model_name():
    env = ROOT / ".env"
    values = {}
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    ladder = [m.split("/")[-1] for m in values.get("LLM_LADDER", "").split(",") if m.strip()]
    if ladder:
        return ">".join(ladder)
    return values.get("LLM_MODEL", os.environ.get("LLM_MODEL", "unknown")).split("/")[-1]


def model_for(method):
    return model_name() if method == "agent" else "-"


def wrong_actions(name, sequence):
    done = [a for a in sequence if a.split(":")[0] in agent.ACT]
    return [a for a in done if a not in scenarios.correct(name)]


def trial(name, method):
    scenarios.reset()
    scenarios.inject(name)
    time.sleep(6)
    try:
        if method == "naive":
            r = baseline.naive()
        elif method == "runbook":
            r = baseline.runbook()
        else:
            a = agent.run(name, verbose=False)
            t = a["time_to_recover"]
            r = {"recovered": a["recovered"], "actions": a["actions"], "tokens": a["tokens"],
                 "steps": a["steps"], "verified": a["verified"], "bad_json": a["bad_json"],
                 "sequence": a["executed"], "calls": a["sequence"], "llm_seconds": round(a["llm_seconds"]),
                 "rate_retries": a["rate_retries"], "nudges": a.get("nudges", 0), "wait_seconds": a.get("wait_seconds", 0),
                 "models": a.get("models", {}), "escalated_at": a.get("escalated_at"), "seconds": t if t is not None else a["seconds"]}
        r["wrong_actions"] = len(wrong_actions(name, r.get("sequence", [])))
    except Exception as e:
        r = {"recovered": False, "actions": 0, "seconds": 0, "error": type(e).__name__, "detail": agent.redact(str(e))[:500]}
    r.update(scenario=name, method=method, model=model_for(method))
    return r


def load():
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []


def save(rows):
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def summary(rows):
    print("\nRESULTS (all saved runs)")
    print("%-12s %-8s %-26s %-10s %6s %7s %6s %6s" % ("scenario", "method", "model", "recovered", "secs", "tokens", "wrong", "errors"))
    for name in scenarios.NAMES + sorted({r["scenario"] for r in rows} - set(scenarios.NAMES)):
        for method in ["naive", "runbook", "agent"]:
            models = sorted({r.get("model", "-") for r in rows if r["scenario"] == name and r["method"] == method})
            for model in models:
                mine = [r for r in rows if r["scenario"] == name and r["method"] == method and r.get("model", "-") == model]
                errors = len([r for r in mine if "error" in r])
                mine = [r for r in mine if "error" not in r]
                if not mine:
                    print("%-12s %-8s %-26s no valid trials, %d infrastructure errors" % (name, method, model, errors))
                    continue
                ok = sum(r["recovered"] for r in mine)
                secs = sum(r["seconds"] for r in mine) / len(mine)
                tok = sum(r.get("tokens", 0) for r in mine) / len(mine)
                w = [r["wrong_actions"] for r in mine if "wrong_actions" in r]
                print("%-12s %-8s %-26s %d/%-8d %5.0fs %7.0f %6s %6d" % (
                    name, method, model, ok, len(mine), secs, tok, "%.1f" % (sum(w) / len(w)) if w else "-", errors))


def main():
    methods = arg("--methods", ["naive", "runbook", "agent"])
    names = arg("--scenarios", scenarios.NAMES)
    split = arg("--set", [""])[0]
    if split == "extra":
        from recovery import faults_extra
        names = faults_extra.names()
    elif split:
        from recovery import fuzz
        names = fuzz.ids(split)
        done = {(r["scenario"], r["method"], r.get("model", "-")) for r in load()}
        if split == "heldout" and "--force" not in sys.argv and any((n, m, model_for(m)) in done for n in names for m in methods):
            print("Held-out results already exist for this method and model. It is run once; use --force to override.")
            return
    repeats = int(arg("--repeats", ["1"])[0])
    pause = int(arg("--pause", ["15"])[0])
    replaced = {(n, m, model_for(m)) for n in names for m in methods}
    rows = [r for r in load() if (r["scenario"], r["method"], r.get("model", "-")) not in replaced]
    for name in names:
        for method in methods:
            for run in range(repeats):
                r = trial(name, method)
                if "error" in r and "per day" not in r.get("detail", ""):
                    print("   infrastructure error (%s), waiting 60s and retrying once: %s" % (r["error"], r.get("detail", "")[:300]))
                    time.sleep(60)
                    r = trial(name, method)
                r["run"] = run
                rows.append(r)
                save(rows)
                print("%-12s %-8s recovered=%-5s actions=%d wrong=%s %5.0fs tokens=%s %s" % (
                    name, method, r["recovered"], r["actions"], r.get("wrong_actions", "-"),
                    r["seconds"], r.get("tokens", "-"), r.get("error", "")))
                if method == "agent":
                    time.sleep(pause)
    scenarios.reset()
    summary(rows)


if __name__ == "__main__":
    main()
