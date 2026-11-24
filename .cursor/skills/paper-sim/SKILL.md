---
name: paper-sim
description: >
  Find one paper that matches a simulation request and reproduce its
  simulation with COMSOL, HFSS, or Lumerical FDTD. Use when the user asks to
  find a paper, reproduce a paper, compare simulation results with a paper,
  or mentions 论文, 复现, or a literature search for a solver.
---

# Reproduce a paper

The working directory is the plugin root. On Windows the command is `.venv\Scripts\python.exe -m sim_plugin`. This workflow does not launch a solver until the user confirms the extracted setup.

1. Create one folder for the whole case: `paper new --folder FOLDER --solver comsol|hfss|fdtd --request TEXT`.
2. Search public literature for one paper that matches the request and the chosen solver. Save an openly available PDF, or a PDF the user supplied, with `paper add`. If the PDF is not legally available, save the citation only and ask the user for the file. Do not bypass a paywall.
3. Read the paper and write the simulation parameters into a spec the existing solver command accepts. Also write the numerical results stated by the paper into `targets.json`.
4. Show the extracted geometry, materials, frequency or wavelength, boundaries, mesh or solver settings, and the paper's reported numbers. Mark each item as specified by the paper or assumed. Run `confirm` and wait for the user. Then save that spec with `paper spec`.
5. Run the confirmed spec with the existing `comsol`, `hfss`, or `fdtd` command. Keep the solver output, and also copy the numbers needed for comparison into the case folder.
6. Run `paper map` to write `对照.json`, then `paper compare`. Compare writes `comparison.json` and `汇报.md` in the same folder. Without `--map`, compare uses `对照.json` or the solver's default path. `[middle]` selects the middle sample and `[5]` selects a numbered sample. An interval is printed as `min–max`, and a missing value is `—`. Report the paper value, the local value, and whether the difference is inside the stated tolerance. Do not call a local result a reproduction of an unstated figure. HFSS examples in this workflow are straight rectangular waveguides. The backend does not build a CPW or return Neff or Z0.

`paper status` lists which of paper, targets, spec, result, and comparison are still missing. `paper new`, `paper add`, `paper targets`, `paper spec`, `paper map`, and `paper compare` do not launch a solver.
