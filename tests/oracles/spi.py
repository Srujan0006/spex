"""SPI oracle, modes 0-3, written from the SPI definitions only (independent of spec/ and spex/).

[Source: Motorola/Freescale "SPI Block Guide V04.01", clock phase and polarity section]
- CPOL: SCK idle level. The *leading* edge leaves the idle level, the *trailing* edge returns to it.
- CPHA = 0: data is sampled on the leading edge and changed on the trailing edge; the first bit is valid
  once SS (here CS, active low) falls.
- CPHA = 1: data is changed on the leading edge and sampled on the trailing edge.
- Data is MSB first (the common setting; the Block Guide allows LSB first as an option).
Device timing (setup tSU and hold tH around a sampling edge, minimum SCK half period) is datasheet-specific,
so it is a parameter here.

Pins in a pad word: CS bit 0, SCK bit 1, MOSI bit 2, MISO bit 3. A waveform is a list of pad words, one per cycle.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

CS, SCK, MOSI, MISO = 0, 1, 2, 3
Error = Tuple[int, str]


def _b(v, i):
    return (v >> i) & 1


def gen_controller(mode: int, frames: List[List[int]], H: int, lead: int = 20, t_lead: int = None,
                   t_lag: int = None, gap: int = 30, mosi_delay: int = 0, bits: Dict[int, int] = None) -> List[int]:
    """CS/SCK/MOSI of a controller. frames = list of byte lists; H = SCK half period (cycles).
    MOSI changes `mosi_delay` cycles after each shift edge (or after CS falls, for the first bit in CPHA 0).
    bits = {frame index: number of bits} truncates a frame (a planted fault). MISO bit is left at 1."""
    cpol, cpha = mode >> 1, mode & 1
    t_lead = H if t_lead is None else t_lead
    t_lag = H if t_lag is None else t_lag
    w: List[int] = []

    def put(n, cs, sck, mosi):
        for _ in range(n):
            w.append(cs << CS | sck << SCK | mosi << MOSI | 1 << MISO)

    put(lead, 1, cpol, 1)
    for f, frame in enumerate(frames):
        seq = [(byte >> (7 - i)) & 1 for byte in frame for i in range(8)]
        if bits and f in bits:
            seq = seq[:bits[f]]
        mosi = 1
        events = []                                  # (time offset, sck, mosi)
        if cpha == 0 and seq:
            events.append((mosi_delay, cpol, seq[0]))
        t = t_lead
        for i, b in enumerate(seq):
            lead_t, trail_t = t, t + H
            if cpha == 1:
                events.append((lead_t, 1 - cpol, None))
                events.append((lead_t + mosi_delay, None, b))
            else:
                events.append((lead_t, 1 - cpol, None))
            events.append((trail_t, cpol, None))
            if cpha == 0 and i + 1 < len(seq):
                events.append((trail_t + mosi_delay, None, seq[i + 1]))
            t = trail_t + H
        end = (t - H) + t_lag if seq else t_lead
        sck = cpol
        for u in range(end):
            for (et, es, em) in events:
                if et == u:
                    if es is not None:
                        sck = es
                    if em is not None:
                        mosi = em
            put(1, 0, sck, mosi)
        put(gap, 1, cpol, mosi)
    return w


def add_target(w: List[int], mode: int, frames: List[List[int]], delay: int = 2, release: int = 1) -> List[int]:
    """Behavioural target on an existing controller waveform: drives MISO `delay` cycles after each shift event
    (CS fall for the first bit in CPHA 0; trailing edges in CPHA 0, leading edges in CPHA 1); MISO = `release`
    while CS is high."""
    cpol, cpha = mode >> 1, mode & 1
    out = list(w)
    changes = {}                                      # cycle -> MISO value
    f, bitq, miso = -1, [], release
    for n in range(1, len(w)):
        cs0, cs1 = _b(w[n - 1], CS), _b(w[n], CS)
        s0, s1 = _b(w[n - 1], SCK), _b(w[n], SCK)
        if cs0 == 1 and cs1 == 0:
            f += 1
            data = frames[f] if f < len(frames) else []
            bitq = [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]
            if cpha == 0:
                changes[n + delay] = bitq.pop(0) if bitq else 1
        elif cs0 == 0 and cs1 == 1:
            changes[n] = release
        elif cs1 == 0 and s0 != s1:
            leading = s1 != cpol
            shift = (cpha == 0 and not leading) or (cpha == 1 and leading)
            if shift and bitq:
                changes[n + delay] = bitq.pop(0)
    for n in range(len(out)):
        if n in changes:
            miso = changes[n]
        out[n] = (out[n] & ~(1 << MISO)) | (miso << MISO)
    return out


def check(w: List[int], mode: int, tsu: int, th: int, hmin: int):
    """Returns (frames of (mosi_bytes, miso_bytes), errors). Errors: (cycle, kind)."""
    cpol, cpha = mode >> 1, mode & 1
    errs: List[Error] = []
    frames = []
    n = 1
    N = len(w)
    while n < N:
        if not (_b(w[n - 1], CS) == 1 and _b(w[n], CS) == 0):
            n += 1
            continue
        if _b(w[n], SCK) != cpol:
            errs.append((n, "SCK not idle at CS fall"))
        start = n
        end = start
        while end < N and _b(w[end], CS) == 0:
            end += 1
        if end < N and _b(w[end], SCK) != cpol:
            errs.append((end, "SCK not idle at CS rise"))
        edges = [u for u in range(start + 1, end) if _b(w[u], SCK) != _b(w[u - 1], SCK)]
        last = start
        for u in edges:
            if u - last < hmin:
                errs.append((u, "SCK half period too short"))
            last = u
        samples = [u for u in edges if (_b(w[u], SCK) != cpol) == (cpha == 0)]
        mo, mi = [], []
        for s in samples:
            for pin, name in ((MOSI, "MOSI"), (MISO, "MISO")):
                lo, hi = max(s - tsu, start), min(s + th, end - 1)
                if any(_b(w[u], pin) != _b(w[u - 1], pin) for u in range(lo + 1, hi + 1)):
                    errs.append((s, f"{name} setup/hold"))
            mo.append(_b(w[s], MOSI))
            mi.append(_b(w[s], MISO))
        if len(samples) % 8:
            errs.append((end, f"{len(samples)} bits in frame, not a multiple of 8"))

        def pack(bits):
            return [sum(b << (7 - i) for i, b in enumerate(bits[k:k + 8])) for k in range(0, len(bits) - 7, 8)]
        frames.append((pack(mo), pack(mi)))
        n = end + 1
    return frames, errs
