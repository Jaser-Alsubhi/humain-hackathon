from sklearn.linear_model import LogisticRegression

from eval.holdout import make_holdout
from eval.robustness import robustness_report
from eval.toy_task import make_data


def test_noise_hurts():
    X, y = make_data()
    Xd, Xh, yd, yh = make_holdout(X, y)
    rep = robustness_report(
        "t", lambda: LogisticRegression(max_iter=500), Xd, yd, log=False)
    assert abs(rep["clean"]["drop"]) < 1e-9
    assert rep["noise_1.0"]["macro_f1"] <= rep["clean"]["macro_f1"]
