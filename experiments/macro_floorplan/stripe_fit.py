"""Which macro x positions put every Metal4 power stripe inside a same-net power column of the macro?

    python3 stripe_fit.py <macro.lef> [--pitch 67.44 --offset 26.36 --core-x 2.88 --width 2.1 --gnd 5.62]

Stripe pairs (Tiny Tapeout cmos5l block PDN): POWER centre at core_x + offset + pitch * n, GROUND centre gnd um to
its right, both `width` wide, full core height. A stripe crossing the macro must lie inside power columns of its
own net over the whole macro height, except one gap of at most MAX_GAP um (the VDD!/VDDARRAY! split, where the LEF
has an OBS; method and gap rule from Loom's src/pdn_cfg.tcl, Apache-2.0, credited in docs/notes/CREDITS.md).
Prints the macro x positions (on the macro's own column grid) where that holds for every crossing stripe.
"""
import argparse
import re

MAX_GAP = 7.0
NETS = {"P": ("VDD!", "VDDARRAY!"), "G": ("VSS!",)}


def columns(lef):
    t = open(lef).read()
    w, h = map(float, re.search(r"SIZE ([\d.]+) BY ([\d.]+)", t).groups())
    cols = {}
    for net, pins in NETS.items():
        rs = []
        for pin in pins:
            m = re.search(r"PIN %s\s(.*?)END %s" % (re.escape(pin), re.escape(pin)), t, re.S)
            if m:
                rs += [tuple(map(float, r)) for r in re.findall(r"RECT ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", m.group(1))]
        cols[net] = rs
    return w, h, cols


def stripe_ok(xc, half, rects, h):
    """Rects covering [xc-half, xc+half] in x; their union in y must span 0..h with gaps <= MAX_GAP."""
    ys = sorted((r[1], r[3]) for r in rects if r[0] <= xc - half + 1e-6 and r[2] >= xc + half - 1e-6)
    if not ys:
        return False
    at = 0.0
    for y0, y1 in ys:
        if y0 - at > MAX_GAP:
            return False
        at = max(at, y1)
    return h - at <= MAX_GAP and ys[0][0] <= MAX_GAP


def fits(x, w, h, cols, a):
    """True if every stripe crossing the macro placed at x is inside its own net's columns."""
    n0 = int((x - a.core_x - a.offset - a.gnd - a.width) // a.pitch) - 1
    crossing = 0
    for n in range(max(n0, 0), n0 + int(w // a.pitch) + 4):
        for net, d in (("P", 0.0), ("G", a.gnd)):
            xc = a.core_x + a.offset + a.pitch * n + d - x
            if -a.width / 2 < xc < w + a.width / 2:
                crossing += 1
                if not stripe_ok(xc, a.width / 2, cols[net], h):
                    return False, crossing
    return True, crossing


def main():
    p = argparse.ArgumentParser()
    p.add_argument("lef")
    p.add_argument("--pitch", type=float, default=67.44)
    p.add_argument("--offset", type=float, default=26.36)
    p.add_argument("--core-x", type=float, default=2.88)
    p.add_argument("--width", type=float, default=2.1)
    p.add_argument("--gnd", type=float, default=5.62)
    p.add_argument("--xmax", type=float, default=1721.28)
    a = p.parse_args()
    w, h, cols = columns(a.lef)
    vdd_x0 = min((r[0] + r[2]) / 2 for r in cols["P"])
    base = (a.core_x + a.offset - vdd_x0) % 11.24
    good = []
    x = base
    while x + w <= a.xmax:
        ok, n = fits(round(x, 3), w, h, cols, a)
        if ok:
            good.append((round(x, 3), n))
        x += 11.24
    print(f"{a.lef.split('/')[-1]}: {w} x {h}; {len(good)} fitting x positions (x, stripes crossing):")
    print("  ", good)


if __name__ == "__main__":
    main()
