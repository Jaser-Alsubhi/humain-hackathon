# Mend: agentic recovery of a failing system

Mend is an AI agent that investigates a failing web stack, takes the smallest safe action that fixes it, and checks that the system really recovered. It also catches failures that a healthy-looking site hides, such as orders that are accepted and never stored, or messages dropped during a traffic spike. When none of its tools can fix the fault, it stops and writes an incident ticket instead of looping.

It runs unattended. A monitor checks the site and the data every 5 seconds and starts the agent by itself, so something that breaks at 3 a.m. is found, fixed and verified with nobody watching. The project website has a Break it button that does exactly this on a real server: [mend-ai.swedencentral.cloudapp.azure.com](https://mend-ai.swedencentral.cloudapp.azure.com).

Built solo for the Misk x HUMAIN Future AI Builders Hackathon, Challenge 1.

## Results at a glance

Every run saved in the results file is counted, failures included. The file keeps the latest runs per scenario, so earlier failed runs (for example, two failed hang runs and one failed queue run) are listed in the evidence log. Details per scenario are in [docs/RESULTS.md](docs/RESULTS.md), and the evidence behind each number is in [docs/EVIDENCE.md](docs/EVIDENCE.md).

<!-- RESULTS:START -->
| Fault family | Naive restart | Fixed runbook | Mend agent | Agent wrong actions | Agent tokens per run |
|---|---|---|---|---|---|
| Outages | 0/18 | 15/18 | **22/22** | 0 | 8,926 |
| Silent data faults | 0/12 | 0/12 | **14/14** | 0 | 21,548 |
| Unfixable fault (the agent must escalate) | 0/3 | 0/3 | **2/2** | 0 | 13,256 |
| Hangs | 1/4 | 0/4 | **8/9** | 0 | 14,204 |
<!-- RESULTS:END -->

- Table notes: agent columns pool every saved agent run, including a few early runs on the smaller gpt-oss-20b. The Hangs cell 8/9 includes one failed `hung_exhaust` run on gpt-oss-20b. On gpt-oss-120b, the model behind every other claim, hangs are 8/8. Those 8 are development results, not a blind test.
- Naive restart: restart the backend and hope. Fixed runbook: scripted rules (start stopped containers, unpause paused ones, roll back a changed config).
- Agent model: gpt-oss-120b on Cerebras (an earlier phase used the same model on Groq). A smaller model, gpt-oss-20b, was tried on some faults and is counted separately in the results file.
- Rehearse mode (optional, off by default) was compared with the plain agent on 12 fresh faults: 9/12 against 10/12 recovered, and runs with a wrong action fell from 8 to 4. It is an exploratory result, not a clear improvement; see `docs/EVIDENCE.md`, section 8.
- Held-out result (12 unseen generated fault combinations, evaluated once on the frozen code `2f73884`): agent 10/12, fixed runbook 10/12, naive restart 1/12. The agent made 6 wrong actions in 4 runs and the runbook made none. Details are in `docs/REPORT.md` and `docs/EVIDENCE.md`.

## Key findings

- **Where it wins.** Faults where the site looks healthy but the data is wrong: agent 14 of 14, naive restart and runbook 0 of 12 each.
- **Where it ties.** On 12 unseen generated faults, run once on frozen code, the agent and a hand-written runbook both recovered 10.
- **Where it is weak.** On those 12 faults the agent made 6 wrong actions (the runbook made none) and used about 24,000 tokens per run. In the monitored run of the unfixable fault the first attempt restarted twice before the second attempt escalated.

## Impact

- **Recovery without waiting for a person.** On the live site, a stopped database is detected by the monitor, fixed and verified in 16 seconds in the recorded run, with nobody pressing anything.
- **Lost data comes back.** Orders and payments that were silently dropped are restored from the intake journal, messages a queue lost are replayed, and corrupted ledger rows are corrected. Records lost and recovered are counted in `docs/EVIDENCE.md`.
- **People are called only when needed.** When no tool can fix the cause, Mend hands over a ticket with what it found, what it tried and what it recommends, instead of retrying.
- **Measured, not claimed.** Two baselines on the same faults, a blind test locked by hash before any agent ran, and the tie with the runbook reported as it is.

## The five problems from the brief

| Problem | Our scenario | Status |
|---|---|---|
| Payments that silently drop orders | Tables that accept writes and store nothing, with `/ready` green | Agent 6/6 in dev |
| A queue that loses messages under load | A queue whose overflow policy was changed to drop, hit by a traffic spike | Agent 5/5 in dev (2/3 before one change) |
| A sync job that slowly corrupts data | A sync job, then a bug that turns correct ledger rows wrong | Agent 3/3 in dev |
| A workflow that hangs forever | A frozen backend that Docker still reports as running | Agent 5/5 and 3/3 in dev |
| A repair agent that never escalates | A fault no tool can fix, so the agent must hand over with a ticket | Agent 2/2 in dev |

All of these are development results. On the held-out run of 12 unseen generated faults the agent ties the runbook (10/12 each). The agent's advantage is on problems no runbook can fix, such as the five above.

## Quick start

```
cp .env.example .env              # set OPENAI_API_KEY, OPENAI_BASE_URL and LLM_MODEL (any OpenAI-compatible endpoint)
docker compose up -d --build      # backend :8000, frontend :5173, MySQL :3307
python -m recovery.run_agent db_down          # inject a fault, let the agent fix it
```

More commands:

```
pytest                                                          # unit tests and CI checks
python -m recovery.silent --oracle                              # zero-token check of the data-fault scenarios, queue included
python -m recovery.watch                                        # the unattended monitor (run break_it in another terminal)
python -m recovery.break_it db_down                             # inject a fault without telling the monitor
python -m recovery.evaluate --scenarios sync_corruption --methods naive,runbook,agent --repeats 3
python scripts/make_results.py                                  # rebuild the tables from results/recovery_eval.json
```

## How it works

```
alert -> investigate (logs, health, process state, data checks) -> choose the least disruptive action
      -> guard (allowlist, step and action limits, settle rule, redaction) -> act -> verify
      -> recovered: stop      not fixable: escalate with findings, what was tried and a recommendation
```

- **Monitor.** `recovery.watch` polls `/ready` and the data checks every 5 seconds, needs two failed checks in a row, then starts the agent with an alert built only from measurements. It stops after two attempts, and escalation ends the incident.
- **Tools.** Observation tools (health, service status, frozen processes, logs, metrics, database connections, config changes, data invariants, write probe, sync jobs, queue status) and action tools (restart, start, unpause, rollback config, recreate, restore table, replay from journal, restore sync job, resync ledger, replay queue), plus `escalate`.
- **Guard.** Only registered tools run. At most 12 steps and 4 actions, the last 2 steps are reserved for acting and verifying, and secrets are redacted before a model or a log sees them. A settle rule holds an action on a service whose dependency was just changed, because the site may simply be catching up.
- **Verification.** A fault only counts as fixed when `/ready` is 200 and, for data faults, the invariant check is clean and every table really stores writes. A healthy `/health` is not enough.
- **Untrusted input.** Everything inside tool output is treated as data. A planted instruction in a config note is ignored (3 of 3 runs).

## The faults

| Family | Faults | What makes them hard |
|---|---|---|
| Outages | database down, database paused, bad config, both at once, planted instruction in a config note, exhausted connections | A blanket restart is wrong. The order of fixes matters |
| Silent data faults | payments dropped, orders dropped, sync job that corrupts a ledger, queue that drops messages in a traffic spike | The site reports ready the whole time. Only the data shows it |
| Unfixable | database credential rotated outside the agent's control | The right move is to stop and hand over |
| Hangs | frozen backend, frozen backend with exhausted connections | The container says "running" while its process is frozen |
| Extra and fuzzed | six faults the runbook has no rule for, and 20 randomly generated fault combinations (8 dev, 12 locked held-out) | Tests generalisation |

## Evaluation rules

- Every scenario has a **zero-token oracle**: it proves the fault really breaks the stack, the baselines fail, a wrong-order fix fails and the right fix passes, before any model is run.
- Baselines come first, and results are saved after every trial.
- A **wrong action** is any executed action outside the scenario's known correct fix set.
- The fuzzer's held-out split is locked in `results/fuzz_manifest.json` and is evaluated once.
- Scenarios were designed knowing their fixes, so dev results show behaviour, not an unbiased test. The held-out run (12 faults, run once) is the unbiased one, and there the agent only ties the runbook.

## Layout

- `recovery/`: agent loop, tools (`ops.py`, `silent.py`), scenarios, baselines, evaluation, fuzzer, escalation
- `backend/`, `frontend/`, `docker-compose.yml`, `ops/`: the stack the agent repairs, including the orders pipeline and intake journal
- `tests/`: unit tests, run in CI (`.github/workflows/ci.yml`)
- `results/`: saved evaluation rows, escalation tickets and the locked fuzz manifest
- `site/`, `.github/workflows/deploy-site.yml`: the project website and its deploy pipeline
- `docs/`: evidence log, results tables and report

## What was built when

Built before the event opened (before 14:00 on Friday 30 October): the base stack (FastAPI, React, MySQL, Docker Compose), an earlier evaluation scaffold (removed in the final cleanup because Mend does not use it), the agent loop with its guard, the two baselines, the outage faults, the fault fuzzer with its locked split, and the six extra faults.

Built during the event: the orders pipeline and intake journal, the silent data faults and invariant checks, the escalation tool and unfixable scenario, the sync-corruption scenario, the frozen-process detection, the retry hardening, the message queue and its overflow fault, the unattended monitor, the public Break it button and the server behind it, the project website and its automatic deploy to Azure.

## Limitations

- The agent's strength comes partly from purpose-built tools for each fault family. A fault outside those families needs new tools or ends in escalation.
- Most scenarios were designed knowing their fix, so dev results are easier than unseen faults.
- Repeats are small (3 to 5), so results show stability, not statistical rates. The held-out set has 12 faults with one run each, so 10/12 is a small sample too.
- The ledger in the sync scenario lives in the same database, so it is a simulated replica.
- The Break it button runs the real agent on a small shared server, so it is limited to 3 runs per visitor per hour and 25 per day, one at a time, with a kill switch. Five of its six faults were run once live, which shows the chain works, not a rate. The recorded replay is always available.
- The queue is a table and a worker thread in the same database, not a message broker.
- In the one monitored run of the unfixable fault, the first agent attempt restarted the backend twice and ended without a ticket. The monitor's second attempt escalated correctly, so the full incident ended with a ticket, but not on the first pass.
- The monitor detects silent faults only through the data checks (orders, payments, the ledger and the queue). A silent fault elsewhere would not be seen.
- Latency of 80 to 200 seconds on some runs is mostly provider rate limiting (5 requests a minute), not compute.

## Links

- Website: https://mend-ai.swedencentral.cloudapp.azure.com
- Slides: uploaded in the project's Presentation section on the hackathon platform
- Demo video: added at submission
