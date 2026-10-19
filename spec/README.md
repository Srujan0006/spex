# Protocol specs

One file per protocol, written in the SPEX DSL (`spex/dsl`).

Each spec declares:
- its sides (for example `controller`, `target`);
- the owner side of every action;
- its choice points;
- a resync location for the Check role.

Week 1 targets: `uart_8n1.py`, `spi.py` (modes 0-3), `i2c.py` (controller + target, 100/400 kHz).
