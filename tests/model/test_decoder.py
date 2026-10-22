"""L1 translation validation: every compiled image, decoded by spex.decoder (written from SEMANTICS §11 only), equals
the compiler's role-expanded source graph, for every spec and role.

Negative controls: corrupted images (here) and planted compiler encoding bugs (tests/model/mutants.py: 'GE window
index loses bit 3', 'constants lose their high byte', 'nominal time in the next slot') must make this file fail."""
import copy
import dataclasses

import pytest

from spec.i2c import i2c
from spec.spi import spi
from spec.uart_8n1 import uart_8n1
from spex.compiler import compile_spec
from spex.decoder import DecodeError, compare, decode

SPECS = [("uart 115200", lambda: uart_8n1(417, 8), ["tx"]),
         ("uart 9600", lambda: uart_8n1(5000, 100), ["tx"])] \
    + [(f"spi mode {m}", (lambda m=m: spi(m)), ["tgt"]) for m in range(4)] \
    + [(f"i2c {s}", (lambda s=s: i2c(s)), ["ctl", "tgt"]) for s in ("standard", "fast")]
CASES = [(name, make, role, side) for name, make, sides in SPECS
         for role, side in [("check", None)] + [("drive", s) for s in sides]]


def _check(r, spec):
    return compare(decode(r.image), r.edges, spec.initial_loc.name,
                   spec.resync_loc.name if spec.resync_loc is not None else None)


@pytest.mark.parametrize("name,make,role,side", CASES, ids=[f"{c[0]}-{c[2]}{'-' + c[3] if c[3] else ''}" for c in CASES])
def test_decoded_image_equals_source(name, make, role, side):
    spec = make()
    r = compile_spec(spec, role, side=side)
    assert _check(r, spec) == []


# ---------------------------------------------------------------- negative controls: corrupted images
def _compiled(which="i2c standard", role="drive", side="ctl"):
    make = dict((n, m) for n, m, _ in SPECS)[which]
    spec = make()
    return spec, compile_spec(spec, role, side=side)


def _first(r, pred):
    for i, w in enumerate(r.image.edges):
        if w and (w >> 1) & 1 and pred(w):
            return i
    raise AssertionError("no such edge")


def test_corrupt_window_msb_detected():
    spec, r = _compiled()                                      # the Standard-mode controller uses windows 8+
    img = copy.deepcopy(r.image)
    i = _first(r, lambda w: (w >> 2) & 1 and (w >> 17) & 3)
    img.edges[i] ^= 1 << 2
    assert compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)


def test_corrupt_target_detected():
    spec, r = _compiled("uart 115200", "check", None)
    img = copy.deepcopy(r.image)
    i = _first(r, lambda w: True)
    img.edges[i] ^= 1 << 25                                    # retarget one edge
    try:
        probs = compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)
    except DecodeError:
        return                                                 # a target with no location word is also a finding
    assert probs


def test_swapped_windows_detected():
    spec, r = _compiled("uart 115200", "drive", "tx")
    img = copy.deepcopy(r.image)
    used = [i for i, w in enumerate(img.windows) if w is not None]
    a, b = used[0], used[1]
    img.windows[a], img.windows[b] = img.windows[b], img.windows[a]
    assert compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)


def test_changed_constant_detected():
    spec, r = _compiled("spi mode 1", "check", None)
    img = copy.deepcopy(r.image)
    k = next(i for i, c in enumerate(img.consts) if c is not None)
    img.consts[k] ^= 1
    assert compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)


def test_changed_nominal_detected():
    spec, r = _compiled("uart 115200", "drive", "tx")
    img = copy.deepcopy(r.image)
    n = next(i for i, v in enumerate(img.noms) if v is not None)
    img.noms[n] += 1
    assert compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)


def test_pattern_mode_flip_detected():
    spec, r = _compiled("uart 115200", "check", None)
    img = copy.deepcopy(r.image)
    p = next(i for i, v in enumerate(img.patterns) if v is not None and i > 0)
    img.patterns[p] = dataclasses.replace(img.patterns[p], mode=1 - img.patterns[p].mode)
    assert compare(decode(img), r.edges, spec.initial_loc.name, spec.resync_loc.name)


def test_decoder_does_not_import_the_compiler_or_model():
    """Independence (CLAUDE.md §2): the decoder decodes words itself."""
    import ast
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[2] / "spex" / "decoder" / "__init__.py"
    names = set()
    for node in ast.walk(ast.parse(src.read_text())):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    assert not any(n.startswith(("spex", ".")) and n != "__future__" for n in names), names
