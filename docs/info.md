<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

SPEX executes a protocol specification written as a timed automaton (locations, clocks, timing windows, pin events). One spec runs in four roles: Drive (plays one side), Check (monitors a bus and reports timing and sequence violations), Stress (drives at the edges of every timing window) and Cover (records transition coverage and timing margins). Status: pre-RTL; this tile currently holds the Tiny Tapeout example design.

## How to test

The reference model and tests are in the repository: `python3 -B -m pytest -q`.

## External hardware

None yet.
