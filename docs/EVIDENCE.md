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
