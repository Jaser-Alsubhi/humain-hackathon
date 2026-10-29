import numpy as np

from eval.harness import log_run, split
from eval.metrics import classification_metrics
from src.config import set_seed


def noise(scale):
    def f(X, seed=0):
        rng = np.random.default_rng(seed)
        return X + rng.normal(0, 1, X.shape) * X.std(axis=0) * scale
    return f


def missing(frac):
    def f(X, seed=0):
        rng = np.random.default_rng(seed)
        out = X.copy()
        mask = rng.random(X.shape) < frac
        out[mask] = np.broadcast_to(X.mean(axis=0), X.shape)[mask]
        return out
    return f


def shift(delta):
    def f(X, seed=0):
        return X + delta * X.std(axis=0)
    return f


DEFAULT = {
    "clean": lambda X, seed=0: X,
    "noise_0.5": noise(0.5),
    "noise_1.0": noise(1.0),
    "missing_30pct": missing(0.3),
    "shift_1std": shift(1.0),
}


# Text perturbations: each takes a list of strings and returns a list of strings.
def typos(frac):
    def f(texts, seed=0):
        rng = np.random.default_rng(seed)
        out = []
        for t in texts:
            chars = list(t)
            for i in range(len(chars) - 1):
                if rng.random() < frac:
                    chars[i], chars[i + 1] = chars[i + 1], chars[i]
            out.append("".join(chars))
        return out
    return f


def truncate(frac):
    def f(texts, seed=0):
        out = []
        for t in texts:
            words = t.split()
            keep = max(1, int(round(len(words) * (1 - frac))))
            out.append(" ".join(words[:keep]))
        return out
    return f


def upper(texts, seed=0):
    return [t.upper() for t in texts]


TEXT_DEFAULT = {
    "clean": lambda X, seed=0: X,
    "typos_5pct": typos(0.05),
    "typos_15pct": typos(0.15),
    "truncate_30pct": truncate(0.3),
    "uppercase": upper,
}


def robustness_report(name, make_model, X, y, perturbations=None,
                      seeds=(42, 43, 44), log=True,
                      metric_fn=classification_metrics, score_key="macro_f1",
                      stratify=True):
    """make_model() must return an object with fit(X, y) and predict(X).
    For a non-sklearn pipeline, wrap it in a small class with those two methods.
    Drop is clean minus perturbed, so the metric must be higher-is-better."""
    perturbations = perturbations or DEFAULT
    scores = {k: [] for k in perturbations}
    for s in seeds:
        set_seed(s)
        Xtr, Xte, ytr, yte = split(X, y, seed=s, stratify=stratify)
        model = make_model().fit(Xtr, ytr)
        for k, fn in perturbations.items():
            m = metric_fn(yte, model.predict(fn(Xte, s)))
            scores[k].append(m[score_key])
            if log:
                log_run(name + ":" + k, s, {"perturbation": k}, m)
    clean = float(np.mean(scores["clean"]))
    return {
        k: {score_key: float(np.mean(v)), "score": float(np.mean(v)),
            "drop": clean - float(np.mean(v))}
        for k, v in scores.items()
    }
