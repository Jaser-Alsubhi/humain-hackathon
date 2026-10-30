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

## #3 Sync corruption: a sync job that drifts a ledger away from the orders

**Scenario.** `sync_corruption` adds a `ledger` table and a sync job (a database trigger on `orders`) that copies every new order into it. The first 20 orders sync correctly. Then the job is replaced by a buggy version that adds one cent for every five order ids, so each later copy drifts further from the truth (15 of 35 ledger rows end up wrong). Orders, payments and the intake journal stay correct, the site stays ready, and every health check passes.

**How it is detected.** `check_invariants` compares every third order with its ledger row (a sample), then all orders (the full check). `probe_writes` places a 1 cent test order and reads back what the ledger stored.

**Correct fix.** Reinstall the standard sync job (`restore_sync_job`) and make every ledger row match its order (`resync_ledger`). Doing only one of them is not enough: resyncing alone leaves the job drifting new rows, and restoring alone leaves the old wrong rows.

**Zero-token oracle: PASS.** Site stays ready; 15 ledger rows differ; the sampled check and the write probe catch it; the naive restart and the runbook do not fix it; resync alone does not hold; restore alone leaves the old drift; restore then resync fixes it.

| Method | Recovered | Notes |
|---|---|---|
| Naive restart | 0/3 | 1 wrong action in each run |
| Fixed runbook | 0/3 | takes no action |
| Mend agent (gpt-oss-120b) | 3/3 | 2 actions each, 0 wrong; 20,578, 20,516 and 20,375 tokens |

**Limits.** This is a development scenario designed knowing the fix, not an unbiased test. The ledger lives in the same database, so it is a simulated replica, not a separate system. The drift starts at a set point and grows with order id, so it is gradual in size but not in onset. The alert for this scenario names the ledger, which narrows the search. Either repair order ends clean, so the check is on the final state. Three runs at temperature 0 show stability, not breadth. An earlier version of this scenario (a trigger adding 1 cent to payments) also passed 3 of 3; it was replaced so that the scenario matches the brief, and its numbers are not used here.
