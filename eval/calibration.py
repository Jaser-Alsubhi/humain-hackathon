import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax


def nll(logits, labels, T):
    lp = log_softmax(np.asarray(logits) / T, axis=1)
    return float(-lp[np.arange(len(labels)), labels].mean())


def fit_temperature(logits, labels):
    res = minimize_scalar(
        lambda t: nll(logits, labels, np.exp(t)),
        bounds=(-3, 3), method="bounded")
    return float(np.exp(res.x))


def apply_temperature(logits, T):
    return softmax(np.asarray(logits) / T, axis=1)
