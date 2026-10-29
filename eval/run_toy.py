import json
from pathlib import Path

from eval.harness import run_experiment
from eval.holdout import make_holdout
from eval.toy_task import logreg, majority, make_data

X, y = make_data()
Xd, Xh, yd, yh = make_holdout(X, y)
results = {}
for name, fn in [("majority", majority), ("logreg", logreg)]:
    results[name] = run_experiment(name, fn, Xd, yd)
    print(name, results[name])

baseline = Path("eval/baseline.json")
if not baseline.exists():
    baseline.write_text(json.dumps(results["logreg"]))
    print("baseline saved")
