from collections import Counter

from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression


def make_data(seed=42):
    return make_classification(
        n_samples=600, n_features=10, n_informative=5,
        n_classes=3, random_state=seed)


def majority(Xtr, ytr, Xte):
    c = Counter(ytr).most_common(1)[0][0]
    return [c] * len(Xte)


def logreg(Xtr, ytr, Xte):
    return LogisticRegression(max_iter=500).fit(Xtr, ytr).predict(Xte)
