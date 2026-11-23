"""Check an HFSS spec without launching Electronics Desktop."""

import json
import sys
from pathlib import Path

KNOWN = {
    "name",
    "hide_gui",
    "setup_only",
    "version",
    "project",
    "design",
    "solution_type",
    "frequency_hz",
    "max_passes",
    "max_delta_s",
    "run_root",
    "geometry",
    "variables",
}
SOLUTION_TYPES = {"Modal", "Terminal", "Eigenmode"}
GEOM_KEYS = {"kind", "a_m", "b_m", "length_m", "material"}


def _positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate_spec(spec):
    errors = []
    warnings = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"], warnings
    for key in sorted(set(spec) - KNOWN):
        warnings.append("ignored unknown field: %s" % key)
    if "hide_gui" in spec and not isinstance(spec["hide_gui"], bool):
        errors.append("hide_gui must be a boolean")
    if "setup_only" in spec and not isinstance(spec["setup_only"], bool):
        errors.append("setup_only must be a boolean")
    for key in ("name", "version", "project", "design", "run_root"):
        if key in spec and not isinstance(spec[key], str):
            errors.append("%s must be a string" % key)
    if "solution_type" in spec and spec["solution_type"] not in SOLUTION_TYPES:
        errors.append("solution_type must be Modal, Terminal, or Eigenmode")
    if "frequency_hz" in spec and not _positive(spec["frequency_hz"]):
        errors.append("frequency_hz must be a positive number in hertz")
    if "max_passes" in spec:
        value = spec["max_passes"]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
            errors.append("max_passes must be an integer from 1 to 20")
    if "max_delta_s" in spec and not _positive(spec["max_delta_s"]):
        errors.append("max_delta_s must be a positive number")
    if "variables" in spec and not isinstance(spec["variables"], dict):
        errors.append("variables must be an object of HFSS variable names")
    geometry = spec.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append("geometry must be an object")
        else:
            for key in sorted(set(geometry) - GEOM_KEYS):
                warnings.append("ignored unknown geometry field: %s" % key)
            if geometry.get("kind") != "rectangular_waveguide":
                errors.append("geometry.kind must be rectangular_waveguide")
            for key in ("a_m", "b_m", "length_m"):
                if not _positive(geometry.get(key)):
                    errors.append("geometry.%s must be a positive length in metres" % key)
            if "material" in geometry and not isinstance(geometry["material"], str):
                errors.append("geometry.material must be a string")
            if _positive(geometry.get("a_m")) and _positive(geometry.get("b_m")):
                if geometry["a_m"] < geometry["b_m"]:
                    warnings.append("geometry.a_m is smaller than b_m; TE10 uses a as the broad wall")
            if _positive(geometry.get("frequency_hz", spec.get("frequency_hz"))) and _positive(geometry.get("a_m")):
                cutoff = 3.0e8 / (2.0 * geometry["a_m"])
                freq = spec.get("frequency_hz")
                if _positive(freq) and freq <= cutoff:
                    warnings.append("frequency_hz is below the TE10 cutoff of %.3g Hz" % cutoff)
    if not spec.get("project") and geometry is None:
        errors.append("spec needs a project path or rectangular_waveguide geometry")
    if geometry is not None and "frequency_hz" not in spec and not spec.get("setup_only"):
        errors.append("frequency_hz is required to solve a new waveguide")
    return errors, warnings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m hfss_aedt.validate SPEC.json", file=sys.stderr)
        return 2
    try:
        spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    errors, warnings = validate_spec(spec)
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
