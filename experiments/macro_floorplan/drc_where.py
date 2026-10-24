"""Where are a run's detailed-routing violations? (was used by the removed fp_report workflow; run it on a downloaded runs/ directory)

    python3 drc_where.py RUN_DIR CONFIG_JSON

Reads the final DRC report of the detailed-routing step under RUN_DIR (runs/wokwi) and the macro placements from
CONFIG_JSON (LibreLane MACROS), and prints the violations bucketed by layer and type, by location (over a macro,
within 5 um of one, or in the open core), by the nets involved, and by 50 um hot spot.
"""
import collections
import glob
import json
import os
import re
import sys

SIZE = {"RM_IHPSG13_1P_64x64_c2_bm_bist": (784.48, 64.36), "RM_IHPSG13_1P_256x32_c2_bm_bist": (416.64, 118.78),
        "RM_IHPSG13_1P_64x16_c2": (236.8, 64.36)}


def main(run_dir, config):
    reps = sorted(glob.glob(os.path.join(run_dir, "*detailedrouting*", "*.drc")))
    if not reps:
        print("no detailed-routing DRC report")
        return
    text = open(reps[-1]).read()
    v = re.findall(r"violation type: (\S.*)\n\tsrcs: (.*)\n\tbbox = \(([\d.]+), ([\d.]+)\) - \(([\d.]+), ([\d.]+)\) "
                   r"on Layer (\S+)", text)
    print(f"{reps[-1]}: {len(v)} violations")
    boxes = []
    for name, m in json.load(open(config)).get("MACROS", {}).items():
        w, h = SIZE.get(name, (0, 0))
        for inst, pl in m["instances"].items():
            x, y = pl["location"]
            boxes.append((inst, x, y, x + w, y + h, pl["orientation"]))

    def where(x0, y0, x1, y1):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for inst, a, b, c, d, o in boxes:
            if a <= cx <= c and b <= cy <= d:
                face = "pin face" if (o in ("FS", "S") and cy > d - 3) or (o in ("N", "FN") and cy < b + 3) else "interior"
                return f"over {inst} ({face})"
        for inst, a, b, c, d, o in boxes:
            if a - 5 <= cx <= c + 5 and b - 5 <= cy <= d + 5:
                return f"within 5 um of {inst}"
        return "open core"

    kinds, places, nets, spots = (collections.Counter() for _ in range(4))
    for t, srcs, x0, y0, x1, y1, layer in v:
        x0, y0, x1, y1 = map(float, (x0, y0, x1, y1))
        kinds[(layer, t)] += 1
        places[where(x0, y0, x1, y1)] += 1
        for s in srcs.split():
            nets[s] += 1
        spots[(int((x0 + x1) / 100) * 50, int((y0 + y1) / 100) * 50)] += 1
    for title, c, n in (("layer / type", kinds, 20), ("location", places, 20), ("sources (nets, instances)", nets, 15),
                        ("50 um hot spots (x, y lower-left)", spots, 12)):
        print(f"\n-- {title}")
        for k, cnt in c.most_common(n):
            print(f"{cnt:6d}  {k}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
