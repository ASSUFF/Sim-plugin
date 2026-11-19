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
6. Run `paper compare`. It writes `comparison.json` and `汇报.md` in the same folder. Report the paper value, the local value, and whether the difference is inside the stated tolerance. Do not call a local result a reproduction of an unstated figure.

`paper status` lists which of paper, targets, spec, result, and comparison are still missing. `paper new`, `paper add`, `paper targets`, `paper spec`, and `paper compare` do not launch a solver.
