# Evidence log

## #1 Payments that silently drop orders

Setup: two dev scenarios, designed knowing the fix, so not an unbiased test. A table (payments, or orders) is switched to MySQL's BLACKHOLE engine, which accepts every write and stores nothing. The site stays up and /ready stays 200 throughout. The journal holds 35 intake entries (20 before the fault, 15 after).

Damage before recovery
- silent_drop_payments: 35 of 35 payments missing. 35 orders marked paid with no money on the books, 52,695 cents (526.95) unbooked.
- silent_drop_orders: 35 of 35 orders missing, while the payments exist.

Results (3 repeats per scenario)
- Naive restart: 0/6. It restarts the backend and leaves every record missing.
- Scripted runbook: 0/6. It finds nothing to do, because no container is down and the config is unchanged.
- Agent (gpt-oss-120b): 6/6, 0 wrong actions, 2 actions each (restore_table, then reconcile_from_journal). Mean 15,080 tokens and 17 s on payments, 15,961 tokens and 36 s on orders.

After recovery: 0 records missing, 0 cents unbooked, and the write probe stores rows on both tables.

How the agent got there: check_invariants showed the missing records, probe_writes showed which table dropped writes, table_info showed the BLACKHOLE engine, then it restored the table before replaying the journal. Replaying first loses the rows again; the zero-token oracle confirms this.

Limits
- 3 repeats, not 5, to protect the daily token allowance.
- The agent runs at temperature 0, so repeats show stability, not independent trials.
- Dev scenarios, not held-out. The held-out run is in section #7.
- Recovery relies on the intake journal. If the journal were lost, the data could not be restored.

## #5 Escalation: unfixable credential rotation

Fault: root@% password rotated inside the database container, backend crash-loops with "Access denied". No tool can fix it, so the correct action set is empty and success means handing off with a ticket that names the cause.

- naive 0/3 (restarts a service every run, 1 wrong action each). runbook 0/3 (no action, no handoff).
- agent (gpt-oss-120b) 2/2 saved runs: 0 actions, 0 wrong, ticket written. A separate smoke run (not saved in the results file) also escalated with 0 actions.
- One earlier run crashed on an LLM timeout (a bug in my retry code, since fixed) after calling recreate_service before reaching a decision. So the agent can act once before it escalates. This is not ruled out.
- The ticket diagnosis is only partly right. It cites "Access denied" but blames root being restricted to localhost, and recommends granting remote access. The real cause is a rotated password, so that recommendation would not fix it.
- The handled-correctly check is keyword-based, so it is weak evidence of a correct diagnosis.
- Limits: 2 saved repeats, not 5. A development scenario designed knowing the fix. The prompt change was not regression-tested on the fixable scenarios for premature escalation.

## #4 Hang: a process that is running but frozen

**Scenarios.** `hung_backend` freezes the backend process with SIGSTOP. Docker still reports the container as running, but `/health` and `/ready` time out. The fix is to restart the backend. `hung_exhaust` combines connection exhaustion with a frozen backend. The fix is to restart the database, then the backend.

**Baselines.** `hung_backend`: naive 1/1 (a blanket restart fixes it in 6s), runbook 0/1. `hung_exhaust`: naive 0/3, runbook 0/3. On `hung_backend` the naive baseline is as good as the agent and faster, and that is stated plainly here. `hung_exhaust` is the fault that separates them.

**Agent (gpt-oss-120b on Cerebras), before the frozen-process fix, all runs, none dropped:**

| Run | Scenario | Result | Actions (wrong) | Time | Tokens |
|---|---|---|---|---|---|
| 1 | hung_backend | failed | 0 (0) | 213s | 38,697 |
| 2 | hung_backend | failed | 1 (1) | 204s | 32,539 |
| 3 | hung_backend | recovered | 3 (2) | 80s | 31,353 |
| 4 | hung_exhaust | recovered | 2 (0) | 183s | 32,493 |

One earlier `hung_exhaust` attempt ended in a rate-limit error and is counted as an infrastructure error, not a failure. One earlier `hung_backend` run was invalid because Docker Desktop was closed, and it was removed. A gpt-oss-20b run of `hung_exhaust` failed (0/1, 237s, 38,548 tokens). That run is from before the fix and was not repeated.

**What went wrong, from the audit logs.**
- Run 1: the agent spent its investigation steps on logs and metrics, then made four blocked investigation calls in a row and never acted. The guard's block message did not say which tools were still allowed.
- Run 2: with the guard fixed, it acted, but restarted the healthy frontend and then escalated. Nothing in its tool output showed that the backend process was frozen.
- Run 3: with process state added to `service_status`, the first tool result showed the backend as `Tsl` (T = stopped). The agent still restarted and recreated the healthy frontend first, then restarted the backend and recovered. It had the right evidence and ignored it.

**Changes made after seeing these failures.** (1) When investigation is closed, the guard names the tools still allowed. (2) `service_status` shows each container's process state. (3) After run 3 showed that a raw state table is ignored, `service_status` now starts with an explicit warning when a container reports running but holds a frozen process (pid, command, state), and a new `find_frozen_processes` tool says to restart only the service that holds it. (4) SYSTEM rule 10 states, in general terms, that a container can report running while its main process is frozen or blocked, and that only the service holding it should be restarted. Rule 10 is a general rule about a failure class and names no scenario, but it is a prompt change aimed at this failure. Its contribution on its own was not measured, because I did not run an ablation without it. Changes 3 and 4 were made after seeing the dev failures, so these dev numbers are not an unbiased test.

**Agent after the fix, all runs:**

| Scenario | Agent | Wrong actions | Time per run | Tokens per run | Naive | Runbook |
|---|---|---|---|---|---|---|
| hung_backend | 5/5 | 0 | 9 to 11s | about 6,800 | 1/1 | 0/1 |
| hung_exhaust | 3/3 | 0 | 33 to 47s | 16,700 to 21,600 | 0/3 | 0/3 |

On `hung_backend` every run took one action, the restart of the backend, with near-identical token counts (6,814 to 6,830). The agent now follows one fixed path: read the warning, restart the service that holds the frozen process, verify. On `hung_exhaust` every run took two actions with no wrong action.

**Limits.** Three to five runs per scenario show stability, not rates. `hung_backend` does not show an advantage over the naive restart. The improvement comes partly from a tool that names the frozen process, so the result depends on that tool. The smaller gpt-oss-20b model failed on `hung_exhaust` before the fix and has not been re-tested. The held-out set is the unbiased test.

## #3 Sync corruption: a sync job that turns good records bad over time

**Scenario.** `sync_corruption` adds a `ledger` table and a sync job (a database trigger on `orders`) that copies every new order into it. The first 20 orders sync correctly, so the ledger starts out right. Then a second trigger is installed that, on every new order, adds one cent to older ledger rows. Rows that were correct turn wrong, and each new order makes more of them wrong: after 15 more orders, all 35 ledger rows differ from their orders. Orders, payments and the intake journal stay correct, the site stays ready, and every health check passes.

**How it is detected.** `check_invariants` compares every third order with its ledger row (a sample), then all orders (the full check). `probe_writes` places a 1 cent test order and reads back what the ledger stored.

**Correct fix.** Reinstall the standard sync job (`restore_sync_job`), which removes the drifting trigger, and make every ledger row match its order (`resync_ledger`). Doing only one of them is not enough: resyncing alone leaves the job drifting new rows, and restoring alone leaves the old wrong rows.

**Zero-token oracle: PASS.** Site stays ready; 35 of 35 ledger rows differ; the sampled check and the write probe catch it; the naive restart and the runbook do not fix it; resync alone does not hold; restore alone leaves the old drift; restore then resync fixes it.

| Method | Recovered | Notes |
|---|---|---|
| Naive restart | 0/3 | 1 wrong action in each run |
| Fixed runbook | 0/3 | takes no action |
| Mend agent (gpt-oss-120b) | 3/3 | 2 actions each, 0 wrong; 21,632, 18,627 and 21,510 tokens; 15 s, 17 s and 127 s (the slow run is most likely provider rate limiting, not checked) |

**Limits.** This is a development scenario designed knowing the fix, not an unbiased test. The ledger lives in the same database, so it is a simulated replica, not a separate system. The drift starts at a set point rather than appearing gradually in time. The alert used in the evaluation names the ledger, which narrows the search. A single run through the monitor, whose alert names no cause, recovered it as well (section #6), although that alert still names the failing check (`ledger_mismatch`). Either repair order ends clean, so the check is on the final state. Three runs show stability, not rates. Two earlier versions of this scenario passed 3 of 3 too (a trigger adding 1 cent to payments, and a trigger whose error grew with the order id). Both were replaced so that the bug acts on rows that were already correct, which matches the brief, and their numbers are not used here.

## #2 A queue that loses messages under load

**Scenario.** The backend has a message queue: `POST /queue/messages` writes each message to an append-only journal first, then offers it to a bounded queue (a table), and a worker thread drains the queue. What happens when the queue is full is configuration. A deploy changes three settings: the overflow policy goes from reject (answer 429) to drop (answer 202 and discard), the depth from 1000 to 10, and the worker slows to 2 seconds a message. Then a spike of 40 messages arrives, after 20 messages sent under good settings. Every message is accepted and journaled, `/ready` stays 200, orders and payments are untouched, and in the oracle run 26 of the 60 messages were lost (the exact number varies with timing).

**How it is detected.** `check_invariants` compares the queue journal with what is still queued and what the worker processed (`queue_lost`). `queue_status` shows the counts, the queue settings in the active configuration and a verdict ("26 messages are still lost"). `config_changes` shows the settings that changed.

**Correct fix.** Roll back the configuration, then replay the lost messages from the journal (`replay_queue`). Either alone does not fix it. Replaying while the bad settings are active loses the messages again.

**Zero-token oracle: PASS.** The site stays ready; all 60 messages are journaled and 26 are lost; the naive restart and the runbook do not fix it; rollback alone leaves them lost; replay before rollback loses them again; rollback then replay fixes it. The older scenarios still pass the oracle after the queue was added.

| Method | Recovered | Notes |
|---|---|---|
| Naive restart | 0/3 | 1 wrong action in each run |
| Fixed runbook | 0/3 | rolls back the config, which does not bring the messages back |
| Mend agent, first version (gpt-oss-120b) | 2/3 | 0 wrong actions |
| Mend agent, after one change (gpt-oss-120b) | 5/5 | 2 actions each (rollback, then replay), 0 wrong; 65 to 127 s; 17,355 to 29,811 tokens |

**What went wrong in the first version, all three runs.** Run 1 replayed the messages first, while the bad settings were still active, so they were dropped again. It then rolled back the config and stopped without replaying a second time. Run 2 made the same first mistake, noticed, and replayed again after the rollback. Run 3 rolled back first and then replayed. So the agent had the evidence (the settings were visible in `config_changes` and `queue_status`) and sometimes acted in the wrong order.

**Change made after seeing this.** Three general changes, none naming this scenario: SYSTEM rule 8 now says to replay only after whatever lost the data is fixed, because replaying into a destination that still has the fault loses the data again; the `replay_queue` description says the messages are lost again if the current settings are what lost them; and `queue_status` ends with a plain verdict. After the change all five runs rolled back first and replayed second. The payments scenario, which also uses replay, passed 3 of 3 afterwards. Tokens per payments run rose from about 15,000 to about 25,000. I did not check why, and my guess is the two extra tool descriptions sent on every step.

**Limits.**
- A development scenario, designed knowing the fix, and the prompt change was made after seeing a failure. Not an unbiased test.
- The queue is a table in the same database and the worker is a thread in the backend, so it is a small simulation of a message queue, not a broker such as RabbitMQ or Kafka.
- The agent runs at temperature 0, so five runs show stability, not a rate.
- Detection relies on the journal. Messages that never reach the journal cannot be found.
- The effect of the rule 8 change was measured only on the queue and payments scenarios.

## #6 Unattended operation: the monitor and the live button

**What it is.** `recovery.watch` polls `/ready` and the data checks every 5 seconds. After two failed checks in a row it starts the agent. The alert it passes is built only from measurements ("the readiness check is failing (HTTP 503)", "data checks fail (ledger_mismatch=35)"), so it names the failing check but no cause. Escalation ends the incident and the monitor stops after two attempts. `recovery.break_it` injects a fault without telling the monitor what it was. A small server on the VM runs the same loop for the public Break it button.

**What was run.** On the laptop, the monitor recovered `db_down` and `sync_corruption` unattended. On the public project site, each of five faults was run once through the button on the real VM, and all five recovered and were verified:

| Fault | Time | Steps | Actions | Tokens |
|---|---|---|---|---|
| Database stops | 17 s | 3 | 1 | 6,722 |
| Bad configuration is deployed | 74 s | 5 | 1 | 12,579 |
| Backend freezes | 36 s | 3 | 1 | 6,887 |
| Sync job corrupts data | 78 s | 9 | 2 | 21,647 |
| Payments silently lost | 137 s | 10 | 2 | 23,305 |

**Unfixable fault through the monitor (laptop, one run, not clean).** The monitor detected the rotated database password in about 16 seconds. Attempt 1 investigated, then ran `recreate_service` and `restart_service` on the backend, neither of which could help, and ended without a ticket (198 s, 51,240 tokens). Attempt 2 took 0 actions and escalated correctly (105 s, 26,344 tokens): ticket `ESC-20261031T005401-672` names the MySQL auth error 1045 and recommends creating a database user and updating the backend credentials. The monitor then stayed paused and did not call the agent again. In the earlier lab runs of this fault the agent took 0 actions in 2 of 2 runs, so this single monitored run is worse than those. Two harmless but pointless restarts happened before the ticket. The code was not changed after this run.

**Limits.**
- One live run per fault, so this shows the chain works end to end, not a rate.
- The queue fault was added to the live list after these runs.
- The monitor has not been run on the frozen backend from the laptop, and the live list leaves out the unfixable fault. The one monitored unfixable run needed both attempts to reach a ticket (see above).
- Detection of silent faults depends on the journal and the data checks, which only cover orders, payments, the ledger and the queue. A silent fault elsewhere would not be seen.
- The live button is limited to 3 runs per visitor per hour and 25 per day, one at a time, with a kill switch. The live agent uses a shared provider key and a small shared VM.



## #7 Held-out run: 12 unseen generated faults

**What was run.** `python -m recovery.evaluate --set heldout --methods agent --repeats 1`, once, on the frozen code (commit `f32c07b`). The 12 faults come from a locked fuzzer manifest (`results/fuzz_manifest.json`, seed 20261030). The baselines were run on the same 12 faults earlier. No fault was rerun and no code changed after the run.

| Fault | Combination | Naive | Runbook | Agent (wrong actions) |
|---|---|---|---|---|
| fz-b56b2d | connections exhausted + wrong password | no | no | no (0), 203 s |
| fz-e60897 | backend paused | yes | yes | yes (1), 8 s |
| fz-ca6865 | connections exhausted + backend stopped | no | no | yes (0), 123 s |
| fz-10ec16 | password rotated | no | yes | yes (0), 10 s |
| fz-dc3a0d | database paused + password rotated + backend paused | no | yes | yes (2), 202 s |
| fz-fef3cc | host name changed + backend stopped | no | yes | yes (0), 29 s |
| fz-5521c4 | database name changed + backend stopped | no | yes | yes (0), 24 s |
| fz-91e410 | database paused + backend paused | no | yes | yes (0), 20 s |
| fz-bb3ac9 | database stopped + wrong password | no | yes | yes (0), 33 s |
| fz-0b3410 | database stopped + database name changed + backend paused | no | yes | yes (1), 50 s |
| fz-e911d2 | database stopped + database name changed | no | yes | yes (0), 35 s |
| fz-de4c32 | database paused + password changed + backend paused | no | yes | no (2), 331 s |

**Totals.** Agent 10/12 and 6 wrong actions (in 4 runs). Runbook 10/12 and 0. Naive 1/12 and 12. The agent used 24,189 tokens per run on average (7,384 to 42,399) and took 89 s on average (most runs took about 35 s or less). The agent itself verified recovery in 8 of 12 runs.

**What this shows.** The agent does not beat the scripted runbook on generic infrastructure faults: both recover 10 of 12. Two of the agent's four weaker runs were misses (`fz-b56b2d`, `fz-de4c32`) and two recovered with extra or unneeded actions (`fz-dc3a0d`, `fz-0b3410`). In `fz-de4c32` the agent unpaused both containers, then restarted and recreated the backend without ever calling the config-changes tool, and the runbook fixed the same fault in 6 s. Its value is on the five problems in this document, where the runbook scores 0.

**Limits and a disclosure.**
- 12 faults with one run each is a small sample, and temperature 0 means a rerun would likely repeat these results.
- Docker Desktop reported a full disk on the laptop at about the time the last faults ran, because of a large unrelated download. The results table shows 0 infrastructure errors, so every run is counted as it is. The saved step lists hold only tool names, not tool output, so they cannot show whether Docker was failing during a run. I cannot rule out that the disk problem slowed `fz-de4c32` (331 s, the longest run).
- The fault combinations include families the agent saw in dev (host name, password, database name, pauses, exhaustion), but not these exact combinations.
