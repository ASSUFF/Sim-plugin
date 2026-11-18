---
name: hfss-sim
description: >
  Drive local Ansys HFSS: solve, sweep, and optimize. Use when the user
  mentions HFSS, Electronics Desktop, an .aedt file, S-parameters, WR-90,
  or a waveguide.
---

# HFSS

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `hfss_doctor`, `hfss_validate`, `hfss_prepare`, `hfss_run`, `hfss_sweep`, `hfss_optimize`, and `hfss_advise` are already available, call those tools.

When the user states a simulation task in full for the first time, do not launch HFSS. Organize the request, fill in settings that are easy to miss, and ask the user to confirm. Mark each item as specified or assumed. Cover frequency, geometry and materials, the solution region, mesh or adaptive-pass accuracy, the S-parameters to report, and, for a sweep or search, the goal, the range, and the run limit. Start `run`, `sweep`, or `optimize` only after confirmation. For an existing `.aedt`, use `inspect --project`, then `set` with `variables` to edit a copy. The original file stays unchanged.

Lengths are metres and frequency is hertz. For S21 use `dB(S(P2,P1))` and `goal: max`. For S11 use `dB(S(P1,P1))` and `goal: min`.

Call `hfss doctor` first. If port `1055@localhost` is closed, do not start a solve. `hfss run` solves one spec. `hfss sweep` compares 2 to 8 values of one parameter. `hfss optimize` searches one numeric path, at most 8 times. After a solve, call `hfss advise` and write the advice from those facts.

The WR-90 example is `hfss/examples/wr90.json`. At 10 GHz and a length of 0.03 m, S21 is 0.0 dB and S11 is -64.084 dB. The length search example is `hfss/examples/wr90_length_optimize.json`. The length sweep example is `hfss/examples/wr90_length_sweep.json`.

Point `HFSS_AEDT_PYTHON` at the Python executable of the hfss-aedt environment, and `HFSS_AEDT_SRC` at that checkout's `src` directory, when they are not already on this computer.

`best` is only the best result among the computed runs. If it lies at an end of the interval, say that a wider interval may contain a better point.

Do not close an Electronics Desktop window the user already has open. A source project is copied into `hfss/runs` before it is edited.
