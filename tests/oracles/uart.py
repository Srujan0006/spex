"""UART 8N1 oracle, written from the common asynchronous framing only (independent of spec/ and spex/).

Framing [Source: the de-facto standard asynchronous serial frame, as in TIA-232 practice and every UART datasheet]:
idle line high; a frame is a start bit (low), 8 data bits least-significant first, one stop bit (high).
Bit time T line cycles. A receiver finds the falling start edge at t0 and samples bit k (start = 0, data 1..8,
stop = 9) at the middle of the bit, t0 + (k + 1/2) T.

Timing rule used here (stricter than a sampling receiver, so it can judge a transmitter's edges):
every transition inside a frame lies within +-tol of a nominal boundary t0 + k T (k = 1..9), at most one per boundary;
the next start edge comes no earlier than t0 + 10 T - tol (the stop bit is a full bit, less the tolerance).

A waveform is a list of line values (0/1), one per line (pad) cycle.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

Error = Tuple[int, str]          # (line cycle, kind)


def encode(data: List[int], T: int, lead: int = 20, gap: int = 0, tail: int = 20,
           offset: Optional[Callable[[int, int], int]] = None) -> List[int]:
    """Legal 8N1 waveform. offset(frame, k) shifts boundary k (1..9) and the next start (k = 10) by that many
    cycles; keep |offset| <= tol to stay legal."""
    off = offset or (lambda f, k: 0)
    w = [1] * lead
    for f, byte in enumerate(data):
        bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
        t0 = len(w)
        bounds = [t0] + [t0 + k * T + off(f, k) for k in range(1, 10)] + [t0 + 10 * T + off(f, 10) + gap]
        for k, b in enumerate(bits):
            w += [b] * (bounds[k + 1] - bounds[k])
    return w + [1] * tail


def decode(w: List[int], T: int, tol: int) -> Tuple[List[int], List[Error]]:
    data, errs = [], []
    t, n = 1, len(w)
    earliest_start = 0
    while t < n:
        if not (w[t - 1] == 1 and w[t] == 0):
            t += 1
            continue
        t0 = t
        if t0 < earliest_start:
            errs.append((t0, "stop bit too short"))
        end = t0 + (19 * T) // 2              # stop-bit sample point
        if end >= n:
            errs.append((t0, "truncated frame"))
            break
        samples = [w[t0 + ((2 * k + 1) * T) // 2] for k in range(10)]
        if samples[0] != 0:
            errs.append((t0, "false start"))
        if samples[9] != 1:
            errs.append((t0 + (19 * T) // 2, "framing error"))
        used = set()
        for u in range(t0 + 1, end + 1):
            if w[u] != w[u - 1]:
                k = round((u - t0) / T)
                if not 1 <= k <= 9 or abs(u - t0 - k * T) > tol or k in used:
                    errs.append((u, "transition off the bit grid"))
                used.add(k)
        if samples[0] == 0 and samples[9] == 1:
            data.append(sum(b << i for i, b in enumerate(samples[1:9])))
        earliest_start = t0 + 10 * T - tol
        t = end + 1
        while t < n and w[t] == 1:            # idle until the next start edge
            t += 1
    return data, errs
