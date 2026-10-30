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
