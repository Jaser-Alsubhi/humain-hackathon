import numpy as np
from sklearn.linear_model import LinearRegression

from eval.harness import run_experiment
from eval.toy_task import logreg, make_data


def test_custom_score_key():
    X, y = make_data()
    r = run_experiment("t", logreg, X, y, log=False, score_key="accuracy")
    assert r["mean"] == r["mean_accuracy"]


def test_regression_without_stratification():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 3))
    y = X @ np.array([1.0, 2.0, 3.0]) + rng.normal(scale=0.1, size=200)

    def fit_predict(Xtr, ytr, Xte):
        return LinearRegression().fit(Xtr, ytr).predict(Xte)

    def neg_rmse(y_true, y_pred):
        return {"neg_rmse": -float(np.sqrt(np.mean((y_true - y_pred) ** 2)))}

    r = run_experiment("reg", fit_predict, X, y, log=False, metric_fn=neg_rmse,
                       score_key="neg_rmse", stratify=False)
    assert r["mean"] > -0.5
