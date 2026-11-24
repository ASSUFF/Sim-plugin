"""Check a simulation spec without launching Lumerical."""

import json
import re
import sys
from pathlib import Path

OP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KNOWN = {
    "name",
    "hide_gui",
    "setup_only",
    "project",
    "run_root",
    "global_source",
    "simulation",
    "commands",
    "overrides",
    "script",
    "script_file",
    "script_assignments",
    "exports",
    "confirmation",
    "frequency_points",
}
_PLACE = {"name", "x", "y", "z", "x span", "y span", "z span", "x min", "x max", "y min", "y max", "z min", "z max"}
_STRUCTURE = _PLACE | {
    "material",
    "override mesh order from material database",
    "mesh order",
    "vertices",
    "first axis",
    "rotation 1",
    "rotation 2",
    "rotation 3",
}
_MONITOR = _PLACE | {
    "monitor type",
    "override global monitor settings",
    "use source limits",
    "use wavelength spacing",
    "frequency points",
    "wavelength center",
    "wavelength span",
}
_INDEX = _PLACE | {
    "spatial interpolation",
    "override global monitor settings",
    "use source limits",
    "use wavelength spacing",
    "frequency points",
    "wavelength center",
    "wavelength span",
}
_MESH = _PLACE | {
    "override x mesh",
    "override y mesh",
    "override z mesh",
    "dx",
    "dy",
    "dz",
    "set maximum mesh step",
    "set minimum mesh step",
    "equivalent x index",
    "equivalent y index",
    "equivalent z index",
    "override mesh order from material database",
}
_SOURCE = _PLACE | {"injection axis", "direction", "mode selection", "amplitude", "phase"}
_FDTD = _PLACE | {
    "dimension",
    "mesh accuracy",
    "simulation time",
    "auto shutoff min",
    "background material",
    "mesh type",
    "x min bc",
    "x max bc",
    "y min bc",
    "y max bc",
    "z min bc",
    "z max bc",
}
_OBJECT_PROPS = {
    "addrect": _STRUCTURE,
    "addpoly": _STRUCTURE,
    "addcircle": _STRUCTURE,
    "addring": _STRUCTURE,
    "addtriangle": _STRUCTURE,
    "addpyramid": _STRUCTURE,
    "addpower": _MONITOR,
    "addprofile": _MONITOR,
    "addtime": _MONITOR,
    "adddftmonitor": _MONITOR,
    "addmodeexpansion": _MONITOR | {"mode selection"},
    "addindex": _INDEX,
    "addmesh": _MESH,
    "addmode": _SOURCE,
    "adddipole": _SOURCE,
    "addplane": _SOURCE,
    "addgaussian": _SOURCE,
    "addtfsf": _SOURCE,
    "addfdtd": _FDTD,
    "fdtd": _FDTD,
}
_MONITOR_TYPES = {
    "point",
    "linear x",
    "linear y",
    "linear z",
    "2d x-normal",
    "2d y-normal",
    "2d z-normal",
    "3d",
}
_SET_RE = re.compile(r"""set\(\s*["']([^"']+)["']\s*(?:,\s*["']([^"']*)["'])?""", re.IGNORECASE)
_ADD_RE = re.compile(r"\b(add[a-z0-9]+)\b", re.IGNORECASE)
_SELECT_RE = re.compile(r"""select\(\s*["']([^"']+)["']\s*\)""", re.IGNORECASE)


def _property_problem(kind, prop, value=None):
    allowed = _OBJECT_PROPS.get(kind)
    if allowed is None:
        return None
    if prop.lower() not in allowed:
        return "%s 没有属性 %s。" % (kind, prop)
    if prop.lower() == "monitor type" and isinstance(value, str) and value.strip():
        if value.strip().lower() not in _MONITOR_TYPES:
            return (
                "monitor type 不能是 %s。可用 Point、Linear X、Linear Y、Linear Z、"
                "2D X-normal、2D Y-normal、2D Z-normal、3D。"
            ) % value
    return None


def script_property_problems(script):
    """Return errors and warnings for set() calls that follow a known add*."""
    errors = []
    warnings = []
    kind = None
    unknown = set()
    if not isinstance(script, str):
        return errors, warnings
    for raw in script.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        selected = _SELECT_RE.search(line)
        if selected:
            kind = "fdtd" if selected.group(1).lower() == "fdtd" else None
        added = _ADD_RE.search(line)
        if added:
            kind = added.group(1).lower()
            if kind not in _OBJECT_PROPS:
                unknown.add(kind)
                kind = None
        found = _SET_RE.search(line)
        if not found or kind is None:
            continue
        problem = _property_problem(kind, found.group(1), found.group(2))
        if problem:
            errors.append(problem)
    for name in sorted(unknown):
        warnings.append("脚本里的 %s 不在属性表中，未检查它后面的 set。" % name)
    return errors, warnings


def _material_spelling(material):
    exact = "<Object defined dielectric>"
    if not isinstance(material, str):
        return None
    if material == exact:
        return None
    if material.lower() == exact.lower():
        return "对象介质的名称必须是 %s。大小写不同会让 Lumerical 卡住。" % exact
    return None


def safe_identifier(value, label):
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ValueError("%s must be a Lumerical identifier" % label)
    return value


def validate_spec(spec):
    errors = []
    warnings = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"], warnings
    for key in sorted(set(spec) - KNOWN):
        warnings.append("ignored unknown field: %s" % key)
    for key in ("hide_gui", "setup_only"):
        if key in spec and not isinstance(spec[key], bool):
            errors.append("%s must be a boolean" % key)
    if "name" in spec and (not isinstance(spec["name"], str) or not spec["name"].strip()):
        errors.append("name must be a non-empty string")
    for key in ("project", "run_root", "script", "script_file"):
        if key in spec and not isinstance(spec[key], str):
            errors.append("%s must be a string" % key)
    if "global_source" in spec:
        source = spec["global_source"]
        if not isinstance(source, dict):
            errors.append("global_source must be an object of numbers in metres")
        else:
            for key, value in source.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append("global_source.%s must be a number in metres" % key)
                elif value <= 0:
                    errors.append("global_source.%s must be positive" % key)
    if "simulation" in spec and not isinstance(spec["simulation"], dict):
        errors.append("simulation must be an object")
    elif isinstance(spec.get("simulation"), dict):
        for key, value in spec["simulation"].items():
            problem = _property_problem("fdtd", key, value if isinstance(value, str) else None)
            if problem:
                errors.append("simulation.%s: %s" % (key, problem))
    if "frequency_points" in spec:
        points = spec["frequency_points"]
        if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 2001:
            errors.append("frequency_points must be an integer from 2 to 2001")
    commands = spec.get("commands") or []
    if "commands" in spec and not isinstance(commands, list):
        errors.append("commands must be an array")
        commands = []
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            errors.append("commands[%d] must be an object" % index)
            continue
        op = command.get("op") or command.get("command")
        if not isinstance(op, str) or not OP_RE.match(op):
            errors.append("commands[%d].op must be a Lumerical add* name" % index)
        if "properties" in command and not isinstance(command["properties"], dict):
            errors.append("commands[%d].properties must be an object" % index)
        elif isinstance(command.get("properties"), dict):
            material_error = _material_spelling(command["properties"].get("material"))
            if material_error:
                errors.append("commands[%d].properties.material: %s" % (index, material_error))
            if isinstance(op, str) and OP_RE.match(op):
                if op.lower() not in _OBJECT_PROPS:
                    warnings.append("commands[%d] 的 %s 不在属性表中，未检查属性。" % (index, op))
                for key, value in command["properties"].items():
                    problem = _property_problem(op.lower(), key, value if isinstance(value, str) else None)
                    if problem:
                        errors.append("commands[%d].properties.%s: %s" % (index, key, problem))
    overrides = spec.get("overrides") or []
    if "overrides" in spec and not isinstance(overrides, list):
        errors.append("overrides must be an array")
        overrides = []
    for index, item in enumerate(overrides):
        if not isinstance(item, dict):
            errors.append("overrides[%d] must be an object" % index)
            continue
        for key in ("object", "property"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append("overrides[%d].%s must be a string" % (index, key))
        if "value" not in item:
            errors.append("overrides[%d].value is required" % index)
    exports = spec.get("exports") or []
    if "exports" in spec and not isinstance(exports, list):
        errors.append("exports must be an array")
        exports = []
    for index, item in enumerate(exports):
        if not isinstance(item, dict):
            errors.append("exports[%d] must be an object" % index)
            continue
        kind = item.get("kind", "result")
        if kind not in ("transmission", "result"):
            errors.append("exports[%d].kind must be transmission or result" % index)
        if not isinstance(item.get("monitor"), str) or not NAME_RE.match(item.get("monitor", "")):
            errors.append("exports[%d].monitor must be a Lumerical identifier" % index)
        if "name" in item and (not isinstance(item["name"], str) or not NAME_RE.match(item["name"])):
            errors.append("exports[%d].name must be a Lumerical identifier" % index)
        if kind == "result" and "result" in item and not isinstance(item["result"], str):
            errors.append("exports[%d].result must be a string" % index)
    script_text = spec.get("script") if isinstance(spec.get("script"), str) else ""
    script_errors, script_warnings = script_property_problems(script_text)
    errors.extend(script_errors)
    warnings.extend(script_warnings)
    script_file = spec.get("script_file")
    if isinstance(script_file, str) and script_file.strip():
        path = Path(script_file)
        if path.is_file():
            file_errors, file_warnings = script_property_problems(path.read_text(encoding="utf-8"))
            errors.extend(file_errors)
            warnings.extend(file_warnings)
        else:
            warnings.append("script_file 当前读不到，属性白名单未检查这份脚本。")
    has_work = any(spec.get(key) for key in ("project", "simulation", "commands", "script", "script_file"))
    if not has_work:
        errors.append("spec needs a project, simulation, commands, script, or script_file")
    return errors, warnings


def load_spec(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m lumerical_fdtd.validate SPEC.json", file=sys.stderr)
        return 2
    try:
        spec = load_spec(argv[0])
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    errors, warnings = validate_spec(spec)
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
