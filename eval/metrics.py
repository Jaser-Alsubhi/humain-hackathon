import numpy as np
from sklearn.metrics import accuracy_score, f1_score


def classification_metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro")),
    }


def ece(confidences, correct, n_bins=10):
    conf = np.asarray(confidences, dtype=float)
    ok = np.asarray(correct, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs(ok[m].mean() - conf[m].mean())
    return float(total)
