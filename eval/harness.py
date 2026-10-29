import json
import time
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split

from eval.metrics import classification_metrics
from src.config import SEED, set_seed

RUNS = Path("results/runs.jsonl")


def split(X, y, seed=SEED, test_size=0.2, stratify=True):
    return train_test_split(
        X, y, test_size=test_size, random_state=seed,
        stratify=y if stratify else None)


def git_hash():
    try:
        head = Path(".git/HEAD").read_text().strip()
        if head.startswith("ref:"):
            return Path(".git", head[5:]).read_text().strip()[:7]
        return head[:7]
    except Exception:
        return "unknown"


def log_run(name, seed, config, metrics):
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "name": name,
        "seed": seed,
        "git": git_hash(),
        "config": config,
        "metrics": metrics,
    }
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def run_experiment(name, fit_predict, X, y, seeds=(42, 43, 44), config=None,
                   log=True, metric_fn=classification_metrics,
                   score_key="macro_f1", stratify=True):
    """metric_fn(y_true, y_pred) returns a dict. score_key picks the headline number.
    For lower-is-better metrics (RMSE), return the negative so higher is always better."""
    scores = []
    for s in seeds:
        set_seed(s)
        Xtr, Xte, ytr, yte = split(X, y, seed=s, stratify=stratify)
        pred = fit_predict(Xtr, ytr, Xte)
        m = metric_fn(yte, pred)
        if log:
            log_run(name, s, config or {}, m)
        scores.append(m[score_key])
    mean, std = float(np.mean(scores)), float(np.std(scores))
    return {"mean": mean, "std": std,
            f"mean_{score_key}": mean, f"std_{score_key}": std}
