# Sim-plugin

This is a sim-plugin for Ansys Electronics (HFSS), Lumerical (FDTD), and COMSOL. It started as a personal tool, so there are still rough edges. Suggestions are welcome.

中文说明：[使用说明.md](使用说明.md)

Updated 2026-11-19. Version `v0.2.1119.1`.

The version has four parts, for example `v0.2.1119.1`. The first `0` means it is not a formal release yet. The second part is the major version and changes only for a large update. This update changes it from `1` to `2` because the plugin can now reproduce a paper. The third part is the month and day of the update. The fourth part is the minor version for that day and increases by 1 for a small update.

This folder is a simulation plugin. After you place it anywhere on a computer, an AI can drive the local COMSOL, HFSS, and Lumerical FDTD installations through a command line or MCP: solve with given parameters, change parameters, sweep, pick the best result among the runs that were actually computed, and collect facts for advice.

## Confirm the first task

When the user states a simulation task in full for the first time, do not launch a solver yet. Organize the request into a list and ask the user to confirm it. Keep every condition the user already gave, and fill in settings that are easy to miss but change the result. Mark each item as specified by the user or assumed for this run. Cover at least:

- wavelength or frequency, and bandwidth
- simulation region and boundaries
- geometry and materials
- model detail, and mesh or solver accuracy
- simulation time, adaptive passes, and convergence
- quantities to report; for a sweep or search, also the goal, the value range, and the run limit

Write the items into `confirmation.items`. Each item has `name`, `source`, and `value`. `source` is `specified` or `assumed`. The names are `frequency`, `region`, `geometry`, `material`, `accuracy`, `stop`, and `outputs`. A sweep or search also needs `goal`, `range`, and `limit`. Run `confirm`. It does not launch a solver. The `spec` it returns is what `run`, `sweep`, and `optimize` accept. Do not call those three until the user accepts the list. If the spec changes after that, run `confirm` again. Without it, those commands return `stage` `confirm` and `launched_solver` false.

```text
.venv\Scripts\python.exe -m sim_plugin hfss confirm --spec draft.json
```

Use `comsol` or `fdtd` in place of `hfss` for the other solvers. The shipped examples already contain a confirmation. A later change that only rewords the task, and does not change these settings, does not need another confirmation.

Run every command from the **plugin root**, the directory that contains `pyproject.toml`. Nothing in these instructions depends on a fixed drive letter.

Solver details are in `comsol/使用说明.md`, `hfss/使用说明.md`, and `fdtd/使用说明.md`. Third-party licenses are in `致谢.md`.

`工作记录.md` and `交接.md` are not in the download. After you place the plugin on a computer, write those notes locally from the work done on that computer. Do not reuse paths or acceptance results from another machine.

## 1. Install

Windows is required, plus COMSOL, HFSS, or Lumerical already installed on that computer. Those applications are not included. `doctor` finds them on the computer where the plugin is running.

From the plugin root:

```text
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

These checks do not launch a solver. `ok: true` means the application was found:

```text
.venv\Scripts\python.exe -m sim_plugin comsol doctor
.venv\Scripts\python.exe -m sim_plugin hfss doctor
.venv\Scripts\python.exe -m sim_plugin fdtd doctor
```

The install path in the JSON belongs to that computer. Another machine, or another install folder, produces a different path.

HFSS solving also needs a separate `hfss-aedt` checkout and its Python environment:

```text
HFSS_AEDT_PYTHON  python.exe from that environment
HFSS_AEDT_SRC     the hfss-aedt src directory
```

Both variables are required. When either is missing, or the file it names is not there, an HFSS command returns `stage` `backend` and reports the current value of `HFSS_AEDT_PYTHON` and `HFSS_AEDT_SRC`. The plugin does not use a path from a particular computer. If Lumerical is not in a default location, set `LUMERICAL_ROOT` to the version directory that contains `api/python/lumapi.py`.

## 2. What it can do

| Task | COMSOL | HFSS | Lumerical FDTD |
|---|---|---|---|
| Confirm a spec without solving | `comsol confirm --spec draft.json` | `hfss confirm --spec draft.json` | `fdtd confirm --spec draft.json` |
| See whether it is installed | `comsol doctor` | `hfss doctor` | `fdtd doctor` |
| Check a spec without solving | `validate`, plus `search` | `validate`, plus `prepare` | `validate`, plus `prepare` |
| Inspect an existing project | `comsol inspect --project model.mph` | `hfss inspect --project model.aedt` | `fdtd inspect --project model.fsp` |
| Edit a copy of an existing project | `comsol set --project model.mph --spec changes.json` | `hfss set --project model.aedt --spec changes.json` | `fdtd set --project model.fsp --spec changes.json` |
| Solve with given parameters | `comsol run` | `hfss run` | `fdtd run` |
| Change parameters | edit `value` in the spec and run again | edit the spec and run again | edit the spec or `overrides` and run again |
| Sweep | at most 8 combinations | at most 8 combinations; the older single-parameter form still works | at most 8 combinations; the older single-parameter form still works |
| Pick the best computed point | `best` from a sweep, and `optimize` | `optimize`, at most 8 runs | `optimize`, at most 8 runs |
| Facts for advice | `comsol advise` | `hfss advise` | `fdtd advise` |
| Build a model | look up API names, write Java, validate, compile, and batch-run | describe a waveguide in JSON | describe geometry, sources, and monitors in JSON |

HFSS and FDTD multi-parameter sweeps use a `sweep` object. Each parameter has 2 to 8 values, and the full set of combinations cannot exceed 8. A larger set returns `stage` `spec` and does not launch a solver. The older single `parameter` plus `values` form still works. Before a solve, the same checklist reviews mesh detail, adaptive passes, convergence, simulation time, and the number of frequency points. A failure returns `stage` `checklist`. An install or license failure names exactly one next step.

An existing project is copied into `comsol/runs`, `hfss/runs`, or `fdtd/runs` before it is opened. The original file is left unchanged. `inspect` does not solve. `set` writes the changes only to the copy. To solve an existing COMSOL model, use `run --project` and put the study tag, such as `std1`, in `study`. HFSS `inspect` returns objects and solution setups, not design variables; put the values to change in `variables`.

## Reproduce a paper

Given a request, an AI can find one matching paper and reproduce its COMSOL, HFSS, or FDTD simulation in one folder. The folder holds the paper, the extracted spec, the local results, and the comparison.

`paper new`, `add`, `targets`, `spec`, `status`, and `compare` do not launch a solver. Save only a PDF the user supplied or one that is openly available. Do not bypass a paywall. Confirm the extracted spec before calling the existing solver command. `compare` writes `comparison.json` and `汇报.md` beside the paper. Without a tolerance it records the difference and does not call the results the same.

Results are JSON. The process exits with code 1 when `ok` is false. `best` means the best result among the runs that were computed. When that point is at the end of the interval, a wider interval may contain a better point. The advice text is written by the current AI from the `advise` facts.

## 3. Three ways to call it

1. **Command line.** From the plugin root: `.venv\Scripts\python.exe -m sim_plugin <solver> <command>`.
2. **MCP.** The program is `.venv\Scripts\python.exe` inside the plugin root, with arguments `-m` and `sim_plugin.mcp_server`. After a reload the tools are `comsol_*`, `hfss_*`, and `fdtd_*`. Replace `<plugin-root>` with the real path on that computer. Keep the quotes when the path contains spaces:

```json
{
  "mcpServers": {
    "sim-plugin": {
      "command": "<plugin-root>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "sim_plugin.mcp_server"]
    }
  }
}
```

3. **Skills.** `comsol/agent/SKILL.md`, `hfss/agent/SKILL.md`, and `fdtd/agent/SKILL.md`, also copied under `.cursor/skills/` and `.agents/skills/`. A skill says when to call, which units to use, and what not to do.

## 4. Commands

Every command prints JSON.

| Solver | Command | What it does | Launches the solver |
|---|---|---|---|
| COMSOL | `comsol doctor` | Find the install | No |
| | `comsol search KEYWORD --limit 20` | Find Java `create` type names | No |
| | `comsol validate --java X.java --spec X.json` | Check a script and spec | No |
| | `comsol run --java X.java --spec X.json --stoptime 180` | Solve | Yes |
| | `comsol sweep --java X.java --spec X.json` | Every combination in the spec, at most 8 | Yes |
| | `comsol optimize --java X.java --spec X.json` | Coarse-to-fine search, at most 8 | Yes |
| | `comsol advise --report REPORT.json` | List facts for advice | No |
| HFSS | `hfss doctor` / `validate` / `prepare` | Find, check, or fill defaults | No |
| | `hfss run --spec X.json` | Solve | Yes |
| | `hfss sweep --spec X.json` | at most 8 combinations | Yes |
| | `hfss optimize --spec X.json` | One numeric path, at most 8 | Yes |
| | `hfss advise --report REPORT.json` | List facts for advice | No |
| FDTD | `fdtd doctor` / `validate` / `prepare` | Find, check, or fill defaults | No |
| | `fdtd run` / `sweep` / `optimize` | Solve, sweep one property, or search at most 8 times | Yes, when installed |
| | `fdtd advise --report REPORT.json` | List facts for advice | No |

## 5. Examples

Run these from the plugin root.

COMSOL plate: 300 K on the left, 400 K on the right, the other two edges insulated. Expect `T_avg_K=350`, `T_max_K=400`, and `T_min_K=300`.

```text
.venv\Scripts\python.exe -m sim_plugin comsol run --java comsol\examples\SteadyHeat.java --spec comsol\examples\steady_heat.json --stoptime 180
```

To sweep, add `"sweep"` and `"goal"` to the spec, run `sweep`, then pass the returned `report` to `advise`.

HFSS WR-90 at 10 GHz and a length of 0.03 m has S21 near 0 dB and S11 near -64.084 dB.

```text
.venv\Scripts\python.exe -m sim_plugin hfss run --spec hfss\examples\wr90.json
.venv\Scripts\python.exe -m sim_plugin hfss sweep --spec hfss\examples\wr90_length_sweep.json
.venv\Scripts\python.exe -m sim_plugin hfss optimize --spec hfss\examples\wr90_length_optimize.json
```

FDTD examples are under `fdtd/examples/`. Lengths are metres and times are seconds.

```text
.venv\Scripts\python.exe -m sim_plugin fdtd run --spec fdtd\examples\smoke_2d.json
.venv\Scripts\python.exe -m sim_plugin fdtd sweep --spec fdtd\examples\sweep_wg_width.json
```

## 6. How to read a result

Look at `ok`, `launched_solver`, `work_dir` or `run_dir`, `results`, `rows`, `best`, `assumptions`, `note`, and `report`. Sweeps and searches for all three solvers use `rows` and `best`. `best` is one of those rows. `assumptions` lists the checklist items marked `assumed`, and that list is saved in the run report.

1. `best` is only the best result among the computed runs. Repeat `note` when it is present.
2. A single solve is not an optimum. `advise` says so.
3. More than 8 sweep or optimize runs are rejected before the solver starts.

## 7. Boundaries

- A source project is copied into `comsol/runs`, `hfss/runs`, or `fdtd/runs`. Only the copy is edited.
- Run one solver command at a time.
- Do not close a COMSOL, Electronics Desktop, or Lumerical window the user already has open.
- Do not point a run directory at the user's other project folders.
- `HFSS_PROTECTED_PROJECT` names one project that must not be opened or copied. When it is unset, the plugin still refuses the protected project path used during development.
- Without Lumerical, `fdtd run` returns `stage=install`.
- When the HFSS license port `1055@localhost` is closed, `hfss run` returns `stage=license`. Do not restart the license service repeatedly.
- An FDTD transmission slightly above 1 is a normalized numeric result.

## 8. If something fails

| What you see | Check first |
|---|---|
| `doctor` has `ok: false` | Whether the application is installed. COMSOL uses the registry, HFSS uses `ANSYSEM_ROOT242`, and FDTD uses `LUMERICAL_ROOT` |
| HFSS cannot find its backend interpreter | Set `HFSS_AEDT_PYTHON` and `HFSS_AEDT_SRC` |
| `stage` is `license` | Whether the license port is open |
| Too many combinations | Use fewer values. The limit is 8 |
| An AI tool cannot see the tools | Reload MCP and point the interpreter at this plugin's `.venv` |
