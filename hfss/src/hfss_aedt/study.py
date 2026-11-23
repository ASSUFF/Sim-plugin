"""Fill missing HFSS inputs and compare one parameter."""

import copy


WR90 = {"a_m": 0.02286, "b_m": 0.01016, "length_m": 0.03}


def prepare_spec(spec):
    completed = copy.deepcopy(spec if isinstance(spec, dict) else {})
    assumptions = []
    if "hide_gui" not in completed:
        completed["hide_gui"] = True
        assumptions.append("hide_gui=true: Electronics Desktop stays in the background")
    if "solution_type" not in completed:
        completed["solution_type"] = "Modal"
        assumptions.append("solution_type=Modal")
    if "max_passes" not in completed:
        completed["max_passes"] = 4
        assumptions.append("max_passes=4")
    if "max_delta_s" not in completed:
        completed["max_delta_s"] = 0.02
        assumptions.append("max_delta_s=0.02")
    if not completed.get("project"):
        geometry = completed.get("geometry")
        if not isinstance(geometry, dict):
            geometry = {"kind": "rectangular_waveguide"}
            completed["geometry"] = geometry
            assumptions.append("geometry=WR-90 rectangular waveguide, because no project or geometry was given")
        geometry.setdefault("kind", "rectangular_waveguide")
        for key, value in WR90.items():
            if key not in geometry:
                geometry[key] = value
                assumptions.append("%s=%s m, WR-90 default" % (key, value))
        if "material" not in geometry:
            geometry["material"] = "vacuum"
            assumptions.append("material=vacuum")
        if "frequency_hz" not in completed:
            completed["frequency_hz"] = 1.0e10
            assumptions.append("frequency=10 GHz, above the WR-90 TE10 cutoff")
    return completed, assumptions


def validate_study(study):
    errors = []
    if not isinstance(study, dict):
        return ["study must be a JSON object"]
    if not isinstance(study.get("base"), dict):
        errors.append("base must be a simulation spec")
    parameter = study.get("parameter") or {}
    has_path = isinstance(parameter.get("path"), str) and parameter["path"].strip()
    has_variable = isinstance(parameter.get("variable"), str) and parameter["variable"].strip()
    if not has_path and not has_variable:
        errors.append("parameter.path or parameter.variable is required")
    values = study.get("values")
    if not isinstance(values, list) or not 2 <= len(values) <= 8:
        errors.append("values must contain 2 to 8 entries")
    if (study.get("metric") or {}).get("goal", "max") not in ("max", "min"):
        errors.append("metric.goal must be max or min")
    return errors


def score_hfss_payload(payload, metric):
    key = (metric or {}).get("key", "dB(S(P2,P1))")
    data = payload.get("s_db") or {}
    value = data.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def choose_best(points, goal):
    usable = [point for point in points if isinstance(point.get("score"), (int, float)) and not isinstance(point.get("score"), bool)]
    if not usable:
        return None
    if goal == "min":
        return min(usable, key=lambda point: point["score"])
    return max(usable, key=lambda point: point["score"])


def assign_path(spec, path, value):
    node = spec
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("parameter.path is empty")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value
