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
