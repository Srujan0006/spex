# Bug ledger

Every bug found, including in tests, tools and specs, with the method that found it (credit: Loom, TeslaCoilerOW).

| # | Date | Where | Defect | Found by (method) | Fix (commit) | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | proposal rev 1, edge encoding | A single guard enum could not test the clock window AND the bit count | design review | rev 2 (S4) | fixed in spec |
| 2 | 2026-10-19 | proposal rev 1, coverage record | 40-bit record does not fit a 32-bit macro word | design review | rev 2 (S10) | fixed in spec |
| 3 | 2026-10-19 | area probe v2 | lo and hi written from the same word, so Yosys merged them and under-reported area | self-check of the measurement | probe fixed, re-measured | fixed |
| 4 | 2026-10-19 | area probe v2 | first change of any pin set the timestamp (SDA could stamp an SCL edge) | design review round 2 | rev 2.1 (S8) | fixed in spec and probe |
| 5 | 2026-10-19 | SEMANTICS v0 §4 | Latency bound "L or L+E" ignores carry-over (S7): a change carried into the next location reacts in L+2 = 5 cycles | writing worked example 13.1 a3 (SEMANTICS v1) | S35 (proposed) | fixed in spec, awaiting approval |
| 6 | 2026-10-19 | SEMANTICS v0 §2/§5 | Clock guards on the current x judge a late-seen event up to 2 cycles late; a legal event at `hi` seen in an entry cycle is rejected | writing worked example 13.3 c6 | S20, S21 (proposed) | fixed in spec, awaiting approval |
| 7 | 2026-10-19 | proposal §3.2 | "A genuine glitch is caught one cycle later": it is caught 2 cycles after the firing (entry cycle in between), timestamp exact | writing worked example 13.2 L3 | SEMANTICS 13.2 | fixed in spec |
| 8 | 2026-10-19 | tests/model/test_rules.py (R9 coverage test) | Hits had only increasing offsets, so a model that never updates the minimum passed | mutation run (`scripts/mutate_model.py`, mutant "coverage min never updated" survived) | added a third, smaller hit | fixed |
| 9 | 2026-10-20 | SEMANTICS v1 R4.1 / host usage | Sync flops reset to 0, so an idle-high pin shows a change in cycle 2; a Check engine started in cycle 0 raises a false UNEXPECTED | toy-UART Drive→Check duality test (tests/model/test_compiler.py) | R12.7 (start in cycle ≥ 3); host library must enforce | documented, open for the host library |
| 10 | 2026-10-20 | tests/model/test_compiler.py | Two "accept" tests were in fact nondeterministic specs (an untimed edge on another pin overlaps); the compiler rightly rejected them | the compiler's own R7.11 check | tests rewritten with genuinely disjoint guards | fixed |
