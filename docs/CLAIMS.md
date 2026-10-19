# Claims and evidence

Every headline claim made in the README, the datasheet or the write-up gets a row here.

**Status vocabulary** (credit: Kanishk234's claims table):
- proven unbounded
- proven bounded (depth N)
- tested (N cases)
- simulated only
- estimated
- not yet verified

| ID | Claim | Evidence (command / file / CI run) | Status | Blind spot |
|---|---|---|---|---|
| C1 | One SPEX engine is about 0.158 mm² of standard cells before layout | `experiments/area_probe/` with `yowasp-yosys -s synth_v2.ys` | estimated (sketch, not the design) | no place and route; tables in flops |
