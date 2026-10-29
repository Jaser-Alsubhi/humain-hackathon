import numpy as np

from eval.calibration import apply_temperature, fit_temperature
from eval.metrics import ece


def test_temperature_reduces_ece():
    rng = np.random.default_rng(0)
    n = 2000
    labels = rng.integers(0, 3, n)
    pred = labels.copy()
    flip = rng.random(n) < 0.3
    pred[flip] = (pred[flip] + 1) % 3
    logits = 5 * np.eye(3)[pred] + rng.normal(0, 0.1, (n, 3))

    def score(lg):
        p = lg if lg.max() <= 1.0 else None
        return p

    from scipy.special import softmax
    before = softmax(logits, axis=1)
    T = fit_temperature(logits, labels)
    after = apply_temperature(logits, T)
    e_before = ece(before.max(1), before.argmax(1) == labels)
    e_after = ece(after.max(1), after.argmax(1) == labels)
    assert T > 1
    assert e_after < e_before
