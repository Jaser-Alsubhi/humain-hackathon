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
- Dev scenarios, not held-out.
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

**Baselines.** `hung_backend`: naive 1/1 (a blanket restart fixes it in 6s), runbook 0/1. `hung_exhaust`: naive 0/1, runbook 0/1. On `hung_backend` the naive baseline beats the agent on speed and cost, and that is stated plainly here.

**Agent (gpt-oss-120b on Cerebras), all runs, none dropped:**

| Run | Scenario | Result | Actions (wrong) | Time | Tokens |
|---|---|---|---|---|---|
| 1 | hung_backend | failed | 0 (0) | 213s | 38,697 |
| 2 | hung_backend | failed | 1 (1) | 204s | 32,539 |
| 3 | hung_backend | recovered | 3 (2) | 80s | 31,353 |
| 4 | hung_exhaust | recovered | 2 (0) | 183s | 32,493 |

One earlier `hung_exhaust` attempt ended in a rate-limit error and is counted as an infrastructure error, not a failure. One earlier `hung_backend` run was invalid because Docker Desktop was closed, and it was removed. A gpt-oss-20b run of `hung_exhaust` failed (0/1, 237s, 38,548 tokens).

**What went wrong, from the audit logs.**
- Run 1: the agent spent its investigation steps on logs and metrics, then made four blocked investigation calls in a row and never acted. The guard's block message did not say which tools were still allowed.
- Run 2: with the guard fixed, it acted, but restarted the healthy frontend and then escalated. Nothing in its tool output showed that the backend process was frozen.
- Run 3: with process state added to `service_status`, the first tool result showed the backend as `Tsl` (T = stopped). The agent still restarted and recreated the healthy frontend first, then restarted the backend and recovered. It had the right evidence and ignored it.

**Two changes made after seeing these failures.** Both are general, not scenario-specific, and were made before the held-out run: (1) when investigation is closed, the guard names the tools still allowed (commit 91d579c); (2) `service_status` shows each container's process state (commit f918377). I did not add a hang-specific hint to the prompt, because that would tune the agent to this scenario.

**Limits.** Each configuration was run once or three times, so these are anecdotes, not rates. The agent recovered 1 of 3 `hung_backend` runs, and that run carried two wrong actions. The model's tendency to ignore a correct process-state signal is unresolved. Latency of 80 to 213 seconds is mostly API throttling between steps.

## #3 Sync corruption: a quiet bug that changes amounts

**Scenario.** `sync_corruption` installs a database trigger (`sync_job_bug`) that adds 1 cent to every payment written after it starts. The site stays ready and every health check passes. The intake journal still holds the true amounts, so the invariant checker sees `amount_mismatch` rise (15 of 35 payments). The write probe also catches it: it writes 1 cent and reads back a different amount.

**Correct fix, two steps in order.** Stop the sync job (`disable_sync_job`), then overwrite the wrong amounts from the journal (`repair_amounts_from_journal`). Repairing without stopping the job does not hold, because new writes are corrupted again.

**Zero-token oracle: PASS.** Site stays ready; 15 amounts differ; the write probe sees the corruption; the naive restart and the runbook do not fix it; repairing without stopping the cause does not hold; stopping the cause then repairing fixes it.

| Method | Recovered | Notes |
|---|---|---|
| Naive restart | 0/3 | 1 wrong action in each run |
| Fixed runbook | 0/3 | takes no action |
| Mend agent (gpt-oss-120b) | 3/3 | 2 actions each, 0 wrong; 17,207, 19,776 and 17,199 tokens |

**Limits.** This is a development scenario designed knowing the fix, and the corruption is simulated with a trigger, not a real sync job copying data into a ledger. Three runs at temperature 0 show stability, not breadth. The description of `repair_amounts_from_journal` says to stop whatever is still changing new writes first, which is a hint toward the right order, so this result is easier than a case with no such hint. I did not run the agent without that sentence.
