# Bug ledger

Every bug found, including in tests, tools and specs, with the method that found it (credit: Loom, TeslaCoilerOW).

| # | Date | Where | Defect | Found by (method) | Fix (commit) | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-10-19 | proposal rev 1, edge encoding | A single guard enum could not test the clock window AND the bit count | design review | rev 2 (S4) | fixed in spec |
| 2 | 2026-10-19 | proposal rev 1, coverage record | 40-bit record does not fit a 32-bit macro word | design review | rev 2 (S10) | fixed in spec |
| 3 | 2026-10-19 | area probe v2 | lo and hi written from the same word, so Yosys merged them and under-reported area | self-check of the measurement | probe fixed, re-measured | fixed |
| 4 | 2026-10-19 | area probe v2 | first change of any pin set the timestamp (SDA could stamp an SCL edge) | design review round 2 | rev 2.1 (S8) | fixed in spec and probe |
