"""Fault fuzzer: random combinations of fault primitives, a locked dev/held-out split, an oracle check and statistics.
python -m recovery.fuzz --generate            create results/fuzz_manifest.json once (--force to overwrite)
python -m recovery.fuzz --oracle dev|heldout  check every scenario breaks the stack and its scripted fix repairs it (no LLM)
python -m recovery.fuzz --generate-fresh     add a third split of 12 new faults (dev and held-out are not touched)
python -m recovery.fuzz --report              recovery rate with 95% Wilson intervals, by split and number of faults
Agent runs: python -m recovery.evaluate --set dev|heldout --methods runbook,agent"""
import hashlib
import json
import math
import random
import re
import sys
import time
from pathlib import Path

from recovery import ops

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results" / "fuzz_manifest.json"
EVAL = ROOT / "results" / "recovery_eval.json"
SEED = 20261030

# At most one primitive per slot, so injected faults never contradict each other. Each maps to the actions that fix it.
SLOTS = {
    "db": {"db_stop": {"start_service:db"}, "db_pause": {"unpause_service:db"}, "db_exhaust": {"restart_service:db"}},
    "config": {"cfg_host": {"rollback_config"}, "cfg_password": {"rollback_config"}, "cfg_dbname": {"rollback_config"}},
    "backend": {"be_stop": {"start_service:backend"}, "be_pause": {"unpause_service:backend"}},
}
FIX = {p: fixes for slot in SLOTS.values() for p, fixes in slot.items()}
ORDER = list(FIX)
# Primitives that never appear in the dev split, so the held-out set contains faults the prompt was never tuned on.
HELDOUT_ONLY = {"cfg_password", "cfg_dbname", "be_stop", "be_pause"}
ARGS = {
    "cfg_host": ["db-old", "db-legacy", "mysql-primary", "database"],
    "cfg_password": ["wrongpass", "rotated2026", "changeme"],
    "cfg_dbname": ["hackdb_old", "app", "hackdb2"],
}


def key(spec):
    return tuple((f["p"], f.get("arg")) for f in spec["faults"])


def make(seed, n, allowed, need_heldout=False, exclude=()):
    rng = random.Random(seed)  # nosec B311 - reproducible test data, not security
    out, seen = [], set(exclude)
    for _ in range(10000):
        if len(out) == n:
            break
        faults = []
        for slot in rng.sample(list(SLOTS), rng.choice([1, 1, 2, 2, 3])):
            options = sorted(p for p in SLOTS[slot] if p in allowed)
            if options:
                p = rng.choice(options)
                faults.append({"p": p, "arg": rng.choice(ARGS[p]) if p in ARGS else None})
        faults.sort(key=lambda f: ORDER.index(f["p"]))
        spec = {"faults": faults}
        if not faults or key(spec) in seen:
            continue
        if need_heldout and not {f["p"] for f in faults} & HELDOUT_ONLY:
            continue
        seen.add(key(spec))
        spec["id"] = "fz-" + hashlib.sha256(json.dumps(faults, sort_keys=True).encode()).hexdigest()[:6]
        out.append(spec)
    return out


def describe(spec):
    return " + ".join(f["p"] + ("=" + f["arg"] if f.get("arg") else "") for f in spec["faults"])


def correct(spec):
    return set().union(*(FIX[f["p"]] for f in spec["faults"]))


def _exhaust():
    from recovery import scenarios
    ops.mark_db_dirty()
    ops.compose("exec", "-T", "db", "sh", "-c", scenarios.LIMIT)
    ops.compose("exec", "-d", "db", "sh", "-c", scenarios.HOG)
    time.sleep(3)
    ops.compose("restart", "backend")


def _cfg(kind, arg):
    good = ops.config_text(version="fz-" + kind)
    if kind == "cfg_host":
        bad = ops.config_text(host=arg, version="fz-" + kind)
    elif kind == "cfg_password":
        bad = re.sub(r"(root:)[^@\s]+(@)", lambda m: m.group(1) + arg + m.group(2), good)
    else:
        bad = re.sub(r"(:3306/)\w+", lambda m: m.group(1) + arg, good)
    assert bad != good, "fault %s did not change the config" % kind
    ops.write_config(ops.ACTIVE, bad)
    ops.compose("up", "-d", "--no-deps", "backend")


PRIMS = {
    "db_stop": lambda a: ops.compose("stop", "db"),
    "db_pause": lambda a: ops.compose("pause", "db"),
    "db_exhaust": lambda a: _exhaust(),
    "cfg_host": lambda a: _cfg("cfg_host", a),
    "cfg_password": lambda a: _cfg("cfg_password", a),
    "cfg_dbname": lambda a: _cfg("cfg_dbname", a),
    "be_stop": lambda a: ops.compose("stop", "backend"),
    "be_pause": lambda a: ops.compose("pause", "backend"),
}


def inject(spec):
    for f in spec["faults"]:
        PRIMS[f["p"]](f.get("arg"))


def _digest(specs):
    return hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()


def generate(force=False):
    if MANIFEST.exists() and not force:
        print("manifest already exists, not overwriting (use --force)")
        return
    every = set(FIX)
    dev = make(SEED, 8, every - HELDOUT_ONLY)
    held = make(SEED + 1, 12, every, need_heldout=True, exclude={key(s) for s in dev})
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps({"seed": SEED, "dev": dev, "heldout": held, "heldout_sha256": _digest(held)}, indent=2), encoding="utf-8")
    for split, specs_ in (("dev", dev), ("heldout", held)):
        print("%s: %d scenarios" % (split, len(specs_)))
        for s in specs_:
            print("  %s  %s" % (s["id"], describe(s)))


def generate_fresh():
    """A third split of 12 new faults, added to the manifest without touching dev or held-out (the held-out hash stays valid)."""
    m = load()
    if "fresh" in m:
        print("fresh split already exists")
        return
    used = {key(s) for s in m["dev"] + m["heldout"]}
    m["fresh"] = make(SEED + 2, 12, set(FIX), need_heldout=True, exclude=used)
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
    print("fresh: %d scenarios" % len(m["fresh"]))
    for s in m["fresh"]:
        print("  %s  %s" % (s["id"], describe(s)))


def load():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def specs(split):
    m = load()
    if split == "heldout" and _digest(m["heldout"]) != m["heldout_sha256"]:
        raise SystemExit("held-out set was modified after it was locked")
    return m[split]


def ids(split):
    return [s["id"] for s in specs(split)]


def lookup(name):
    m = load()
    for s in m["dev"] + m["heldout"] + m.get("fresh", []):
        if s["id"] == name:
            return s
    raise ValueError(name)


def _do(action):
    name, _, service = action.partition(":")
    fn = getattr(ops, name)
    return fn(service) if service else fn()


def oracle(split, only=None):
    from recovery import scenarios
    bad = 0
    chosen = [s for s in specs(split) if only is None or s["id"] == only]
    for s in chosen:
        scenarios.reset()
        inject(s)
        time.sleep(6)
        broken = ops.check_health()["ready"][0] != 200
        for f in s["faults"]:
            for action in sorted(FIX[f["p"]]):
                _do(action)
        fixed = ops.wait_ready(90)
        ok = broken and fixed
        bad += not ok
        print("%-10s broken=%-5s fixed=%-5s %-6s %s" % (s["id"], broken, fixed, "OK" if ok else "CHECK", describe(s)))
    scenarios.reset()
    print("%d scenarios, %d need attention" % (len(chosen), bad))


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def report():
    m = load()
    rows = json.loads(EVAL.read_text(encoding="utf-8")) if EVAL.exists() else []
    print("%-8s %-8s %-26s %-6s %-8s %-6s %-14s %s" % ("split", "method", "model", "faults", "recov", "rate", "95% CI", "wrong/trial"))
    for split in ("dev", "heldout", "fresh"):
        if split not in m:
            continue
        size = {s["id"]: len(s["faults"]) for s in m[split]}
        mine = [r for r in rows if r["scenario"] in size and "error" not in r]
        for method, model in sorted({(r["method"], r.get("model", "-")) for r in mine}):
            sel = [r for r in mine if r["method"] == method and r.get("model", "-") == model]
            for k in (1, 2, 3, None):
                g = sel if k is None else [r for r in sel if size[r["scenario"]] == k]
                if not g:
                    continue
                ok = sum(r["recovered"] for r in g)
                lo, hi = wilson(ok, len(g))
                w = sum(r.get("wrong_actions", 0) for r in g) / len(g)
                print("%-8s %-8s %-26s %-6s %3d/%-4d %4.0f%%  [%3.0f%%, %3.0f%%]  %.2f" % (
                    split, method, model, "all" if k is None else k, ok, len(g), 100 * ok / len(g), 100 * lo, 100 * hi, w))


def main():
    a = sys.argv[1:]
    if "--generate-fresh" in a:
        generate_fresh()
    elif "--generate" in a:
        generate(force="--force" in a)
    elif "--oracle" in a:
        i = a.index("--oracle")
        oracle(a[i + 1], a[i + 2] if len(a) > i + 2 else None)
    elif "--report" in a:
        report()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
