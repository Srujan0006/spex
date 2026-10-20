# Sealed held-out protocols (credit: MarcosAsh)

**Purpose.** Show the main judging criterion: the chip runs protocols it was not designed for.

**Procedure:**
1. Before the RTL freeze, choose 6-8 protocols not implemented anywhere in this repo, for example WS2812, 1-Wire, PS/2, DShot, NEC IR or CAN.
2. Write them one per line in a private file, with a random salt line.
3. Commit only `sha256(file)` below. Keep the file itself outside the repo.
4. At Gate B (2026-12-14), publish the file. Anyone can check the hash.
5. Then write each protocol as a spec, using only the public standard and the DSL. Model-check it, run it in Drive and Check, and record the result in CLAIMS.md.

| Committed on | sha256 | Revealed on |
|---|---|---|
| (pending) | | |

## Plan: a held-out protocol written from the spec guide only (S48, owner 2026-10-20)

**Aim.** Measure how usable the spec language is: a fresh session, with no access to this conversation or to the
existing specs' design history, writes one held-out protocol from `docs/SPEC_GUIDE.md` and the public standard only.

**Procedure.**
1. Pick the protocol from the sealed list once it is revealed (Gate B), or, before that, one not in the repo and not
   on the sealed list (proposal: DShot600 or 1-Wire reset/presence).
2. Start a new session with only: `docs/SPEC_GUIDE.md`, `docs/SEMANTICS.md`, `spex/` (the DSL and compiler), the
   standard's text, and the instruction "write `spec/<name>.py` and its oracle; do not read `spec/uart_8n1.py`,
   `spec/spi.py` or `spec/i2c.py`". The guide's references to them are left as they are, unopened.
3. Record, in this file: wall-clock time, number of compile errors and which guide section resolved each, questions
   the guide did not answer, and whether the result passes Drive/Check against its oracle with 5 planted faults.
4. Every question the guide did not answer becomes a guide fix.

| Date | Protocol | Session | Time | Compile errors | Guide gaps found | Result |
|---|---|---|---|---|---|---|
| (planned) | | | | | | |
