"""Drive a local Ansys Lumerical FDTD install.

This file stays importable on Lumerical's bundled Python. lumapi is imported
only when a simulation actually starts.
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lumerical_fdtd.discover import find_install, runs_dir
from lumerical_fdtd.study import choose_best, score_fdtd_payload, validate_study
from lumerical_fdtd.validate import safe_identifier, validate_spec

_np = None
_lumapi = None

SOLVER_PROPS = (
    "dimension",
    "x",
    "y",
    "z",
    "x span",
    "y span",
    "z span",
    "mesh accuracy",
    "simulation time",
    "x min bc",
    "x max bc",
    "y min bc",
    "y max bc",
    "z min bc",
    "z max bc",
)
OBJECT_PROPS = (
    "material",
    "x",
    "y",
    "z",
    "x span",
    "y span",
    "z span",
    "monitor type",
    "injection axis",
    "direction",
)


def bootstrap():
    global _np, _lumapi
    if _lumapi is not None:
        return
    install = find_install()
    os.environ["PATH"] = str(install.bin_dir) + os.pathsep + os.environ.get("PATH", "")
    sys.path.insert(0, str(install.api_dir))
    import numpy
    import lumapi

    _np = numpy
    _lumapi = lumapi


def plain(value):
    if isinstance(value, _np.ndarray):
        if value.size == 1:
            return plain(value.reshape(-1)[0])
        if value.size > 64:
            return {"type": "ndarray", "shape": list(value.shape), "dtype": str(value.dtype)}
        return value.tolist()
    if isinstance(value, _np.floating):
        return float(value)
    if isinstance(value, _np.integer):
        return int(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def prop_name(key):
    key = str(key)
    if " " in key:
        return key
    return key.replace("_", " ")


def try_get(session, prop):
    try:
        return plain(session.get(prop))
    except Exception:
        return None


def list_objects(session):
    try:
        session.groupscope("::model")
    except Exception:
        pass
    try:
        session.selectall()
        raw = session.getid()
    except Exception as exc:
        if "no items are currently selected" in str(exc):
            return []
        return [{"error": str(exc)}]
    ids = [line.strip() for line in str(raw).splitlines() if line.strip()]
    items = []
    for oid in ids[:80]:
        try:
            session.select(oid)
        except Exception as exc:
            items.append({"id": oid, "error": str(exc)})
            continue
        item = {"id": oid, "name": try_get(session, "name"), "type": try_get(session, "type")}
        for prop in OBJECT_PROPS:
            value = try_get(session, prop)
            if value is not None:
                item[prop] = value
        items.append(item)
    if len(ids) > 80:
        items.append({"truncated": len(ids) - 80})
    return items


def solver_settings(session, objects):
    target = None
    for item in objects:
        if item.get("type") == "FDTD" or item.get("name") == "FDTD":
            target = item.get("id") or item.get("name")
            break
    if target is None:
        return None
    session.select(target)
    settings = {}
    for prop in SOLVER_PROPS:
        value = try_get(session, prop)
        if value is not None:
            settings[prop] = value
    try:
        settings["wavelength start"] = plain(session.getglobalsource("wavelength start"))
        settings["wavelength stop"] = plain(session.getglobalsource("wavelength stop"))
    except Exception:
        pass
    return settings


def apply_properties(session, properties):
    for key, value in properties.items():
        if key in ("op", "command"):
            continue
        session.set(prop_name(key), value)


def add_commands(session, commands):
    for command in commands:
        op = command.get("op") or command.get("command")
        getattr(session, op)()
        apply_properties(session, command.get("properties") or {})


def apply_overrides(session, overrides):
    for item in overrides:
        index = item.get("index")
        if index is None:
            session.setnamed(item["object"], prop_name(item["property"]), item["value"])
        else:
            session.setnamed(item["object"], prop_name(item["property"]), item["value"], index)


def _scalar(data):
    """Read a single transmission number. Leave arrays and datasets to the caller."""
    if isinstance(data, dict) or hasattr(data, "shape"):
        return None
    if isinstance(data, bool):
        return None
    if isinstance(data, (int, float)):
        return float(data)
    if isinstance(data, str):
        try:
            return float(data.strip())
        except ValueError:
            return None
    try:
        return float(data)
    except (TypeError, ValueError):
        return None


def _numbered_script(script):
    return "\n".join("%4d | %s" % (index, line) for index, line in enumerate(script.splitlines(), 1))


class ScriptError(Exception):
    """One Lumerical statement failed. index and line are 1-based."""

    def __init__(self, index, line, text, cause):
        self.index = index
        self.line = line
        self.text = text
        self.cause = cause
        super().__init__(str(cause))


def script_statements(script):
    """Split a Lumerical script into statements.

    A statement ends at ';' or a newline when parentheses, brackets, and braces
    are balanced and the cursor is outside a string or comment. A for/if block
    in braces stays one statement. Returns {"text", "line"} with a 1-based line.
    """
    statements = []
    buf = []
    start_line = 1
    line = 1
    depth_paren = 0
    depth_brack = 0
    depth_brace = 0
    quote = None
    started = False
    i = 0
    length = len(script)

    def flush():
        nonlocal buf, started
        text = "".join(buf).strip()
        buf = []
        started = False
        if text:
            statements.append({"text": text, "line": start_line})

    while i < length:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < length else ""
        if quote:
            buf.append(ch)
            if ch == "\\" and nxt:
                buf.append(nxt)
                if nxt == "\n":
                    line += 1
                i += 2
                continue
            if ch == "\n":
                line += 1
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "#":
            while i < length and script[i] != "\n":
                i += 1
            continue
        if ch in ("'", '"'):
            if not started:
                start_line = line
                started = True
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "[":
            depth_brack += 1
        elif ch == "]":
            depth_brack = max(0, depth_brack - 1)
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        balanced = depth_paren == 0 and depth_brack == 0 and depth_brace == 0
        if not started and ch not in " \t\r\n":
            start_line = line
            started = True
        if ch == ";" and balanced:
            buf.append(ch)
            flush()
            i += 1
            continue
        if ch == "\n":
            line += 1
            if balanced:
                flush()
            else:
                buf.append(ch)
            i += 1
            continue
        if ch != "\r":
            buf.append(ch)
        i += 1
    flush()
    return statements


def flatten_matrix_literals(text):
    """Join a multiline [ ... ] literal onto one line. Semicolons inside stay."""
    out = []
    depth = 0
    quote = None
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < length else ""
        if quote:
            out.append(ch)
            if ch == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
        if depth and ch in "\r\n":
            if out and out[-1] not in " \t":
                out.append(" ")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def eval_script(session, script):
    """Run each statement. A matrix literal is one line before it is sent."""
    for index, item in enumerate(script_statements(script), 1):
        text = flatten_matrix_literals(item["text"]).strip()
        if not text:
            continue
        try:
            session.eval(text)
        except Exception as exc:
            raise ScriptError(index, item["line"], text, exc) from exc


def _write_curve_csv(path, array):
    import csv

    flat = array.reshape(-1)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if _np.iscomplexobj(array):
            writer.writerow(["index", "real", "imag"])
            for index, value in enumerate(flat):
                writer.writerow([index, float(value.real), float(value.imag)])
        else:
            writer.writerow(["index", "value"])
            for index, value in enumerate(flat):
                writer.writerow([index, float(value)])
    return str(path)


def store_dataset(data, folder, stem):
    folder.mkdir(parents=True, exist_ok=True)
    summary = {"stem": stem}

    def save_array(key, array):
        array = _np.asarray(array)
        if array.dtype == object:
            return {"skipped": "non-numeric"}
        path = folder / ("%s_%s.npy" % (stem, key))
        _np.save(str(path), array)
        info = {"file": str(path), "shape": list(array.shape), "dtype": str(array.dtype)}
        numeric = _np.issubdtype(array.dtype, _np.number)
        if numeric and array.ndim == 1 and array.size >= 2:
            info["csv"] = _write_curve_csv(folder / ("%s_%s.csv" % (stem, key)), array)
        if array.size <= 32 and numeric:
            if _np.iscomplexobj(array):
                info["real"] = _np.real(array).astype(float).reshape(-1).tolist()
                info["imag"] = _np.imag(array).astype(float).reshape(-1).tolist()
            else:
                info["values"] = array.astype(float).reshape(-1).tolist()
        elif array.ndim == 1 and array.size <= 512 and numeric:
            if _np.iscomplexobj(array):
                info["real"] = _np.real(array).astype(float).tolist()
                info["imag"] = _np.imag(array).astype(float).tolist()
            else:
                info["values"] = array.astype(float).tolist()
        elif numeric and array.size:
            magnitude = _np.abs(array)
            info["abs_min"] = float(_np.nanmin(magnitude))
            info["abs_max"] = float(_np.nanmax(magnitude))
        return info

    number = _scalar(data)
    if number is not None:
        if _np is not None:
            summary["array"] = save_array("value", _np.asarray([number]))
        else:
            summary["array"] = {"shape": [1], "dtype": "float64", "values": [number]}
        return summary
    if isinstance(data, _np.ndarray):
        summary["array"] = save_array("value", data)
        return summary
    if isinstance(data, dict) or hasattr(data, "keys"):
        fields = {}
        for key in list(data.keys()):
            fields[str(key)] = save_array(str(key).replace(" ", "_"), data[key])
        summary["fields"] = fields
        return summary
    summary["repr"] = repr(data)[:2000]
    return summary


def export_results(session, exports, folder):
    saved = []
    errors = []
    for index, item in enumerate(exports):
        name = item.get("name") or ("export_%d" % index)
        try:
            safe_identifier(name, "export name")
            monitor = safe_identifier(item["monitor"], "monitor")
            if item.get("kind") == "transmission":
                # This Lumerical build accepts only the monitor name. With more
                # than one source, the value is normalized to the total source power.
                session.eval('fdtd_export_T = transmission("%s");' % monitor)
                data = session.getv("fdtd_export_T")
            else:
                data = session.getresult(monitor, item.get("result", "T"))
            record = {"name": name, "request": item, "data": store_dataset(data, folder, name)}
            if item.get("kind") == "transmission":
                record["normalization"] = "total source power"
            saved.append(record)
        except Exception as exc:
            errors.append({"name": name, "error": str(exc)})
    return saved, errors


def substitute_assignments(script, assignments):
    import re

    if not isinstance(assignments, dict) or not assignments:
        return script
    text = script
    for name, value in assignments.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)):
            raise ValueError("脚本变量名不合法：%s" % name)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("脚本变量 %s 需要是数字或字符串。" % name)
        if isinstance(value, float):
            literal = "%.12g" % value
        elif isinstance(value, str):
            if "\n" in value or ";" in value:
                raise ValueError("脚本变量 %s 的字符串不能包含分号或换行。" % name)
            literal = '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
        else:
            literal = str(value)
        pattern = re.compile(r"(?m)^(\s*)%s\s*=\s*[^;\n]*;" % re.escape(str(name)))
        text, count = pattern.subn(lambda _match, name=name, literal=literal: "%s%s = %s;" % (_match.group(1), name, literal), text, count=1)
        if count == 0:
            raise ValueError("脚本里没有赋值 %s = ...;" % name)
    return text


def load_script(spec, spec_path):
    if spec.get("script_file"):
        path = Path(spec["script_file"])
        if not path.is_file() and spec_path is not None:
            path = Path(spec_path).resolve().parent / spec["script_file"]
        if not path.is_file():
            raise FileNotFoundError("script_file not found: %s" % spec["script_file"])
        return path.read_text(encoding="utf-8")
    return spec.get("script") or ""


def open_session(project, hide):
    if project:
        return _lumapi.FDTD(str(project), hide=hide)
    return _lumapi.FDTD(hide=hide)


def new_run_dir(name, spec):
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_") or "sim"
    folder = runs_dir(spec) / ("%s_%s" % (datetime.now().strftime("%Y%m%d_%H%M%S"), safe[:40]))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def emit(payload, code=0):
    text = json.dumps(payload, ensure_ascii=False)
    result_path = payload.get("summary_path")
    if result_path:
        Path(result_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FDTD_RESULT " + text)
    return code


def close_session(session):
    if session is not None:
        try:
            session.close()
        except Exception:
            pass


def inspect_project(project):
    started = time.time()
    session = None
    payload = {"ok": False, "action": "inspect", "project": str(project)}
    try:
        bootstrap()
        session = open_session(project, hide=True)
        objects = list_objects(session)
        payload.update(
            {
                "ok": True,
                "objects": objects,
                "solver": solver_settings(session, objects),
                "elapsed_s": round(time.time() - started, 3),
            }
        )
        if not objects:
            payload["note"] = "No simulation objects were found in ::model."
        return emit(payload)
    except Exception as exc:
        payload["error"] = str(exc)
        if "Session not found" in str(exc):
            payload["hint"] = (
                "Lumerical did not keep a solver session open. Check that a license "
                "is free and that this process is allowed to start fdtd-solutions."
            )
        payload["traceback"] = traceback.format_exc(limit=8)
        return emit(payload, 1)
    finally:
        close_session(session)


def run_spec(spec, spec_path=None, emit_result=True):
    def done(payload, code=0):
        if emit_result:
            return emit(payload, code)
        return payload

    started = time.time()
    errors, warnings = validate_spec(spec)
    if errors:
        return done({"ok": False, "action": "run", "errors": errors, "warnings": warnings}, 1)
    name = spec.get("name") or "sim"
    project = spec.get("project")
    if project:
        project = Path(project)
        if not project.is_file():
            return done({"ok": False, "action": "run", "error": "project file not found: %s" % project}, 1)
    folder = new_run_dir(name, spec)
    hide = bool(spec.get("hide_gui", True))
    session = None
    payload = {
        "ok": False,
        "action": "run",
        "name": name,
        "run_dir": str(folder),
        "summary_path": str(folder / "summary.json"),
        "hide_gui": hide,
        "warnings": warnings,
    }
    saved = folder / ("%s.fsp" % "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)[:40])
    script = ""
    try:
        bootstrap()
        session = open_session(project, hide=hide)
        if spec.get("simulation"):
            if project is None:
                session.addfdtd()
            else:
                session.select("FDTD")
            apply_properties(session, spec["simulation"])
        if spec.get("global_source"):
            for key, value in spec["global_source"].items():
                session.setglobalsource(prop_name(key), value)
        add_commands(session, spec.get("commands") or [])
        apply_overrides(session, spec.get("overrides") or [])
        script = substitute_assignments(load_script(spec, spec_path), spec.get("script_assignments") or {})
        if script:
            eval_script(session, script)
        points = spec.get("frequency_points")
        if isinstance(points, int) and not isinstance(points, bool):
            session.setglobalmonitor("frequency points", int(points))
        session.save(str(saved))
        payload["project_copy"] = str(saved)
        if not spec.get("setup_only", False):
            session.run()
            session.save(str(saved))
            exported, export_errors = export_results(session, spec.get("exports") or [], folder)
            payload["exports"] = exported
            if export_errors:
                payload["export_errors"] = export_errors
                payload["note"] = (
                    "The simulation finished and the project was saved. "
                    "One or more result exports failed."
                )
        objects = list_objects(session)
        payload.update(
            {
                "ok": True,
                "setup_only": bool(spec.get("setup_only", False)),
                "objects": objects,
                "solver": solver_settings(session, objects),
                "elapsed_s": round(time.time() - started, 3),
            }
        )
        return done(payload)
    except Exception as exc:
        if saved.is_file() and "project_copy" not in payload:
            payload["project_copy"] = str(saved)
        if isinstance(exc, ScriptError):
            payload["error"] = "脚本第 %d 条语句失败（原文第 %d 行）：%s" % (exc.index, exc.line, exc.cause)
            payload["statement_index"] = exc.index
            payload["statement_line"] = exc.line
            payload["statement"] = exc.text[:500]
        else:
            payload["error"] = str(exc)
        if script:
            payload["script_lines"] = _numbered_script(script)
        if "Session not found" in str(exc):
            payload["hint"] = (
                "Lumerical did not keep a solver session open. Check that a license "
                "is free and that this process is allowed to start fdtd-solutions."
            )
        payload["traceback"] = traceback.format_exc(limit=12)
        payload["elapsed_s"] = round(time.time() - started, 3)
        return done(payload, 1)
    finally:
        close_session(session)


def run_study(study):
    import copy

    errors = validate_study(study)
    if errors:
        return emit({"ok": False, "action": "study", "errors": errors}, 1)
    goal = (study.get("metric") or {}).get("goal", "max")
    parameter = study["parameter"]
    points = []
    for value in study["values"]:
        spec = copy.deepcopy(study["base"])
        spec.setdefault("overrides", []).append(
            {"object": parameter["object"], "property": parameter["property"], "value": value}
        )
        spec["name"] = "%s_%s" % (study.get("name") or "study", value)
        payload = run_spec(spec, emit_result=False)
        points.append(
            {
                "value": value,
                "ok": bool(payload.get("ok")),
                "score": score_fdtd_payload(payload, study.get("metric")),
                "run_dir": payload.get("run_dir"),
                "error": payload.get("error"),
            }
        )
    best = choose_best(points, goal)
    return emit(
        {
            "ok": best is not None,
            "action": "study",
            "parameter": parameter,
            "goal": goal,
            "points": points,
            "best": best,
        },
        0 if best is not None else 1,
    )


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run local Lumerical FDTD")
    sub = parser.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project", required=True)
    run = sub.add_parser("run")
    run.add_argument("--spec", required=True)
    study = sub.add_parser("study")
    study.add_argument("--spec", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.action == "inspect":
        project = Path(args.project)
        if not project.is_file():
            return emit({"ok": False, "error": "project file not found: %s" % project}, 1)
        return inspect_project(project)
    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if args.action == "study":
        return run_study(spec)
    payload = run_spec(spec, spec_path, emit_result=False)
    return emit(payload, 0 if payload.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
