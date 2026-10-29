# Runbook

## First hour after the challenge is revealed
1. Read the task twice. Write the metric and the input and output format in one line each.
2. Swap make_data, the models and the metric into eval/run_all.py. Keep seeds, the held-out lock and the report.
3. Majority and simple baselines first, then log them. Commit.
4. Only then build the real approach, one change at a time, logging each run.

## Commands
- Everything: `python -m eval.run_all`
- Tests: `pytest`
- Stack: `docker compose up -d`, health at http://localhost:8000/health
- Offline embeddings: set EMBED_PROVIDER=local (the model is cached)

## Rules
- Run final_evaluation once, at the end. It raises an error if reused.
- Never commit .env. Work in the private repo only.
- Re-run run_all and commit results/report.md before presenting.
