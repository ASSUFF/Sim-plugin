---
name: hfss-sim
description: >
  Drive local Ansys HFSS: solve, sweep, and optimize. Use when the user
  mentions HFSS, Electronics Desktop, an .aedt file, S-parameters, WR-90,
  or a waveguide.
---

# HFSS

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `hfss_doctor`, `hfss_validate`, `hfss_prepare`, `hfss_run`, `hfss_sweep`, `hfss_optimize`, and `hfss_advise` are already available, call those tools.

For a new task, fill `confirmation.items` before solving. Each item has `name`, `source` (`specified` or `assumed`), and `value`. The names are `frequency`, `region`, `geometry`, `material`, `accuracy`, `stop`, and `outputs`. A sweep or search also needs `goal`, `range`, and `limit`. Call `confirm` and show the list to the user. `run`, `sweep`, and `optimize` accept only the spec `confirm` returns. They do not launch HFSS when `stage` is `confirm`. Each report stores `assumptions` from checklist items whose `source` is `assumed`. For an existing `.aedt`, use `inspect --project`, then `set` with `variables` to edit a copy. The original file stays unchanged.

Lengths are metres and frequency is hertz. For S21 use `dB(S(P2,P1))` and `goal: max`. For S11 use `dB(S(P1,P1))` and `goal: min`.

Call `hfss doctor` first. If port `1055@localhost` is closed, do not start a solve. `hfss run` solves one spec. `hfss sweep` compares one parameter, or every combination in `sweep`, at most 8 solves. More than 8 returns `stage` `spec`. A real solve first passes the checklist; a failure returns `stage` `checklist`. A license failure returns `stage` `license` and one next step. Do not start the license service again. `hfss optimize` searches one numeric path, at most 8 times. After a solve, call `hfss advise` and write the advice from those facts.

The WR-90 example is `hfss/examples/wr90.json`. At 10 GHz and a length of 0.03 m, S21 is 0.0 dB and S11 is -64.084 dB. The length search example is `hfss/examples/wr90_length_optimize.json`. The length sweep example is `hfss/examples/wr90_length_sweep.json`.

`HFSS_AEDT_PYTHON` is the Python executable of the hfss-aedt environment, and `HFSS_AEDT_SRC` is that checkout's `src` directory. Both are required. If a command returns `stage` `backend`, tell the user those two variables and stop. Do not look for a path from another computer.

`best` is only the best result among the computed runs. If it lies at an end of the interval, say that a wider interval may contain a better point.

Do not close an Electronics Desktop window the user already has open. A source project is copied into `hfss/runs` before it is edited.
