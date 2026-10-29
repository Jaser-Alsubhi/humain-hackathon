import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from eval.holdout import make_holdout
from eval.robustness import TEXT_DEFAULT, robustness_report


def make_corpus():
    rng = np.random.default_rng(0)
    a = ["alpha", "bravo", "charlie", "delta"]
    b = ["xray", "yankee", "zulu", "whiskey"]
    texts, labels = [], []
    for i in range(200):
        lab = i % 2
        words = list(rng.choice(a if lab == 0 else b, 4)) + list(rng.choice(a + b, 2))
        texts.append(" ".join(str(w) for w in words))
        labels.append(lab)
    return texts, np.array(labels)


def test_text_robustness_report():
    texts, labels = make_corpus()
    rep = robustness_report(
        "text", lambda: make_pipeline(TfidfVectorizer(), LogisticRegression(max_iter=200)),
        texts, labels, perturbations=TEXT_DEFAULT, log=False)
    assert set(TEXT_DEFAULT) == set(rep)
    assert rep["clean"]["drop"] == 0
    assert 0.0 <= rep["typos_15pct"]["macro_f1"] <= 1.0


def test_holdout_without_stratification():
    X = np.arange(200, dtype=float).reshape(-1, 1)
    y = np.linspace(0, 1, 200)
    Xd, Xh, yd, yh = make_holdout(X, y, stratify=False)
    assert len(Xh) == 40
    assert not set(Xd.ravel()) & set(Xh.ravel())
