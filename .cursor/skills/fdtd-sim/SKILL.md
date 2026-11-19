---
name: fdtd-sim
description: >
  Drive local Ansys Lumerical FDTD. Use when the user mentions Lumerical,
  lumapi, an .fsp file, wavelength, a monitor, or transmission. If doctor
  reports that the solver is not installed, do not try to launch it.
---

# FDTD

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `fdtd_doctor`, `fdtd_validate`, `fdtd_prepare`, `fdtd_run`, `fdtd_sweep`, `fdtd_optimize`, and `fdtd_advise` are already available, call those tools.

For a new task, fill `confirmation.items` before solving. Each item has `name`, `source` (`specified` or `assumed`), and `value`. The names are `frequency`, `region`, `geometry`, `material`, `accuracy`, `stop`, and `outputs`. A sweep or search also needs `goal`, `range`, and `limit`. Call `confirm` and show the list to the user. `run`, `sweep`, and `optimize` accept only the spec `confirm` returns. They do not launch FDTD when `stage` is `confirm`. For an existing `.fsp`, use `inspect --project`, then `set` with `overrides` to edit a copy. The original file stays unchanged.

Lengths are metres and times are seconds. Call `fdtd doctor` first. If `installed` is not true, stop. Do not call `run`, `sweep`, or `optimize`. Set `LUMERICAL_ROOT` when the version directory is not found automatically. It must contain `api/python/lumapi.py`.

Examples are in `fdtd/examples`. `sweep` takes 2 to 8 values of one object property. `optimize` runs at most 8 times. Use `goal: max` for transmission. Both return `rows` and `best` in the same shape as COMSOL and HFSS. `best` is one row. The score is in `results`, and the parameter name is `object.property`. After a solve, call `fdtd advise` and write the advice from those facts. `best` is only the best result among the computed runs. If it lies at an end of the interval, say that a wider interval may contain a better point. Reports include `assumptions`, taken from checklist items whose `source` is `assumed`.

Copy a source `.fsp` into `fdtd/runs` before editing it. Do not overwrite the user's original project.
