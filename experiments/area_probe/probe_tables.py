"""Area per configuration table and per read port (owner request 2026-10-22).

    YOSYS=yowasp-yosys python3 probe_tables.py      # run from experiments/area_probe; liberty in lib/

Synthesises table_ports.v for every engine table of SEMANTICS v1 (after S44/S45) at 1..P read ports with the same
script as the other probes (synth -flatten; dfflibmap; abc; stat against the typical liberty) and prints a Markdown
table: storage-only area (1 port), each extra port's cost, and the total at the engine's port count.
Port counts are those of ta_engine_v4b.v: 4 guard reads per evaluation cycle (one per edge slot) plus the extra reads
named in PORTS_NOTE.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib", "sg13cmos5l_stdcell_typ_1p20V_25C.lib")
YOSYS = os.environ.get("YOSYS", "yowasp-yosys")

# name: (entries, bits per entry, engine read ports, what the ports are)
TABLES = {
    "windows": (16, 34, 6, "4 guard slots + location invariant + coverage margin; {clk 2, lo 16, hi 16}"),
    "nominal": (8, 16, 4, "4 slots at entry (POLICY nominal, S44)"),
    "patterns": (8, 17, 5, "4 guard slots + fired edge's trigger mask; 7 used, entry 0 = none"),
    "constants": (8, 16, 4, "4 data-guard slots"),
    "actions": (16, 32, 1, "fired edge"),
    "location words (flops)": (64, 14, 1, "current location; S44 moved these to a 1P_64x16 macro"),
}


def area(n, w, p):
    tag = f"tp_{n}_{w}_{p}"
    ys = os.path.join(HERE, f"_{tag}.ys")
    log = os.path.join(HERE, f"_{tag}.log")
    with open(ys, "w") as f:
        f.write(f"read_verilog {os.path.join(HERE, 'table_ports.v')}\n"
                f"chparam -set N {n} -set W {w} -set P {p} table_ports\n"
                f"synth -top table_ports -flatten\n"
                f"dfflibmap -liberty {LIB}\nabc -liberty {LIB}\nopt_clean\nstat -liberty {LIB}\n")
    try:
        subprocess.run([YOSYS, "-q", "-l", log, "-s", ys], check=True, capture_output=True, timeout=1800)
        text = open(log).read()
    finally:
        for f in (ys, log):
            if os.path.exists(f):
                os.remove(f)
    m = re.findall(r"Chip area for module '\\table_ports': ([\d.]+)", text)
    if not m:
        sys.exit(f"no area for {tag}")
    return float(m[-1])


def main():
    rows = []
    for name, (n, w, ports, note) in TABLES.items():
        a = [area(n, w, p) for p in range(1, ports + 1)]
        extra = [a[i] - a[i - 1] for i in range(1, len(a))]
        per_port = sum(extra) / len(extra) if extra else 0.0
        rows.append((name, n, w, n * w, a[0], per_port, ports, a[-1], note))
        print(f"{name}: " + ", ".join(f"{p + 1} ports {v:,.0f}" for p, v in enumerate(a)), flush=True)
    print()
    print("| table | entries x bits | bits | 1 read port (µm²) | each extra port (µm², mean) | engine ports | total at engine ports (µm²) | ports |")
    print("|---|---|---|---|---|---|---|---|")
    tot = 0.0
    for name, n, w, bits, a1, pp, ports, at, note in rows:
        print(f"| {name} | {n} x {w} | {bits} | {a1:,.0f} | {pp:,.0f} | {ports} | {at:,.0f} | {note} |")
        if not name.startswith("location"):
            tot += at
    print(f"\nSum of the tables an engine keeps in flops after S44 (all but location words): {tot:,.0f} µm²")


if __name__ == "__main__":
    main()
