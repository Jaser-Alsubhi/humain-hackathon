# HUMAIN Hackathon

Reproducible AI evaluation stack: FastAPI backend, React frontend, MySQL, Docker Compose, seeded evaluation harness.

## Run everything
    python -m eval.run_all        # experiments, ablations, robustness, writes results/report.md
    pytest                        # tests, including the regression check
    docker compose up --build     # backend :8000, frontend :5173, MySQL :3307

## Layout
- src/ : config (seeds), LLM wrapper (retries, cache, JSON validation)
- eval/ : harness, metrics (macro F1, ECE), temperature scaling, robustness perturbations, locked held-out split
- tests/ : API, LLM wrapper, regression, held-out, calibration, robustness
- results/ : runs.jsonl (every run), report.md (latest report)

## Evaluation rules
- All experiments use the dev split. The held-out set is used once, via eval.holdout.final_evaluation.
- Every comparison runs on 3 seeds and reports mean and std.
- CI fails if the score drops below eval/baseline.json minus a tolerance.

## Docs
- docs/REPORT_TEMPLATE.md : report structure by judging criterion
- docs/PITCH.md : presentation outline and rehearsal questions
- docs/RUNBOOK.md : first-hour plan and command cheat sheet
