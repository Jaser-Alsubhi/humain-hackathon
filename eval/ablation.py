from eval.harness import run_experiment
from eval.metrics import classification_metrics


def drop_cols(fit_predict, cols):
    drop = set(cols)

    def wrapped(Xtr, ytr, Xte):
        keep = [i for i in range(Xtr.shape[1]) if i not in drop]
        return fit_predict(Xtr[:, keep], ytr, Xte[:, keep])
    return wrapped


def ablation_report(variants, X, y, seeds=(42, 43, 44), log=True,
                    metric_fn=classification_metrics, score_key="macro_f1",
                    stratify=True):
    """First variant is the reference. Delta is the change in the mean score against it."""
    out = {}
    base = None
    key = "mean_" + score_key
    for name, fn in variants.items():
        r = run_experiment("ablation:" + name, fn, X, y, seeds=seeds, log=log,
                           metric_fn=metric_fn, score_key=score_key,
                           stratify=stratify)
        if base is None:
            base = r[key]
        out[name] = {**r, "delta": r[key] - base}
    return out
