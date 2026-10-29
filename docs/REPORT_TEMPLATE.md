# <Project name>: report

## 1. Problem and approach
Task as understood, the success metric and why it fits, what we built, in under five sentences.

## 2. Results (task performance)
| Model | Macro F1 (or task metric) | Std over 3 seeds |
|---|---|---|
| Baseline | | |
| Final | | |

Held-out result, evaluated once: <number>. Commit: <hash>. Baseline first, always.

## 3. Robustness and adaptation
- Perturbation table (copy from results/report.md): noise, missing values, shift, changed input format.
- Failure handling: what happens when the LLM or network is down (degraded mode, fallback path).
- What still breaks, stated plainly.

## 4. Evaluation and iteration
| # | Change | Hypothesis | Result | Kept? |
|---|---|---|---|---|
- Ablation table: each component removed, with delta against the full system and the seed spread.
- Regression check: CI fails if the score drops below baseline.json minus tolerance.
- One failed experiment and what it taught us.

## 5. Technical judgment
Each major decision as: choice, rejected alternative, evidence for the choice.

## 6. Engineering quality
- Reproduce: `python -m eval.run_all` (writes results/report.md). Stack: `docker compose up --build`.
- Seeds fixed, every run logged to results/runs.jsonl with git hash.
- Tests, CI, security scan, no secrets in the repo, mock mode, offline mode.

## 7. Limitations and next steps
Ranked, honest, specific.
