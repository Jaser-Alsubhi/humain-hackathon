import json
from pathlib import Path

from eval.harness import run_experiment
from eval.holdout import make_holdout
from eval.toy_task import logreg, make_data


def test_no_regression():
    X, y = make_data()
    Xd, Xh, yd, yh = make_holdout(X, y)
    result = run_experiment("ci-logreg", logreg, Xd, yd, log=False)
    baseline = json.loads(Path("eval/baseline.json").read_text())
    assert result["mean_macro_f1"] >= baseline["mean_macro_f1"] - 0.02
