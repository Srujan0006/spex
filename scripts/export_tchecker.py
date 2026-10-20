"""Export the step-6 TChecker models and, if tck-reach is on PATH (or given), check each against its expected verdict.

    python3 -B scripts/export_tchecker.py OUT_DIR [--tck-reach PATH]

Models (expected reachability of the observer's `bad` label):
  uart_8n1        spec/uart_8n1.py with the frame observer "never two start bits without a stop"   -> unreachable
  uart_broken     the same spec plus a planted edge that starts a new frame from the middle of one  -> reachable (teeth)
  uart_time       uart_8n1 with the timed observer "stop bit 9T +- d after the start bit"            -> unreachable
  uart_slow_stop  the same, but the spec's stop window is 10 cycles wider (a timing-only bug)        -> reachable (teeth)
Exit status: 0 if every verdict matches, 1 otherwise, 2 if tck-reach is missing (models are still written).
"""
import argparse
import copy
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spec.uart_8n1 import uart_8n1  # noqa: E402
from spex.dsl import Op  # noqa: E402
from spex.tchecker import NO_DOUBLE_START, export, frame_time  # noqa: E402

UART_EVENTS = {"start bit": "start", "stop bit": "stop"}


def broken_uart():
    s = uart_8n1(T, D)
    L = {l.name: l for l in s.locs}
    # planted bug: from the middle of a frame, the transmitter may start another frame
    s.emit(L["STABLE"], L["START"], "tx", {"TX": 0}, op=Op("LOAD"), reset=["g"], label="broken restart")
    return s


T, D = 48, 4


def slow_stop_uart():
    s = uart_8n1(T, D)
    stop = next(e for e in s.edges if e.label == "stop bit")
    stop.window = s.window("g", stop.window.lo, stop.window.hi + 10, nom=stop.window.nom)   # planted timing bug
    stop.src.invariant = s.window("g", 0, stop.window.hi)       # ...with its invariant (else the bug is masked)
    return s


def models():
    yield "uart_8n1", export(uart_8n1(T, D), UART_EVENTS, [NO_DOUBLE_START]), False
    ev = dict(UART_EVENTS, **{"broken restart": "start"})
    yield "uart_broken", export(broken_uart(), ev, [NO_DOUBLE_START], name="uart_broken"), True
    obs = frame_time(9 * T - D, 9 * T + D)
    yield "uart_time", export(uart_8n1(T, D), UART_EVENTS, [obs], name="uart_time"), False
    yield "uart_slow_stop", export(slow_stop_uart(), UART_EVENTS, [obs], name="uart_slow_stop"), True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--tck-reach", default=shutil.which("tck-reach"))
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ok = True
    for name, text, expect in models():
        path = os.path.join(a.out, f"{name}.tck")
        open(path, "w").write(text)
        if not a.tck_reach:
            print(f"{name}: written to {path} (tck-reach not found, not checked)")
            continue
        checks = [("bad", expect)] + ([("ok", True)] if "labels: ok" in text else [])   # ok: not vacuous
        for label, want in checks:
            r = subprocess.run([a.tck_reach, "-a", "reach", "-l", label, path], capture_output=True, text=True)
            m = re.search(r"REACHABLE\s+(true|false)", r.stdout)
            got = None if m is None else m.group(1) == "true"
            good = got is want
            ok &= good
            print(f"{name}: {label} reachable = {got}, expected {want}: {'OK' if good else 'MISMATCH'}")
            if got is None:
                print(r.stdout[-2000:], r.stderr[-2000:])
    if not a.tck_reach:
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
