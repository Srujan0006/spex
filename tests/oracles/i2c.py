"""I2C oracle and bus models, written from UM10204 only (independent of spec/ and spex/).

[Source: NXP UM10204 "I2C-bus specification and user manual", Rev. 7.0, 1 October 2021, Table 11
 "Characteristics of the SDA and SCL bus lines for Standard, Fast, and Fast-mode Plus I2C-bus devices";
 read from the PDF with pypdf on 2026-10-20.]
Conditions (UM10204 §3.1.4): START = SDA falls while SCL is high; STOP = SDA rises while SCL is high.
Data (§3.1.3): SDA is stable while SCL is high; it changes only while SCL is low. 8 data bits MSB first, then
an acknowledge bit from the receiver (low = ACK, high = NACK) (§3.1.5, §3.1.6). Clock stretching (§3.1.9): any
device may hold SCL low.

Lines in a pad word: SCL bit 0, SDA bit 1. A waveform is a list of pad words, one per cycle at f_clk.
Rise and fall times are 0 here (digital lines).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

SCL, SDA = 0, 1

# Table 11, in microseconds (min unless the key says max)
TIMING_US = {
    "standard": dict(tHD_STA=4.0, tLOW=4.7, tHIGH=4.0, tSU_STA=4.7, tSU_DAT=0.25, tSU_STO=4.0, tBUF=4.7,
                     tVD_max=3.45, fSCL_khz=100),
    "fast": dict(tHD_STA=0.6, tLOW=1.3, tHIGH=0.6, tSU_STA=0.6, tSU_DAT=0.1, tSU_STO=0.6, tBUF=1.3,
                 tVD_max=0.9, fSCL_khz=400),
}


def cycles(mode: str, f_clk: float = 48e6) -> Dict[str, int]:
    """Limits in clock cycles: minimums rounded up, maximums rounded down."""
    out = {}
    for k, v in TIMING_US[mode].items():
        if k == "fSCL_khz":
            continue
        n = v * 1e-6 * f_clk
        out[k] = math.floor(n + 1e-9) if k.endswith("_max") else math.ceil(n - 1e-9)
    return out


Error = Tuple[int, str]


def _b(v, i):
    return (v >> i) & 1


def check(w: List[int], mode: str, f_clk: float = 48e6):
    """Returns (events, errors). Events: ("S"|"Sr"|"P", cycle) and ("byte", cycle, value, ack: bool)."""
    t = cycles(mode, f_clk)
    ev, errs = [], []
    busy = False
    last_rise = last_fall = last_start = last_stop = last_sda = None
    first_fall_after_start = False
    bits: List[int] = []
    for n in range(1, len(w)):
        s0, s1 = _b(w[n - 1], SCL), _b(w[n], SCL)
        d0, d1 = _b(w[n - 1], SDA), _b(w[n], SDA)
        if s0 != s1:                                                # SCL first
            if s1 == 1:
                if busy:
                    if last_fall is not None and n - last_fall < t["tLOW"]:
                        errs.append((n, "tLOW"))
                    if last_sda is not None and last_fall is not None and last_sda >= last_fall \
                            and n - last_sda < t["tSU_DAT"]:
                        errs.append((n, "tSU;DAT"))
                    if d0 != d1:
                        errs.append((n, "tSU;DAT"))                 # SDA moved in the rising cycle
                    bits.append(d1)
                    if len(bits) == 9:
                        ev.append(("byte", n, sum(b << (7 - i) for i, b in enumerate(bits[:8])), bits[8] == 0))
                        bits = []
                last_rise = n
            else:
                if busy and last_rise is not None and n - last_rise < t["tHIGH"] and not first_fall_after_start:
                    errs.append((n, "tHIGH"))
                if first_fall_after_start and n - last_start < t["tHD_STA"]:
                    errs.append((n, "tHD;STA"))
                first_fall_after_start = False
                last_fall = n
            if d0 != d1 and s1 == 0:
                last_sda = n                                        # hold time 0: change with the fall is data
            continue
        if d0 == d1:
            continue
        if s1 == 1:                                                 # SDA moves while SCL high: START or STOP
            if d1 == 0:
                if busy:
                    if last_rise is not None and n - last_rise < t["tSU_STA"]:
                        errs.append((n, "tSU;STA"))
                    if len(bits) > 1:                       # one clock is the slot the condition sits in
                        errs.append((n, "START inside a byte"))
                    ev.append(("Sr", n))
                else:
                    if last_stop is not None and n - last_stop < t["tBUF"]:
                        errs.append((n, "tBUF"))
                    ev.append(("S", n))
                busy, bits, last_start, first_fall_after_start = True, [], n, True
            else:
                if last_rise is not None and n - last_rise < t["tSU_STO"]:
                    errs.append((n, "tSU;STO"))
                if len(bits) > 1:
                    errs.append((n, "STOP inside a byte"))
                ev.append(("P", n))
                busy, bits, last_stop = False, [], n
        else:                                                       # data change while SCL low
            if busy and last_fall is not None and n - last_fall > t["tVD_max"]:
                errs.append((n, "tVD (data valid late)"))
            last_sda = n
    return ev, errs


def transactions(events) -> List[list]:
    """Group events into [S, bytes..., P] lists of ("S"|"Sr"|"P") or (value, ack)."""
    out, cur = [], None
    for e in events:
        if e[0] == "S":
            cur = ["S"]
        elif e[0] == "Sr":
            cur.append("Sr")
        elif e[0] == "P":
            if cur is not None:
                cur.append("P")
                out.append(cur)
            cur = None
        elif cur is not None:
            cur.append((e[2], e[3]))
    return out


# ---------------------------------------------------------------- bus models
class Bus:
    """Wired-AND with pull-ups: a line is low iff some agent pulls it. Agents see the line of the previous cycle."""

    def __init__(self, *agents):
        self.agents = list(agents)

    def run(self, cycles_: int, extra=None) -> List[int]:
        line = 3
        w = []
        for n in range(cycles_):
            pull = 0
            for a in self.agents:
                pull |= a.step(n, line)
            if extra is not None:
                pull |= extra(n, line)
            line = 3 & ~pull
            w.append(line)
        return w


class Controller:
    """Scripted controller. script: list of ("S",), ("Sr",), ("P",), ("W", byte), ("R", ack: bool).
    Data changes `d` cycles after SCL falls; every interval is the UM10204 minimum plus `margin`."""

    def __init__(self, script, mode="standard", f_clk=48e6, d=2, margin=4, lead=10):
        self.t = cycles(mode, f_clk)
        self.d, self.m, self.lead = d, margin, lead
        self.script = list(script)
        self.acks: List[bool] = []
        self.reads: List[int] = []
        self.pull = 0
        self.g = self._run()
        self.line = 3

    def step(self, n, line):
        self.line = line
        try:
            next(self.g)
        except StopIteration:
            pass
        return self.pull

    def _set(self, scl=None, sda=None):
        if scl is not None:
            self.pull = (self.pull & ~1) | (0 if scl else 1)
        if sda is not None:
            self.pull = (self.pull & ~2) | (0 if sda else 2)

    def _wait(self, k):
        for _ in range(k):
            yield

    def _bit(self, out):
        """Entered just after SCL was pulled low. Returns the sampled SDA."""
        t, m = self.t, self.m
        yield from self._wait(self.d)
        self._set(sda=out)
        yield from self._wait(t["tLOW"] + m - self.d)
        self._set(scl=1)
        yield
        while not self.line & 1:                     # clock stretching: wait for the line
            yield
        sample = (self.line >> 1) & 1
        yield from self._wait(t["tHIGH"] + m)
        self._set(scl=0)
        yield
        return sample

    def _run(self):
        t, m = self.t, self.m
        yield from self._wait(self.lead)
        for op in self.script:
            if op[0] == "S":
                yield from self._wait(t["tBUF"] + m)
                self._set(sda=0)
                yield from self._wait(t["tHD_STA"] + m)
                self._set(scl=0)
                yield
            elif op[0] == "Sr":
                yield from self._wait(self.d)
                self._set(sda=1)
                yield from self._wait(t["tLOW"] + m - self.d)
                self._set(scl=1)
                yield
                while not self.line & 1:
                    yield
                yield from self._wait(t["tSU_STA"] + m)
                self._set(sda=0)
                yield from self._wait(t["tHD_STA"] + m)
                self._set(scl=0)
                yield
            elif op[0] == "P":
                yield from self._wait(self.d)
                self._set(sda=0)
                yield from self._wait(t["tLOW"] + m - self.d)
                self._set(scl=1)
                yield
                while not self.line & 1:
                    yield
                yield from self._wait(t["tSU_STO"] + m)
                self._set(sda=1)
                yield
            elif op[0] == "W":
                for i in range(8):
                    yield from self._bit((op[1] >> (7 - i)) & 1)
                self.acks.append((yield from self._bit(1)) == 0)
            elif op[0] == "R":
                v = 0
                for i in range(8):
                    v = (v << 1) | (yield from self._bit(1))
                self.reads.append(v)
                yield from self._bit(0 if op[1] else 1)
        while True:
            yield


class Target:
    """EEPROM-style target at a 7-bit address: first written byte sets the pointer, further bytes are stored,
    reads return mem[ptr++]. Drives SDA `d` cycles after SCL falls; optionally holds SCL low `stretch` cycles
    after the fall that ends each ACK it gives."""

    def __init__(self, addr=0x50, mem=None, d=3, stretch=0, ack_data=True):
        self.addr, self.mem = addr, dict(mem or {})
        self.d, self.stretch, self.ack_data = d, stretch, ack_data
        self.prev = 3
        self.state = "idle"          # idle / addr / write / read
        self.bits = 0
        self.shift = 0
        self.ptr = None
        self.sda_pull = 0
        self.sched = {}              # cycle -> sda pull value
        self.scl_until = -1
        self.first = True
        self.tx = 0
        self.acked = False
        self.gave_ack = False
        self.ptr_read = False
        self.written: List[int] = []

    def step(self, n, line):
        p = self.prev
        self.prev = line
        sclr = (p & 1) == 0 and line & 1
        sclf = (p & 1) == 1 and not line & 1
        if line & 1 and (p & 1):                    # SCL high, look for START/STOP
            if (p & 2) and not line & 2:
                self.state, self.bits, self.shift, self.sda_pull, self.sched = "addr", 0, 0, 0, {}
            elif not (p & 2) and line & 2:
                self.state, self.sda_pull, self.sched = "idle", 0, {}
        if sclr and self.state != "idle":
            self.bits += 1
            b = (line >> 1) & 1
            if self.bits <= 8:
                self.shift = (self.shift << 1) | b
            if self.bits == 9 and self.state == "read":
                self.acked = b == 0
        if sclf and self.state != "idle":
            self._on_fall(n)
        if n in self.sched:
            self.sda_pull = self.sched.pop(n)
        return (2 if self.sda_pull else 0) | (1 if n < self.scl_until else 0)

    def _on_fall(self, n):
        at = n + self.d
        if self.bits == 9 and self.gave_ack and self.stretch:
            self.scl_until = n + self.stretch           # hold SCL low after the ACK clock (UM10204 3.1.9)
        if self.bits == 8:
            self.gave_ack = False                          # ninth clock: ACK slot
            if self.state == "addr":
                if self.shift >> 1 == self.addr:
                    self.sched[at] = 1
                    self.gave_ack = True
                    if self.shift & 1:
                        self.state, self.ptr_read = "read", True
                    else:
                        self.state, self.first = "write", True
                else:
                    self.state = "idle"
                    self.sched[at] = 0
            elif self.state == "write":
                if self.first:
                    self.ptr, self.first = self.shift, False
                else:
                    self.mem[self.ptr] = self.shift
                    self.written.append(self.shift)
                    self.ptr = (self.ptr + 1) & 0xFF
                self.sched[at] = 1 if self.ack_data else 0
                self.gave_ack = self.ack_data
            elif self.state == "read":
                self.sched[at] = 0                  # release for the controller's ACK
        elif self.bits == 9:                        # the ACK clock ended
            self.bits, self.shift = 0, 0
            if self.state == "read" and (self.ptr_read or self.acked):
                self.ptr_read = False
                self.tx = self.mem.get(self.ptr or 0, 0xFF)
                self.ptr = ((self.ptr or 0) + 1) & 0xFF
                self.sched[at] = 0 if (self.tx >> 7) & 1 else 1
            elif self.state == "read":
                self.state = "idle"
                self.sched[at] = 0
            else:
                self.sched[at] = 0
        elif self.state == "read" and self.bits < 8:
            self.sched[at] = 0 if (self.tx >> (7 - self.bits)) & 1 else 1
