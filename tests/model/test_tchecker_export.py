"""Step 6 exporter (structure only; the model checking runs in CI, workflow `tchecker`).

Planted bugs: tests/model/mutants.py ("urgency invariant dropped", "bit counter not counted")."""
import os
import sys

from spec.uart_8n1 import uart_8n1
from spex.tchecker import NO_DOUBLE_START, export

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import export_tchecker  # noqa: E402

EV = {"start bit": "start", "stop bit": "stop"}


def lines(text, prefix):
    return [l for l in text.splitlines() if l.startswith(prefix)]


def test_uart_export_structure():
    t = export(uart_8n1(48, 4), EV, [NO_DOUBLE_START])
    locs = {l.split(":")[2].split("{")[0]: l for l in lines(t, "location:spec:")}
    assert set(locs) == {"IDLE", "START", "OPEN_D", "STABLE", "OPEN_S", "STOPST"}
    assert "initial:" in locs["IDLE"] and "invariant" not in locs["IDLE"]
    assert "g<=42" in locs["START"]                        # urgency of the internal tick (GE 42)
    assert "g<=10" in locs["OPEN_D"]                       # the spec's own invariant
    edges = lines(t, "edge:spec:")
    assert "edge:spec:IDLE:START:start{do: g=0;bitcnt=0}" in edges
    assert any(e.startswith("edge:spec:OPEN_D:STABLE:") and "g>=2&&g<=10" in e and "bitcnt=bitcnt+1" in e
               for e in edges)
    assert any(e.startswith("edge:spec:STABLE:OPEN_S:") and "bitcnt==8" in e for e in edges)
    assert lines(t, "sync:") == ["sync:spec@start:obs_frame@start", "sync:spec@stop:obs_frame@stop"]


def untimed_bad_reachable(text):
    """Untimed product reachability of the observer's bad location (an over-approximation of TChecker's answer)."""
    spec_edges = [l.split("{")[0].split(":")[2:5] for l in lines(text, "edge:spec:")]
    obs_edges = [l.split(":")[2:5] for l in lines(text, "edge:obs_frame:")]
    seen, todo = set(), [("IDLE", "idle")]
    while todo:
        s, o = todo.pop()
        if (s, o) in seen:
            continue
        seen.add((s, o))
        for src, dst, ev in spec_edges:
            if src != s:
                continue
            if ev in ("start", "stop"):
                todo += [(dst, od) for os_, od, oe in obs_edges if os_ == o and oe == ev]
            else:
                todo.append((dst, o))
    return any(o == "bad" for _, o in seen)


def test_teeth_model_differs_from_good_one_untimed():
    models = {n: (t, exp) for n, t, exp in export_tchecker.models()}
    assert untimed_bad_reachable(models["uart_broken"][0]) and models["uart_broken"][1] is True
    assert not untimed_bad_reachable(models["uart_8n1"][0]) and models["uart_8n1"][1] is False


def test_model_check_with_tchecker(tmp_path):
    """Runs TChecker when TCK_REACH points at tck-reach (CI workflow `tchecker` does; locally:
    scripts/build_tchecker.sh DIR, then TCK_REACH=DIR/bin/tck-reach)."""
    import pytest
    import subprocess
    exe = os.environ.get("TCK_REACH")
    if not exe:
        pytest.skip("TCK_REACH not set")
    script = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "export_tchecker.py")
    r = subprocess.run([sys.executable, "-B", script, str(tmp_path), "--tck-reach", exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "MISMATCH" not in r.stdout and r.stdout.count(": OK") == 28     # 15 models: bad on each, ok on the 13 that have it


def test_spi_and_i2c_export_structure():
    """SPI and I2C models (owner, 2026-10-22). The planted bugs are the teeth models spi_broken, i2c_stray_stop and
    i2c_short_buf, which the `tchecker` CI workflow must find reachable."""
    models = {n: (t, exp) for n, t, exp in export_tchecker.models()}
    for m in range(4):
        t, exp = models[f"spi_m{m}"]
        assert exp is False
        assert {l.split(":")[1].split("@")[1] for l in lines(t, "sync:")} == {"select", "deselect", "sample", "byte"}
    assert models["spi_broken"][1] is True
    # tBUF comes from UM10204 Table 10 at 48 MHz, not from the spec: 4.7 us -> 226 cycles, 1.3 us -> 63
    assert "obs_buf_y>=226" in models["i2c_standard_buf"][0] and "obs_buf_y>=63" in models["i2c_fast_buf"][0]
    good, short = models["i2c_fast_buf"][0], models["i2c_short_buf"][0]
    diff = [(a, b) for a, b in zip(good.splitlines(), short.splitlines()) if a != b]
    assert all("system:" in a or "BUSFREE" in a for a, _ in diff) and any("BUSFREE" in a for a, _ in diff)
    assert models["i2c_stray_stop"][1] is True and models["i2c_short_buf"][1] is True
