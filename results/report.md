# Evaluation report

- Date: 2026-10-28 03:29:39
- Git commit at run time: 4a915c6
- Seeds: 42, 43, 44
- Python: 3.11.9
- scikit-learn: 1.9.1

## Results (dev split, mean and std over seeds)

| Model | Macro F1 | Std |
|---|---|---|
| majority | 0.167 | 0.000 |
| logreg | 0.651 | 0.018 |

## Ablations (logreg, delta against the full model)

| Variant | Macro F1 | Std | Delta |
|---|---|---|---|
| full (C=1) | 0.651 | 0.018 | +0.000 |
| drop features 0-4 | 0.525 | 0.021 | -0.126 |
| drop features 5-9 | 0.553 | 0.020 | -0.097 |
| strong regularisation (C=0.01) | 0.642 | 0.014 | -0.008 |

## Robustness (logreg)

| Perturbation | Macro F1 | Drop |
|---|---|---|
| clean | 0.651 | 0.000 |
| noise_0.5 | 0.566 | 0.085 |
| noise_1.0 | 0.502 | 0.149 |
| missing_30pct | 0.553 | 0.097 |
| shift_1std | 0.504 | 0.146 |

## Notes

- The held-out set is untouched. The final evaluation runs once.
- Every run is logged to results/runs.jsonl with git hash and seed.
