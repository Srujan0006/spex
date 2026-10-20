"""Table usage of every spec in every role (R11.8 sizing evidence; compiler listing line 'table use').

    python3 -B scripts/table_usage.py            # markdown table on stdout
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spec.i2c import i2c  # noqa: E402
from spec.spi import spi  # noqa: E402
from spec.uart_8n1 import uart_8n1  # noqa: E402
from spex.compiler import CompileError, compile_spec  # noqa: E402

SPECS = [
    ("uart_8n1 (115200 Bd: T=417, d=8)", lambda: uart_8n1(417, 8), ["tx"]),
    ("uart_8n1 (9600 Bd: T=5000, d=100)", lambda: uart_8n1(5000, 100), ["tx"]),
    ("uart_8n1 (300 Bd: T=160000, d=3200)", lambda: uart_8n1(160000, 3200), ["tx"]),
    ("spi mode 0 (H=12, tV=6)", lambda: spi(0), ["tgt"]),
    ("spi mode 1 (H=12, tV=6)", lambda: spi(1), ["tgt"]),
    ("i2c standard (100 kHz)", lambda: i2c("standard"), ["ctl", "tgt"]),
    ("i2c fast (400 kHz)", lambda: i2c("fast"), ["ctl", "tgt"]),
]
COLS = ["locations", "edges", "windows", "patterns", "constants", "actions"]


def rows():
    for name, make, sides in SPECS:
        for role, side in [("check", None)] + [("drive", s) for s in sides]:
            try:
                u = compile_spec(make(), role, side=side).usage
            except CompileError as e:
                u = "; ".join(sorted({x.split(": ", 1)[1].split(";")[0] for x in e.errors}))
            yield name, role + (f" ({side})" if side else ""), u


def main():
    print("| spec | role | " + " | ".join(COLS) + " | largest clock value |")
    print("|---" * (len(COLS) + 3) + "|")
    for name, role, u in rows():
        if isinstance(u, str):
            print(f"| {name} | {role} | compile error: {u} (needs the counted loop, SEMANTICS §1a) |" + " |" * len(COLS))
            continue
        print(f"| {name} | {role} | " + " | ".join(f"{u[k][0]}/{u[k][1]}" for k in COLS)
              + f" | {u['max_clock_value']} |")


if __name__ == "__main__":
    main()
