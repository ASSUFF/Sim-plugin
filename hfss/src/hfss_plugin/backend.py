"""Call an hfss-aedt checkout in its own environment.

Set HFSS_AEDT_PYTHON and HFSS_AEDT_SRC to that checkout. When they are unset,
the development-machine checkout is used if it is present. doctor, validate,
and prepare do not launch Electronics Desktop.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path

_DEFAULT_BACKEND_PYTHON = Path(r"S:\simulation\FDTD\ai\em-sim\.venv\Scripts\python.exe")
_DEFAULT_BACKEND_SRC = Path(r"S:\simulation\FDTD\ai\hfss-aedt\src")
_DEFAULT_PROTECTED_PROJECT = Path(r"S:\simulation\HFSS\4mm.aedt")


def _backend_python() -> Path:
    override = os.environ.get("HFSS_AEDT_PYTHON")
    return Path(override) if override else _DEFAULT_BACKEND_PYTHON


def _backend_src() -> Path:
    override = os.environ.get("HFSS_AEDT_SRC")
    return Path(override) if override else _DEFAULT_BACKEND_SRC


def _engine_path() -> Path:
    return _backend_src() / "hfss_aedt" / "engine.py"


def _protected_project_path() -> Path:
    override = os.environ.get("HFSS_PROTECTED_PROJECT")
    return Path(override) if override else _DEFAULT_PROTECTED_PROJECT

_DOCTOR = r"""
import json
from hfss_aedt.discover import find_install, runs_dir
try:
    install = find_install()
    body = install.as_dict()
    body["ok"] = True
    body["software"] = "Ansys HFSS"
    body["runs_dir"] = str(runs_dir())
except FileNotFoundError as exc:
    body = {"ok": False, "software": "Ansys HFSS", "error": str(exc)}
body["launched_solver"] = False
print(json.dumps(body, ensure_ascii=False))
"""

_VALIDATE = r"""
import json, sys
from hfss_aedt.validate import validate_spec
spec = json.load(sys.stdin)
errors, warnings = validate_spec(spec)
print(json.dumps({"ok": not errors, "launched_solver": False, "errors": errors, "warnings": warnings}, ensure_ascii=False))
"""

_PREPARE = r"""
import json, sys
from hfss_aedt.study import prepare_spec
from hfss_aedt.validate import validate_spec
spec = json.load(sys.stdin)
completed, assumptions = prepare_spec(spec)
errors, warnings = validate_spec(completed)
print(json.dumps({
    "ok": not errors,
    "launched_solver": False,
    "spec": completed,
    "assumptions": assumptions,
    "errors": errors,
    "warnings": warnings,
}, ensure_ascii=False))
"""


def doctor(*, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    return _invoke(_DOCTOR, None, python=python, src=src, runner=runner)


def validate(spec: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    return _invoke(_VALIDATE, spec, python=python, src=src, runner=runner)


def prepare(spec: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    return _invoke(_PREPARE, spec, python=python, src=src, runner=runner)


def run(spec: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    blocked = _protected_project(spec)
    if blocked:
        return blocked
    if runner is subprocess.run:
        license_message = license_error()
        if license_message:
            return {"ok": False, "launched_solver": False, "stage": "license", "error": license_message}
    checked = validate(spec, python=python, src=src, runner=runner)
    if not checked.get("ok"):
        checked["stage"] = "validate"
        return checked
    return _engine("run", spec, python=python, src=src, runner=runner)


def sweep(study: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    base = study.get("base") if isinstance(study, dict) else None
    blocked = _protected_project(base if isinstance(base, dict) else {})
    if blocked:
        return blocked
    if runner is subprocess.run:
        license_message = license_error()
        if license_message:
            return {"ok": False, "launched_solver": False, "stage": "license", "error": license_message}
    raw = _engine("study", study, python=python, src=src, runner=runner)
    if not isinstance(raw, dict) or not isinstance(raw.get("points"), list):
        return raw
    return _publish_sweep(study if isinstance(study, dict) else {}, raw)


def license_error(address: str | None = None) -> str | None:
    raw = address if address is not None else os.environ.get("ANSYSLMD_LICENSE_FILE", "1055@localhost")
    targets = []
    for part in raw.split(";"):
        part = part.strip()
        if "@" not in part:
            continue
        port, host = part.split("@", 1)
        if port.isdigit() and host:
            targets.append((host, int(port)))
    if not targets:
        return None
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=2):
                return None
        except OSError:
            continue
    return (
        "连不上 Ansys 许可证服务 "
        + raw
        + "。本机服务名是 Ansys PLE Licensing 2026 R1。"
        + "服务停止时不会启动 Electronics Desktop。"
    )


def _runs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "runs"


def _protected_project(spec: dict) -> dict | None:
    project = spec.get("project") if isinstance(spec, dict) else None
    if not isinstance(project, str) or not project.strip():
        return None
    try:
        same = Path(project).resolve() == _protected_project_path().resolve()
    except OSError:
        same = False
    if not same:
        return None
    return {
        "ok": False,
        "launched_solver": False,
        "error": f"不会打开或复制 {_protected_project_path()}。请换一个工程。",
    }


def inspect(project: str, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    """Open a copy of an existing .aedt and list its objects and setups. Does not solve."""
    path = Path(project)
    if not path.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"找不到工程：{path}"}
    if path.suffix.lower() != ".aedt":
        return {"ok": False, "launched_solver": False, "solved": False, "error": "HFSS 已有工程需要是 .aedt 文件。"}
    blocked = _protected_project({"project": str(path)})
    if blocked:
        blocked["solved"] = False
        return blocked
    folder = _runs_root() / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_inspect"
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / path.name
    shutil.copy2(path, copy)
    body = _call(["inspect", "--project", str(copy)], python=python, src=src, runner=runner)
    body["solved"] = False
    body["source"] = str(path.resolve())
    body["project_copy"] = str(copy)
    body["source_preserved"] = True
    return body


def set_project(spec: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    """Copy an existing .aedt, write variables, and save the copy. Does not solve."""
    if not isinstance(spec, dict) or not isinstance(spec.get("project"), str):
        return {"ok": False, "launched_solver": False, "solved": False, "stage": "spec", "error": "set 需要 project，指向已有的 .aedt。"}
    updated = dict(spec)
    updated["setup_only"] = True
    result = run(updated, python=python, src=src, runner=runner)
    result["solved"] = False
    return result


def _engine(action: str, spec: dict, *, python: Path | None, src: Path | None, runner) -> dict:
    executable = Path(python) if python is not None else _backend_python()
    engine = _engine_path()
    if not executable.is_file():
        return {"ok": False, "launched_solver": False, "error": f"没有找到 HFSS 后端解释器：{executable}"}
    if not engine.is_file():
        return {"ok": False, "launched_solver": False, "error": f"没有找到 HFSS 引擎：{engine}"}
    inbox = _runs_root() / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    spec_path = inbox / f"{action}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_backend_src() if src is None else src) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("HFSS_AEDT_RUNS", str(_runs_root()))
    env.setdefault("ANSYSLMD_LICENSE_FILE", "1055@localhost")
    completed = runner(
        [str(executable), str(engine), action, "--spec", str(spec_path)],
        input=None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    stdout = completed.stdout or ""
    marker = "HFSS_RESULT "
    index = stdout.rfind(marker)
    if index < 0:
        return {
            "ok": False,
            "launched_solver": False,
            "returncode": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": (completed.stderr or "")[-2000:],
            "error": "HFSS 后端没有返回 HFSS_RESULT。",
        }
    line = stdout[index + len(marker) :].strip().splitlines()[0]
    try:
        body = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "launched_solver": False, "error": "HFSS_RESULT 不是合法 JSON。", "raw": line[-2000:]}
    if not isinstance(body, dict):
        body = {"ok": False, "raw": body}
    body["launched_solver"] = bool(body.get("run_dir") or body.get("aedt") or body.get("points"))
    return body


def _call(args: list[str], *, python: Path | None, src: Path | None, runner) -> dict:
    executable = Path(python) if python is not None else _backend_python()
    engine = _engine_path()
    if not executable.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"没有找到 HFSS 后端解释器：{executable}"}
    if not engine.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"没有找到 HFSS 引擎：{engine}"}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_backend_src() if src is None else src) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("HFSS_AEDT_RUNS", str(_runs_root()))
    env.setdefault("ANSYSLMD_LICENSE_FILE", "1055@localhost")
    completed = runner(
        [str(executable), str(engine), *args],
        input=None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    return _parse_result(completed, "HFSS_RESULT ")


def _parse_result(completed, marker: str) -> dict:
    stdout = completed.stdout or ""
    index = stdout.rfind(marker)
    if index < 0:
        return {
            "ok": False,
            "launched_solver": False,
            "solved": False,
            "returncode": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": (completed.stderr or "")[-2000:],
            "error": "HFSS 后端没有返回 HFSS_RESULT。",
        }
    line = stdout[index + len(marker) :].strip().splitlines()[0]
    try:
        body = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "launched_solver": False, "solved": False, "error": "HFSS_RESULT 不是合法 JSON。", "raw": line[-2000:]}
    if not isinstance(body, dict):
        body = {"ok": False, "raw": body}
    body["launched_solver"] = bool(body.get("run_dir") or body.get("aedt") or body.get("points") or body.get("model"))
    return body


def _invoke(script: str, payload: dict | None, *, python: Path | None, src: Path | None, runner) -> dict:
    executable = Path(python) if python is not None else _backend_python()
    source = Path(src) if src is not None else _backend_src()
    if not executable.is_file():
        return {
            "ok": False,
            "launched_solver": False,
            "error": f"没有找到 HFSS 后端解释器：{executable}",
        }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("HFSS_AEDT_RUNS", str(Path(__file__).resolve().parents[2] / "runs"))
    completed = runner(
        [str(executable), "-c", script],
        input=None if payload is None else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    stdout = completed.stdout or ""
    try:
        body = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {
            "ok": False,
            "launched_solver": False,
            "returncode": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": (completed.stderr or "")[-2000:],
            "error": "HFSS 后端没有返回 JSON。",
        }
    if not isinstance(body, dict):
        body = {"ok": False, "raw": body}
    body.setdefault("launched_solver", False)
    if completed.returncode != 0 and body.get("ok") is not False:
        body["ok"] = False
        body["returncode"] = completed.returncode
    return body


def _publish_sweep(study: dict, raw: dict) -> dict:
    """Turn the old engine's points into the same rows/best shape COMSOL uses."""
    parameter = study.get("parameter") if isinstance(study.get("parameter"), dict) else {}
    if isinstance(parameter.get("path"), str) and parameter["path"].strip():
        parameter_name = parameter["path"].strip()
    elif isinstance(parameter.get("variable"), str) and parameter["variable"].strip():
        parameter_name = parameter["variable"].strip()
    else:
        parameter_name = "value"
    metric = study.get("metric") if isinstance(study.get("metric"), dict) else {}
    if metric.get("goal") in ("min", "max"):
        sense = metric["goal"]
    elif raw.get("goal") in ("min", "max"):
        sense = raw["goal"]
    else:
        sense = "max"
    expression = metric.get("key") if isinstance(metric.get("key"), str) and metric["key"].strip() else "dB(S(P2,P1))"
    rows = []
    for point in raw.get("points") or []:
        if not isinstance(point, dict):
            continue
        rows.append(
            {
                "parameters": {parameter_name: point.get("value")},
                "ok": bool(point.get("ok")),
                "results": _sweep_results(point, expression),
                "work_dir": point.get("run_dir"),
                "error": point.get("error"),
            }
        )
    best = _best_row(rows, expression, sense)
    label = study.get("name") or (study.get("base") or {}).get("name") or "hfss"
    folder = _runs_root() / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_name(str(label))}_sweep"
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": bool(rows) and all(row["ok"] for row in rows) and best is not None,
        "stage": "sweep",
        "launched_solver": bool(raw.get("launched_solver")),
        "goal": {"expression": expression, "sense": sense},
        "rows": rows,
        "best": best,
        "run_count": len(rows),
        "max_runs": 8,
        "work_dir": str(folder),
        "note": "best 是这次已计算各次里按目标选出的结果。它不是没有计算过的参数上的全局最优。",
    }
    if best is None and rows and rows[-1].get("error"):
        report["error"] = rows[-1]["error"]
    elif best is None:
        report["error"] = f"结果里没有可用的数值 {expression}。"
    elif raw.get("error"):
        report["error"] = raw["error"]
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _sweep_results(point: dict, expression: str) -> dict:
    loaded = _load_s_db(point.get("run_dir"))
    score = point.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        loaded[expression] = float(score)
    return loaded


def _load_s_db(run_dir) -> dict:
    if not isinstance(run_dir, str) or not run_dir.strip():
        return {}
    folder = Path(run_dir)
    merged = _touchstone_s_db(folder)
    summary = _summary_s_db(folder)
    merged.update(summary)
    return merged


def _summary_s_db(folder: Path) -> dict:
    path = folder / "summary.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    s_db = data.get("s_db") if isinstance(data, dict) else None
    if not isinstance(s_db, dict):
        return {}
    return {
        key: value
        for key, value in s_db.items()
        if isinstance(value, (int, float, str)) and not isinstance(value, bool)
    }


def _touchstone_s_db(folder: Path) -> dict:
    files = sorted(folder.glob("*.s2p")) if folder.is_dir() else []
    if not files:
        return {}
    rows = []
    for line in files[0].read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text or text.startswith("!") or text.startswith("#"):
            continue
        try:
            rows.append([float(item) for item in text.split()])
        except ValueError:
            continue
    if not rows or len(rows[0]) < 5:
        return {}
    values = rows[0]

    def db(magnitude: float):
        if magnitude <= 0:
            return None
        return round(20.0 * math.log10(magnitude), 3)

    body = {"frequency_ghz": values[0]}
    pairs = [("dB(S(P1,P1))", values[1]), ("dB(S(P2,P1))", values[3])]
    if len(values) >= 9:
        pairs.extend([("dB(S(P1,P2))", values[5]), ("dB(S(P2,P2))", values[7])])
    for key, magnitude in pairs:
        converted = db(magnitude)
        if converted is not None:
            body[key] = converted
    return body


def _best_row(rows: list[dict], expression: str, sense: str) -> dict | None:
    usable = []
    for row in rows:
        if not row.get("ok"):
            continue
        value = row["results"].get(expression)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            usable.append(row)
    if not usable:
        return None
    chosen = min(usable, key=lambda row: row["results"][expression]) if sense == "min" else max(
        usable, key=lambda row: row["results"][expression]
    )
    return dict(chosen)


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name).strip("_")
    return cleaned or "hfss"
