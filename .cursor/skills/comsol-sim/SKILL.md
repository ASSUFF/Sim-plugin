---
name: comsol-sim
description: >
  Drive the local COMSOL installation: build a model, solve, sweep, and
  optimize. Use when the user mentions COMSOL, an .mph file, heat transfer,
  a parameter sweep, optimization, or simulation advice.
---

# COMSOL

The working directory is the plugin root, the folder that contains `pyproject.toml`. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. If `comsol_doctor`, `comsol_search`, `comsol_validate`, `comsol_run`, `comsol_sweep`, `comsol_optimize`, and `comsol_advise` are already available, call those tools. Their arguments match the commands below.

## New model

1. Call `comsol doctor`. Stop when no installation is found.
2. Before writing Java, use `comsol search KEYWORD` for `create` type names. Use the returned `create_type`. A hash in the completion data is not a Java property name.
3. The Java file has one public class, and the class name matches the file name. Call `ModelUtil.initStandalone`. A swept parameter is `model.param().set("name", "value-with-unit")`. After the solve, print one line `===RESULT===`, then one `name=number` per line. Call `model.save`. Do not use `Runtime.getRuntime`, `ProcessBuilder`, or reflection.
4. Run `comsol validate --java FILE --spec SPEC.json`. Fix the script when `errors` is not empty.
5. Run `comsol run`. Values in `parameters.*.value` are written into the run copy. The source file the user supplied stays unchanged.

The steady plate example is `comsol/examples/SteadyHeat.java`. `T_cold` is on the left, `T_hot` is on the right, and the other two edges are insulated. With a constant conductivity the area-average temperature is the arithmetic mean. For `T_cold=300[K]` and `T_hot=400[K]`, `T_avg_K` is 350, `T_max_K` is 400, and `T_min_K` is 300.

The optical-heating example is `comsol/examples/OptoHeat.java`.

## Sweep and optimize

- `comsol sweep` runs every combination in `sweep`. Each parameter has 2 to 8 values, and the total number of combinations is at most 8.
- `comsol optimize` searches one parameter from coarse to fine. `optimize.max_runs` is 2 to 8.
- The goal value is numeric. `goal.sense` is `min` or `max`.
- Tell the user that `best` is only the best computed run. Include `note` when it is present. If the best point is at an end of the interval, say that a wider interval may contain a better point.

## Advice

After a solve, sweep, or search, call `comsol advise --report REPORT.json`. Write the advice from `facts`. A single solve is not an optimum.

## Do not

- Do not write run directories into the user's other project folders.
- Do not close a COMSOL window the user already has open.
- Above 8 runs, stop and let the user decide. The plugin rejects the spec before launching COMSOL.
