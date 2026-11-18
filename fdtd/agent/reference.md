# FDTD spec

Units are SI. Wavelengths, coordinates, and spans are metres. `simulation time` is seconds.

`hide_gui` defaults to true. Set it to false only when the user wants to watch the Lumerical window. On Windows or Linux, prefer forward slashes in path strings.

```json
{
  "name": "soi_straight",
  "hide_gui": true,
  "setup_only": false,
  "project": "C:/sim/device.fsp",
  "global_source": {"wavelength start": 1.5e-6, "wavelength stop": 1.6e-6},
  "simulation": {
    "dimension": "2D",
    "x": 0, "x span": 8e-6,
    "y": 0, "y span": 4e-6,
    "mesh accuracy": 2,
    "simulation time": 5e-13,
    "x min bc": "PML", "x max bc": "PML",
    "y min bc": "PML", "y max bc": "PML"
  },
  "commands": [
    {"op": "addrect", "properties": {
      "name": "core",
      "material": "Si (Silicon) - Palik",
      "x": 0, "x span": 8e-6,
      "y": 0, "y span": 0.5e-6
    }},
    {"op": "addmode", "properties": {
      "name": "source",
      "injection axis": "x-axis",
      "direction": "Forward",
      "x": -3e-6,
      "y": 0, "y span": 2e-6
    }},
    {"op": "addpower", "properties": {
      "name": "transmission",
      "monitor type": "Linear Y",
      "x": 3e-6,
      "y": 0, "y span": 2e-6
    }}
  ],
  "overrides": [
    {"object": "core", "property": "y span", "value": 0.45e-6}
  ],
  "exports": [
    {"name": "T", "kind": "transmission", "monitor": "transmission"},
    {"name": "power", "monitor": "transmission", "result": "T"}
  ]
}
```

`project` opens an existing file. Omit it and `simulation` creates the FDTD region. `commands` call Lumerical verbs such as `addrect`, `addmode`, `addpower`, `addgaussian`, `addprofile`, and `addmesh`. Underscores in property names become spaces.

`overrides` call `setnamed`. `script` or `script_file` is Lumerical script for geometry the structured fields cannot express. `setup_only: true` saves the project and does not solve.

2D simulations lie in the XY plane and use line monitors (`Linear X` or `Linear Y`). 3D monitors include `2D X-normal` and `2D Z-normal`.

Material names must exist in that Lumerical installation. Common names are `Si (Silicon) - Palik`, `SiO2 (Glass) - Palik`, and `Si3N4 (Silicon Nitride) - Luke`.

Results are written to `runs/<timestamp>_<name>/summary.json` under `LUMERICAL_FDTD_RUNS` or the current directory. The same JSON is the last `FDTD_RESULT` line from the engine.
