from sklearn.linear_model import LogisticRegression

from eval.holdout import make_holdout
from eval.robustness import robustness_report
from eval.toy_task import make_data

X, y = make_data()
Xd, Xh, yd, yh = make_holdout(X, y)
rep = robustness_report("logreg", lambda: LogisticRegression(max_iter=500), Xd, yd)
for k, v in rep.items():
    print(f"{k:15} macro_f1={v['macro_f1']:.3f} drop={v['drop']:.3f}")
