# DTC (read-only)

Copy the DTC project here unchanged: `dtc_model.py`, `dtc_asm.py`, `dtc_programs.py`, `test_dtc_*.py`, `run_tests.py`, `mutate.py`, `rtl/`, `tb/`, `formal/`, and the two summary documents.

**Reuse from it:**
- the lockstep trace-replay harness (`tb/dtc_trace.py`, `tb/test_*_cosim.py`);
- the RTL mutation harness (`tb/mutate_rtl.py`);
- the shadow-counter formal style;
- `dtc_trigger.sv` (a three-location timed automaton; the first engine prototype);
- `dtc_capture.sv` (trace front end).

Do not edit files here. Copy what you need into the new tree and note the origin in a header comment.
