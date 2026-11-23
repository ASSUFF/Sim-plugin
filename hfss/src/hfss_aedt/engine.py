"""Drive local Ansys HFSS. PyAEDT is imported only when a session starts."""

import argparse
import json
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hfss_aedt.discover import apply_environment, find_install, license_server_error, runs_dir
from hfss_aedt.study import assign_path, choose_best, score_hfss_payload, validate_study
from hfss_aedt.validate import validate_spec


def emit(payload, code=0):
    text = json.dumps(payload, ensure_ascii=False)
    result_path = payload.get("summary_path")
    if result_path:
        Path(result_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HFSS_RESULT " + text)
    return code


def new_run_dir(name, spec):
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_") or "hfss"
    folder = runs_dir(spec) / ("%s_%s" % (datetime.now().strftime("%Y%m%d_%H%M%S"), safe[:40]))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def existing_desktop_pids():
    try:
        import psutil
    except ImportError:
        return set()
    found = set()
    for proc in psutil.process_iter(["name", "pid"]):
        name = (proc.info.get("name") or "").lower()
        if "ansysedt" in name and proc.info.get("pid"):
            found.add(proc.info["pid"])
    return found


def session_pid(app):
    try:
        return int(app.desktop_class.aedt_process_id)
    except Exception:
        return None


def release(app, protected):
    if app is None:
        return
    pid = session_pid(app)
    if pid in protected:
        return
    try:
        app.release_desktop(close_projects=True, close_desktop=True)
    except Exception:
        pass


def _mm(metres):
    return float(metres) * 1000.0


_WALL_CONDUCTIVITY = {
    "copper": 5.8e7,
    "gold": 4.1e7,
    "aluminum": 3.8e7,
    "silver": 6.1e7,
}


def port_modes(geometry):
    modes = geometry.get("modes", 1) if isinstance(geometry, dict) else 1
    if isinstance(modes, bool) or not isinstance(modes, int):
        return 1
    return modes


def wall_conductivity(geometry):
    """Return S/m for a finite-conductivity wall, or None when the wall stays PEC."""
    if not isinstance(geometry, dict):
        return None
    wall = str(geometry.get("wall") or "pec").strip().lower()
    if wall == "pec":
        return None
    if _positive_number(geometry.get("wall_conductivity_s_m")):
        return float(geometry["wall_conductivity_s_m"])
    return _WALL_CONDUCTIVITY.get(wall)


def _positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def s_expressions(modes):
    """Keep the single-mode names. Extra modes use HFSS's P1:n form."""
    if modes <= 1:
        return ["dB(S(P1,P1))", "dB(S(P2,P1))", "dB(S(P1,P2))", "dB(S(P2,P2))"]
    names = []
    for receiver in ("P1", "P2"):
        for source in ("P1", "P2"):
            for mode_out in range(1, modes + 1):
                for mode_in in range(1, modes + 1):
                    names.append("dB(S(%s:%d,%s:%d))" % (receiver, mode_out, source, mode_in))
    return names


def build_waveguide(hfss, geometry):
    length = _mm(geometry["length_m"])
    width = _mm(geometry["a_m"])
    height = _mm(geometry["b_m"])
    hfss.modeler.model_units = "mm"
    box = hfss.modeler.create_box(
        origin=[0, 0, 0],
        sizes=[length, width, height],
        name="waveguide",
        material=geometry.get("material") or "vacuum",
    )
    modes = port_modes(geometry)
    ports = []
    wall_faces = []
    for face in box.faces:
        center = face.center
        x = float(center[0])
        if abs(x) < 1.0e-6:
            name = "P1"
        elif abs(x - length) < 1.0e-3:
            name = "P2"
        else:
            wall_faces.append(face)
            continue
        hfss.wave_port(
            assignment=face,
            name=name,
            integration_line=hfss.axis_directions.ZPos,
            modes=modes,
            renormalize=False,
            characteristic_impedance="Zpi",
        )
        ports.append(name)
    if len(ports) != 2:
        raise RuntimeError("expected wave ports on both ends, found %s" % ports)
    sigma = wall_conductivity(geometry)
    if sigma is not None and wall_faces:
        hfss.assign_finite_conductivity(
            assignment=wall_faces,
            conductivity=sigma,
            permittivity=1,
            is_internal=False,
            name="WallCond",
        )
    return {
        "a_mm": width,
        "b_mm": height,
        "length_mm": length,
        "ports": ports,
        "modes": modes,
        "wall_conductivity_s_m": sigma,
    }


def create_frequency_setup(hfss, spec):
    freq = float(spec["frequency_hz"])
    setup = hfss.create_setup(
        name="Setup1",
        setup_type="HFSSDriven",
        Frequency="%.12gGHz" % (freq / 1.0e9),
        MaximumPasses=int(spec.get("max_passes", 4)),
        MaxDeltaS=float(spec.get("max_delta_s", 0.02)),
        MinimumPasses=1,
        MinimumConvergedPasses=1,
    )
    return setup.name if hasattr(setup, "name") else "Setup1"


def solution_rows(hfss, setup_name, modes=1):
    expressions = s_expressions(modes)
    data = hfss.post.get_solution_data(expressions=expressions, setup_sweep_name="%s : LastAdaptive" % setup_name)
    rows = {}
    if not data:
        return rows
    for expr in expressions:
        try:
            values = data.data_real(expr)
        except Exception:
            values = None
        if values:
            rows[expr] = float(values[0])
    return rows


def touchstone_db(path):
    import math

    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text or text.startswith("!") or text.startswith("#"):
            continue
        rows.append([float(item) for item in text.split()])
    if not rows:
        return {}
    freq, s11m, s11a, s21m, s21a, s12m, s12a, s22m, s22a = rows[0][:9]

    def db(magnitude):
        if magnitude <= 0:
            return None
        return round(20.0 * math.log10(magnitude), 3)

    return {
        "frequency_ghz": freq,
        "dB(S(P1,P1))": db(s11m),
        "dB(S(P2,P1))": db(s21m),
        "dB(S(P1,P2))": db(s12m),
        "dB(S(P2,P2))": db(s22m),
        "angle_deg": {"S11": s11a, "S21": s21a, "S12": s12a, "S22": s22a},
    }


def open_app(spec, project_path, install):
    from ansys.aedt.core import Hfss

    apply_environment(install)
    version = spec.get("version") or install.version
    return Hfss(
        project=str(project_path),
        design=spec.get("design") or "HFSS",
        solution_type=spec.get("solution_type") or "Modal",
        version=version,
        non_graphical=bool(spec.get("hide_gui", True)),
        new_desktop=True,
        close_on_exit=False,
        remove_lock=True,
    )


def snapshot(hfss):
    objects = []
    try:
        objects = list(hfss.modeler.object_names)
    except Exception:
        pass
    setups = []
    try:
        setups = list(hfss.setup_names)
    except Exception:
        pass
    return {
        "project": str(hfss.project_name),
        "design": str(hfss.design_name),
        "objects": objects[:80],
        "setups": setups,
    }


def run_spec(spec, spec_path=None, emit_result=True):
    def done(payload, code=0):
        if emit_result:
            return emit(payload, code)
        return payload

    started = time.time()
    errors, warnings = validate_spec(spec)
    if errors:
        return done({"ok": False, "action": "run", "errors": errors, "warnings": warnings}, 1)
    license_error = license_server_error()
    if license_error:
        return done({"ok": False, "action": "run", "error": license_error}, 1)
    name = spec.get("name") or "hfss"
    folder = new_run_dir(name, spec)
    payload = {
        "ok": False,
        "action": "run",
        "name": name,
        "run_dir": str(folder),
        "summary_path": str(folder / "summary.json"),
        "hide_gui": bool(spec.get("hide_gui", True)),
        "warnings": warnings,
    }
    app = None
    protected = existing_desktop_pids()
    try:
        install = find_install(spec.get("version"))
        payload["aedt"] = install.as_dict()
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_") or "hfss"
        project_path = folder / ("%s.aedt" % safe[:40])
        if spec.get("project"):
            source = Path(spec["project"])
            if not source.is_file():
                return done({"ok": False, "action": "run", "error": "project file not found: %s" % source}, 1)
            shutil.copy2(str(source), str(project_path))
        app = open_app(spec, project_path, install)
        pid = session_pid(app)
        if pid in protected:
            raise RuntimeError(
                "HFSS attached to an already open Electronics Desktop session, pid %s. "
                "That session was left untouched." % pid
            )
        for name, value in (spec.get("variables") or {}).items():
            app[name] = value
        if spec.get("geometry"):
            payload["geometry"] = build_waveguide(app, spec["geometry"])
            if not spec.get("setup_only", False):
                setup_name = create_frequency_setup(app, spec)
                payload["setup"] = setup_name
        app.save_project()
        payload["project_copy"] = str(project_path)
        if not spec.get("setup_only", False):
            setup_name = payload.get("setup")
            if not setup_name:
                names = list(app.setup_names)
                if not names:
                    raise RuntimeError("the project has no analysis setup")
                setup_name = names[0]
                payload["setup"] = setup_name
            app.analyze_setup(setup_name)
            app.save_project()
            try:
                payload["s_db"] = solution_rows(app, setup_name, port_modes(spec.get("geometry") or {}))
            except Exception as exc:
                payload["export_errors"] = [{"error": str(exc)}]
            touchstone = folder / ("%s.s2p" % safe[:40])
            try:
                exported = app.export_touchstone(setup=setup_name, output_file=str(touchstone))
                if exported:
                    payload["touchstone"] = str(exported)
                    if not payload.get("s_db") and port_modes(spec.get("geometry") or {}) <= 1:
                        payload["s_db"] = touchstone_db(Path(str(exported)))
            except Exception as exc:
                payload.setdefault("export_errors", []).append({"error": str(exc)})
        payload["model"] = snapshot(app)
        payload["ok"] = True
        payload["elapsed_s"] = round(time.time() - started, 3)
        return done(payload)
    except Exception as exc:
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc(limit=12)
        payload["elapsed_s"] = round(time.time() - started, 3)
        return done(payload, 1)
    finally:
        release(app, protected)


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
        if parameter.get("variable"):
            variables = spec.setdefault("variables", {})
            variables[parameter["variable"]] = value
        else:
            assign_path(spec, parameter["path"], value)
        spec["name"] = "%s_%s" % (study.get("name") or "study", value)
        payload = run_spec(spec, emit_result=False)
        points.append(
            {
                "value": value,
                "ok": bool(payload.get("ok")),
                "score": score_hfss_payload(payload, study.get("metric")),
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


def inspect_project(project, version=None):
    started = time.time()
    path = Path(project)
    if not path.is_file():
        return emit({"ok": False, "action": "inspect", "error": "project file not found: %s" % path}, 1)
    license_error = license_server_error()
    if license_error:
        return emit({"ok": False, "action": "inspect", "error": license_error}, 1)
    app = None
    protected = existing_desktop_pids()
    payload = {"ok": False, "action": "inspect", "project": str(path)}
    try:
        install = find_install(version)
        app = open_app({"version": version, "hide_gui": True, "design": None}, path, install)
        payload.update({"ok": True, "model": snapshot(app), "elapsed_s": round(time.time() - started, 3)})
        return emit(payload)
    except Exception as exc:
        payload["error"] = str(exc)
        payload["traceback"] = traceback.format_exc(limit=8)
        return emit(payload, 1)
    finally:
        release(app, protected)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run local Ansys HFSS")
    sub = parser.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--version", default=None)
    run = sub.add_parser("run")
    run.add_argument("--spec", required=True)
    study = sub.add_parser("study")
    study.add_argument("--spec", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.action == "inspect":
        return inspect_project(args.project, args.version)
    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if args.action == "study":
        return run_study(spec)
    payload = run_spec(spec, spec_path, emit_result=False)
    return emit(payload, 0 if payload.get("ok") else 1)


if __name__ == "__main__":
    sys.exit(main())
