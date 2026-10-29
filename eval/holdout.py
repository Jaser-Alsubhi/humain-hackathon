import json
import time
from pathlib import Path

from sklearn.model_selection import train_test_split

from eval.harness import git_hash
from eval.metrics import classification_metrics

HOLDOUT_SEED = 2026
FINAL_LOG = Path("results/final_runs.jsonl")


def make_holdout(X, y, frac=0.2, stratify=True):
    Xd, Xh, yd, yh = train_test_split(
        X, y, test_size=frac, random_state=HOLDOUT_SEED,
        stratify=y if stratify else None)
    return Xd, Xh, yd, yh


def final_evaluation(name, fit_predict, Xd, yd, Xh, yh, config=None,
                     allow_repeat=False, metric_fn=classification_metrics):
    if FINAL_LOG.exists() and not allow_repeat:
        raise RuntimeError("Held-out set already used. Final evaluation runs once.")
    pred = fit_predict(Xd, yd, Xh)
    m = metric_fn(yh, pred)
    FINAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "name": name,
        "git": git_hash(),
        "config": config or {},
        "metrics": m,
    }
    with FINAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return m
