import pytest

from eval import holdout
from eval.toy_task import logreg, make_data


def test_holdout_is_disjoint_and_stable():
    X, y = make_data()
    a = holdout.make_holdout(X, y)
    b = holdout.make_holdout(X, y)
    assert (a[1] == b[1]).all()
    assert len(a[0]) + len(a[1]) == len(X)
    assert set(map(tuple, a[0])).isdisjoint(set(map(tuple, a[1])))


def test_final_runs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(holdout, "FINAL_LOG", tmp_path / "final.jsonl")
    X, y = make_data()
    Xd, Xh, yd, yh = holdout.make_holdout(X, y)
    holdout.final_evaluation("t", logreg, Xd, yd, Xh, yh)
    with pytest.raises(RuntimeError):
        holdout.final_evaluation("t", logreg, Xd, yd, Xh, yh)
