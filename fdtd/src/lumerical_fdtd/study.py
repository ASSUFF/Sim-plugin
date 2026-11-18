"""Fill missing FDTD inputs and compare one parameter."""

import copy


def prepare_spec(spec):
    """Fill documented defaults. Geometry that was never described stays missing."""
    completed = copy.deepcopy(spec if isinstance(spec, dict) else {})
    assumptions = []
    if "hide_gui" not in completed:
        completed["hide_gui"] = True
        assumptions.append("hide_gui=true: run without showing the Lumerical window")
    source = completed.setdefault("global_source", {})
    if isinstance(source, dict) and "wavelength start" not in source and "wavelength_start" not in source:
        source["wavelength start"] = 1.55e-6
        source["wavelength stop"] = 1.55e-6
        assumptions.append("wavelength=1550 nm, used when no wavelength was given")
    simulation = completed.get("simulation")
    if not isinstance(simulation, dict):
        simulation = {}
        completed["simulation"] = simulation
        assumptions.append("simulation region=8 um by 4 um, 2D, because no region was given")
    if "dimension" not in simulation:
        simulation["dimension"] = "3D" if "z span" in simulation or "z_span" in simulation else "2D"
        assumptions.append("dimension=%s" % simulation["dimension"])
    if "mesh accuracy" not in simulation and "mesh_accuracy" not in simulation:
        simulation["mesh accuracy"] = 2
        assumptions.append("mesh accuracy=2")
    if "simulation time" not in simulation and "simulation_time" not in simulation:
        simulation["simulation time"] = 1.0e-12
        assumptions.append("simulation time=1 ps")
    for axis, span in (("x", 8e-6), ("y", 4e-6)):
        if axis not in simulation and "%s span" % axis not in simulation:
            simulation[axis] = 0
            simulation["%s span" % axis] = span
    for edge in ("x min bc", "x max bc", "y min bc", "y max bc"):
        if edge not in simulation:
            simulation[edge] = "PML"
    if simulation.get("dimension") == "3D":
        for edge in ("z min bc", "z max bc"):
            if edge not in simulation:
                simulation[edge] = "PML"
    for command in completed.get("commands") or []:
        if not isinstance(command, dict):
            continue
        properties = command.setdefault("properties", {})
        op = command.get("op") or command.get("command")
        if op in ("addrect", "addpoly", "addcircle") and "material" not in properties:
            properties["material"] = "Si (Silicon) - Palik"
            assumptions.append("material=Si (Silicon) - Palik on %s" % (properties.get("name") or op))
    return completed, assumptions


def validate_study(study):
    errors = []
    if not isinstance(study, dict):
        return ["study must be a JSON object"]
    if not isinstance(study.get("base"), dict):
        errors.append("base must be a simulation spec")
    parameter = study.get("parameter")
    if not isinstance(parameter, dict):
        errors.append("parameter must name an object and a property")
    else:
        if not isinstance(parameter.get("object"), str) or not parameter["object"].strip():
            errors.append("parameter.object is required")
        if not isinstance(parameter.get("property"), str) or not parameter["property"].strip():
            errors.append("parameter.property is required")
    values = study.get("values")
    if not isinstance(values, list) or not 2 <= len(values) <= 8:
        errors.append("values must contain 2 to 8 numbers")
    metric = study.get("metric") or {}
    if metric.get("goal", "max") not in ("max", "min"):
        errors.append("metric.goal must be max or min")
    return errors


def series(field):
    if not isinstance(field, dict):
        return None
    if "values" in field:
        return field["values"]
    if "real" in field:
        return field["real"]
    return None


def score_fdtd_payload(payload, metric):
    export_name = (metric or {}).get("export", "T")
    target = (metric or {}).get("wavelength_m")
    for item in payload.get("exports") or []:
        if item.get("name") != export_name:
            continue
        data = item.get("data") or {}
        fields = data.get("fields") or {}
        wavelengths = series(fields.get("lambda"))
        values = series(fields.get("T")) or series(fields.get("value")) or series(data.get("array"))
        if not values:
            return None
        if wavelengths and target is not None and len(wavelengths) == len(values):
            pair = min(zip(wavelengths, values), key=lambda sample: abs(sample[0] - target))
            return float(pair[1])
        return float(values[len(values) // 2])
    return None


def choose_best(points, goal):
    usable = [point for point in points if isinstance(point.get("score"), (int, float)) and not isinstance(point.get("score"), bool)]
    if not usable:
        return None
    if goal == "min":
        return min(usable, key=lambda point: point["score"])
    return max(usable, key=lambda point: point["score"])
