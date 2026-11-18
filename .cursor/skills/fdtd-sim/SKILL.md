---
name: fdtd-sim
description: >
  Drive local Ansys Lumerical FDTD. Use when the user mentions Lumerical,
  lumapi, an .fsp file, wavelength, a monitor, or transmission. If doctor
  reports that the solver is not installed, do not try to launch it.
---

# FDTD

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `fdtd_doctor`, `fdtd_validate`, `fdtd_prepare`, `fdtd_run`, `fdtd_sweep`, `fdtd_optimize`, and `fdtd_advise` are already available, call those tools.

When the user states a simulation task in full for the first time, do not launch FDTD. Organize the request, fill in settings that are easy to miss, and ask the user to confirm. Mark each item as specified or assumed. Cover wavelength and bandwidth, the simulation region and boundaries, geometry and materials, mesh accuracy, simulation time, the monitors to export, and, for a sweep or search, the goal, the range, and the run limit. Start `run`, `sweep`, or `optimize` only after confirmation.

Lengths are metres and times are seconds. Call `fdtd doctor` first. If `installed` is not true, stop. Do not call `run`, `sweep`, or `optimize`. Set `LUMERICAL_ROOT` when the version directory is not found automatically. It must contain `api/python/lumapi.py`.

Examples are in `fdtd/examples`. `sweep` takes 2 to 8 values of one object property. `optimize` runs at most 8 times. Use `goal: max` for transmission. After a solve, call `fdtd advise` and write the advice from those facts. `best` is only the best result among the computed runs. If it lies at an end of the interval, say that a wider interval may contain a better point.

Copy a source `.fsp` into `fdtd/runs` before editing it. Do not overwrite the user's original project.
