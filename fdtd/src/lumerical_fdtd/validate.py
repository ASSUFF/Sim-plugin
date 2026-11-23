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
    "exports",
    "confirmation",
    "frequency_points",
}


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
