import platform
import time
from pathlib import Path

import sklearn
from sklearn.linear_model import LogisticRegression

from eval.ablation import ablation_report, drop_cols
from eval.harness import git_hash, run_experiment
from eval.holdout import make_holdout
from eval.robustness import robustness_report
from eval.toy_task import logreg, majority, make_data

SEEDS = (42, 43, 44)


def logreg_c(C):
    def fit_predict(Xtr, ytr, Xte):
        return LogisticRegression(C=C, max_iter=500).fit(Xtr, ytr).predict(Xte)
    return fit_predict


def run_all(out="results/report.md", log=True):
    # Friday: swap make_data, the models and the ablation variants for the real task.
    X, y = make_data()
    Xd, Xh, yd, yh = make_holdout(X, y)

    models = {"majority": majority, "logreg": logreg}
    results = {
        name: run_experiment(name, fn, Xd, yd, seeds=SEEDS, log=log)
        for name, fn in models.items()
    }

    variants = {
        "full (C=1)": logreg,
        "drop features 0-4": drop_cols(logreg, range(5)),
        "drop features 5-9": drop_cols(logreg, range(5, 10)),
        "strong regularisation (C=0.01)": logreg_c(0.01),
    }
    ablations = ablation_report(variants, Xd, yd, seeds=SEEDS, log=log)

    robust = robustness_report(
        "logreg", lambda: LogisticRegression(max_iter=500),
        Xd, yd, seeds=SEEDS, log=log)

    lines = [
        "# Evaluation report",
        "",
        "- Date: " + time.strftime("%Y-%m-%d %H:%M:%S"),
        "- Git commit at run time: " + git_hash(),
        "- Seeds: " + ", ".join(str(s) for s in SEEDS),
        "- Python: " + platform.python_version(),
        "- scikit-learn: " + sklearn.__version__,
        "",
        "## Results (dev split, mean and std over seeds)",
        "",
        "| Model | Macro F1 | Std |",
        "|---|---|---|",
    ]
    for name, r in results.items():
        lines.append(
            f"| {name} | {r['mean_macro_f1']:.3f} | {r['std_macro_f1']:.3f} |")
    lines += [
        "",
        "## Ablations (logreg, delta against the full model)",
        "",
        "| Variant | Macro F1 | Std | Delta |",
        "|---|---|---|---|",
    ]
    for name, a in ablations.items():
        lines.append(
            f"| {name} | {a['mean_macro_f1']:.3f} | {a['std_macro_f1']:.3f} | {a['delta']:+.3f} |")
    lines += [
        "",
        "## Robustness (logreg)",
        "",
        "| Perturbation | Macro F1 | Drop |",
        "|---|---|---|",
    ]
    for k, v in robust.items():
        lines.append(f"| {k} | {v['macro_f1']:.3f} | {v['drop']:.3f} |")
    lines += [
        "",
        "## Notes",
        "",
        "- The held-out set is untouched. The final evaluation runs once.",
        "- Every run is logged to results/runs.jsonl with git hash and seed.",
        "",
    ]
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return results, ablations, robust


if __name__ == "__main__":
    run_all()
    print("Report written to results/report.md")
