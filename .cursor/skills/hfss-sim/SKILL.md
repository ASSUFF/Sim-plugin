---
name: hfss-sim
description: >
  Drive local Ansys HFSS: solve, sweep, and optimize. Use when the user
  mentions HFSS, Electronics Desktop, an .aedt file, S-parameters, WR-90,
  or a waveguide.
---

# HFSS

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `hfss_doctor`, `hfss_validate`, `hfss_prepare`, `hfss_run`, `hfss_sweep`, `hfss_optimize`, and `hfss_advise` are already available, call those tools.

For a new task, fill `confirmation.items` before solving. Each item has `name`, `source` (`specified` or `assumed`), and `value`. The names are `frequency`, `region`, `geometry`, `material`, `accuracy`, `stop`, and `outputs`. A sweep or search also needs `goal`, `range`, and `limit`. When `base` is already confirmed, the outer list only adds those three. Editing the spec still requires `confirm` again. Call `confirm` and show the list to the user. `run`, `sweep`, and `optimize` accept only the spec `confirm` returns. They do not launch HFSS when `stage` is `confirm`. Each report stores `assumptions` from checklist items whose `source` is `assumed`. For an existing `.aedt`, use `inspect --project`. It lists design variable names. Then `set` with `variables` to edit a copy. The original file stays unchanged.

Lengths are metres and frequency is hertz. For one mode, S21 is `dB(S(P2,P1))` with `goal: max`, and S11 is `dB(S(P1,P1))` with `goal: min`. The geometry is only a straight rectangular waveguide. `geometry.modes` is 1 to 4 and defaults to 1. With more than one mode the names are `dB(S(P2:2,P1:1))` and the same pattern for the other pairs. `geometry.wall` defaults to `pec`. `copper`, `gold`, `aluminum`, and `silver` use built-in conductivities. `finite` also needs `wall_conductivity_s_m` in siemens per metre. The result does not include Neff or Z0. A spectrum is `frequency_sweep` with `start_hz`, `stop_hz`, and `count` from 2 to 201. It is solved once with the adaptive `frequency_hz`, and the curve is `s_spectrum.csv`. `frequencies_hz` is only a checklist list of 1 to 21 points. Set `material_verified` to true before using a material outside the built-in names.

Call `hfss doctor` first. If port `1055@localhost` is closed, do not start a solve. `hfss run` solves one spec. `hfss sweep` compares one parameter, or every combination in `sweep`, at most 8 solves. More than 8 returns `stage` `spec`. A real solve first passes the checklist; a failure returns `stage` `checklist`. A license failure returns `stage` `license` and one next step. Do not start the license service again. `hfss optimize` searches one numeric path, at most 8 times. After a solve, call `hfss advise` and write the advice from those facts.

The WR-90 example is `hfss/examples/wr90.json`. At 10 GHz and a length of 0.03 m, S21 is 0.0 dB and S11 is -64.084 dB. The length search example is `hfss/examples/wr90_length_optimize.json`. The length sweep example is `hfss/examples/wr90_length_sweep.json`.

The rectangular-waveguide backend ships in `hfss/src/hfss_aedt`. `doctor` uses the plugin Python and does not need PyAEDT. A solve needs `import ansys.aedt.core`. If that fails, the error's next step is `pip install pyaedt` (or `pip install -e ".[hfss]"`). Set `HFSS_AEDT_PYTHON` and `HFSS_AEDT_SRC` only to replace that backend. If `stage` is `backend`, follow the error's next step and stop. Do not look for a path from another computer.

`best` is only the best result among the computed runs. If it lies at an end of the interval, say that a wider interval may contain a better point.

Do not close an Electronics Desktop window the user already has open. A source project is copied into `hfss/runs` before it is edited.
