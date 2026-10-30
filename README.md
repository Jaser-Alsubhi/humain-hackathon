# Mend: agentic recovery of a failing system

Mend is an AI agent that investigates a failing web stack, takes the smallest safe action that fixes it, and checks that the system really recovered. It also catches failures that a healthy-looking site hides, such as orders that are accepted and never stored. When none of its tools can fix the fault, it stops and writes an incident ticket instead of looping.

Built solo for the Misk x HUMAIN Future AI Builders Hackathon, Challenge 1.

## Results at a glance

Every run saved in the results file is counted, failures included. The file keeps the latest runs per scenario, so earlier failed runs (for example, two failed hang runs) are listed in the evidence log. Details per scenario are in [docs/RESULTS.md](docs/RESULTS.md), and the evidence behind each number is in [docs/EVIDENCE.md](docs/EVIDENCE.md).

<!-- RESULTS:START -->
| Fault family | Naive restart | Fixed runbook | Mend agent | Agent wrong actions | Agent tokens per run |
|---|---|---|---|---|---|
| Outages | 0/18 | 15/18 | **22/22** | 0 | 8,926 |
| Silent data faults | 0/9 | 0/9 | **9/9** | 0 | 17,177 |
| Unfixable fault (the agent must escalate) | 0/3 | 0/3 | **2/2** | 0 | 13,256 |
| Hangs | 1/2 | 0/2 | **2/3** | 2 | 34,131 |
<!-- RESULTS:END -->

- Naive restart: restart the backend and hope. Fixed runbook: scripted rules (start stopped containers, unpause paused ones, roll back a changed config).
- Agent model: gpt-oss-120b on Cerebras (an earlier phase used the same model on Groq). A smaller model, gpt-oss-20b, was tried on some faults and is counted separately in the results file.
- Held-out result on the frozen final code: pending, and it is run once.

## Quick start

```
cp .env.example .env              # set OPENAI_API_KEY, OPENAI_BASE_URL and LLM_MODEL (any OpenAI-compatible endpoint)
docker compose up -d --build      # backend :8000, frontend :5173, MySQL :3307
python -m recovery.run_agent db_down          # inject a fault, let the agent fix it
```

More commands:

```
pytest                                                          # unit tests and CI checks
python -m recovery.silent --oracle                              # zero-token check of the data-fault scenarios
python -m recovery.evaluate --scenarios sync_corruption --methods naive,runbook,agent --repeats 3
python scripts/make_results.py                                  # rebuild the tables from results/recovery_eval.json
```

## How it works

```
alert -> investigate (logs, health, process state, data checks) -> choose the least disruptive action
      -> guard (allowlist, step and action limits, settle rule, redaction) -> act -> verify
      -> recovered: stop      not fixable: escalate with findings, what was tried and a recommendation
```

- **Tools.** Observation tools (health, service status, frozen processes, logs, metrics, database connections, config changes, data invariants, write probe, sync jobs) and action tools (restart, start, unpause, rollback config, recreate, restore table, replay from journal, restore sync job, resync ledger), plus `escalate`.
- **Guard.** Only registered tools run. At most 12 steps and 4 actions, the last 2 steps are reserved for acting and verifying, and secrets are redacted before a model or a log sees them. A settle rule holds an action on a service whose dependency was just changed, because the site may simply be catching up.
- **Verification.** A fault only counts as fixed when `/ready` is 200 and, for data faults, the invariant check is clean and every table really stores writes. A healthy `/health` is not enough.
- **Untrusted input.** Everything inside tool output is treated as data. A planted instruction in a config note is ignored (3 of 3 runs).

## The faults

| Family | Faults | What makes them hard |
|---|---|---|
| Outages | database down, database paused, bad config, both at once, planted instruction in a config note, exhausted connections | A blanket restart is wrong. The order of fixes matters |
| Silent data faults | payments dropped, orders dropped, sync job that corrupts a ledger | The site reports ready the whole time. Only the data shows it |
| Unfixable | database credential rotated outside the agent's control | The right move is to stop and hand over |
| Hangs | frozen backend, frozen backend with exhausted connections | The container says "running" while its process is frozen |
| Extra and fuzzed | six faults the runbook has no rule for, and 20 randomly generated fault combinations (8 dev, 12 locked held-out) | Tests generalisation |

## Evaluation rules

- Every scenario has a **zero-token oracle**: it proves the fault really breaks the stack, the baselines fail, a wrong-order fix fails and the right fix passes, before any model is run.
- Baselines come first, and results are saved after every trial.
- A **wrong action** is any executed action outside the scenario's known correct fix set.
- The fuzzer's held-out split is locked in `results/fuzz_manifest.json` and is evaluated once.
- Scenarios were designed knowing their fixes, so dev results show behaviour, not an unbiased test. The held-out run is the unbiased one.

## Layout

- `recovery/`: agent loop, tools (`ops.py`, `silent.py`), scenarios, baselines, evaluation, fuzzer, escalation
- `backend/`, `frontend/`, `docker-compose.yml`, `ops/`: the stack the agent repairs, including the orders pipeline and intake journal
- `tests/`: unit tests, run in CI (`.github/workflows/ci.yml`)
- `results/`: saved evaluation rows, escalation tickets and the locked fuzz manifest
- `site/`, `.github/workflows/deploy-site.yml`: the project website and its deploy pipeline
- `docs/`: evidence log, results tables and report

## What was built when

Built before the event opened (before 14:00 on Friday 30 October): the base stack (FastAPI, React, MySQL, Docker Compose), the evaluation scaffold in `eval/` and `src/`, the agent loop with its guard, the two baselines, the outage faults, the fault fuzzer with its locked split, and the six extra faults.

Built during the event: the orders pipeline and intake journal, the silent data faults and invariant checks, the escalation tool and unfixable scenario, the sync-corruption scenario, the frozen-process detection, the retry hardening, the project website and its automatic deploy to Azure.

## Limitations

- The agent's strength comes partly from purpose-built tools for each fault family. A fault outside those families needs new tools or ends in escalation.
- Most scenarios were designed knowing their fix, so dev results are easier than unseen faults.
- Repeats are small (3 to 5), so results show stability, not statistical rates. The held-out set is the broader test.
- The ledger in the sync scenario lives in the same database, so it is a simulated replica.
- The live agent is not exposed publicly. The website replays recorded runs from the test results.
- Latency of 80 to 200 seconds on some runs is mostly provider rate limiting (5 requests a minute), not compute.
- Not built: a queue that loses messages under load.

## Links

- Website: https://mend-ai.swedencentral.cloudapp.azure.com
- Demo video, slides: added at submission
