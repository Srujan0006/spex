"""Per-location window and constant use of every spec in every role (owner request 2026-10-22).

    python3 -B scripts/location_fit.py           # markdown on stdout

Question: does every location use at most 2 distinct windows and at most 2 distinct constants? If so, a "location
record" (the location's windows and constants stored with it, selected by 1-bit fields in the edge word) could replace
the shared window and constant tables.
Counted per location, from the compiled image:
  - windows: the window of every valid edge with a clock guard (GE, WIN, POLICY), plus the location's invariant window;
  - constants: the constant of every valid edge whose data guard reads the constant table (BITCNT_EQ, BITCNT_LT,
    SR_MATCH, SR_NOMATCH, TOKEN; EVENT uses k as an event number and TXF_NE uses nothing).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.table_usage import SPECS  # noqa: E402
from spex.compiler import CompileError, compile_spec  # noqa: E402
from spex.refsim.tables import (CK_NONE, DG_BITCNT_EQ, DG_BITCNT_LT, DG_SR_MATCH, DG_SR_NOMATCH,  # noqa: E402
                                DG_TOKEN, NUM_LOCS, NUM_SLOTS, unpack_edge, unpack_loc)

READS_CONST = {DG_BITCNT_EQ, DG_BITCNT_LT, DG_SR_MATCH, DG_SR_NOMATCH, DG_TOKEN}
LIMIT = 2


def per_location(img):
    """{location: (set of windows, set of constants)} for every defined location."""
    out = {}
    for loc in range(NUM_LOCS):
        if img.locs[loc] is None:
            continue
        lw = unpack_loc(img.locs[loc])
        wins = {lw.inv_win} if lw.inv_en else set()
        consts = set()
        for slot in range(NUM_SLOTS):
            w = img.edges[loc * NUM_SLOTS + slot]
            if w is None:
                continue
            e = unpack_edge(w)
            if not e.valid:
                continue
            if e.ck != CK_NONE:
                wins.add(e.window)
            if e.dk in READS_CONST:
                consts.add(e.k)
        out[loc] = (wins, consts)
    return out


def rows():
    for name, make, sides in SPECS:
        for role, side in [("check", None)] + [("drive", s) for s in sides]:
            label = role + (f" ({side})" if side else "")
            try:
                r = compile_spec(make(), role, side=side)
            except CompileError:
                yield name, label, None
                continue
            names = {i: n for n, i in r.loc_index.items()}
            pl = per_location(r.image)
            mw = max(len(w) for w, _ in pl.values())
            mk = max(len(k) for _, k in pl.values())
            over = [f"{names.get(l, l)} ({len(w)} w, {len(k)} k)" for l, (w, k) in sorted(pl.items())
                    if len(w) > LIMIT or len(k) > LIMIT]
            yield name, label, (len(pl), mw, mk, over)


def main():
    print(f"| spec | role | locations | max windows per location | max constants per location | over {LIMIT} |")
    print("|---|---|---|---|---|---|")
    fits = True
    for name, label, res in rows():
        if res is None:
            print(f"| {name} | {label} | compile error (see table_usage.py) | | | |")
            continue
        n, mw, mk, over = res
        fits &= not over
        print(f"| {name} | {label} | {n} | {mw} | {mk} | {', '.join(over) if over else '—'} |")
    print(f"\nEvery compiled spec fits <= {LIMIT} windows and <= {LIMIT} constants per location: {'yes' if fits else 'no'}")
    return 0 if fits else 1


if __name__ == "__main__":
    sys.exit(main())
