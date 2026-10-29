from sklearn.datasets import make_regression
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score

from eval.ablation import ablation_report, drop_cols


def _r2(y_true, y_pred):
    return {"r2": float(r2_score(y_true, y_pred))}


def _ridge(Xtr, ytr, Xte):
    return Ridge(alpha=1.0).fit(Xtr, ytr).predict(Xte)


def test_ablation_report_regression_metric():
    X, y = make_regression(n_samples=200, n_features=6, n_informative=3,
                           noise=5.0, shuffle=False, random_state=0)
    variants = {"full": _ridge, "drop_0_1": drop_cols(_ridge, [0, 1])}
    rep = ablation_report(variants, X, y, seeds=(1, 2), log=False,
                          metric_fn=_r2, score_key="r2", stratify=False)
    assert rep["full"]["delta"] == 0.0
    assert "mean_r2" in rep["full"]
    assert rep["drop_0_1"]["delta"] < 0.0
