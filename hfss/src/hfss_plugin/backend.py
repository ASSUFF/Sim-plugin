"""Call the bundled hfss_aedt backend, or one named by the environment.

HFSS_AEDT_PYTHON and HFSS_AEDT_SRC replace the interpreter and the src
directory. When they are unset, the plugin uses its own Python and hfss/src.
doctor, validate, and prepare do not import PyAEDT and do not launch
Electronics Desktop. A solve does need PyAEDT.
"""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sim_plugin.checklist import rejection as checklist_rejection
from sim_plugin.confirm import apply_assumptions, assumption_lines, rejection, solver_payload
from sim_plugin.result_check import problems as result_problems
from sim_plugin.sweep import combinations

_DEFAULT_PROTECTED_PROJECT = Path(r"S:\simulation\HFSS\4mm.aedt")


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw) if raw else None


def _bundled_src() -> Path:
    return Path(__file__).resolve().parent.parent


def _backend_python() -> Path | None:
    override = _env_path("HFSS_AEDT_PYTHON")
    if override is not None:
        return override
    return Path(sys.executable)


def _backend_src() -> Path | None:
    override = _env_path("HFSS_AEDT_SRC")
    if override is not None:
        return override
    bundled = _bundled_src()
    engine = _engine_path(bundled)
    if engine is not None and engine.is_file():
        return bundled
    return None


def _engine_path(source: Path | None = None) -> Path | None:
    folder = Path(source) if source is not None else _backend_src()
    if folder is None:
        return None
    return folder / "hfss_aedt" / "engine.py"


def _backend_message() -> str:
    python = os.environ.get("HFSS_AEDT_PYTHON") or "未设置"
    src = os.environ.get("HFSS_AEDT_SRC") or "未设置"
    return (
        "没有找到 HFSS 后端。"
        f"下一步：HFSS_AEDT_PYTHON（当前为 {python}）和 HFSS_AEDT_SRC（当前为 {src}）"
        "若指向了不存在的文件，请去掉这两个变量，改用插件自带的 hfss/src/hfss_aedt。"
        "求解还需要当前 Python 能 import ansys.aedt.core；没有时执行 pip install pyaedt。"
    )


def _pyaedt_problem(executable: Path) -> dict | None:
    completed = subprocess.run(
        [str(executable), "-c", "import ansys.aedt.core"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return None
    return {
        "ok": False,
        "launched_solver": False,
        "stage": "backend",
        "error": (
            "HFSS 后端已在 hfss/src/hfss_aedt，但当前 Python 不能 import ansys.aedt.core。"
            "下一步：在插件环境执行 pip install pyaedt，或把 HFSS_AEDT_PYTHON 设为已经安装 PyAEDT 的 python.exe。"
        ),
    }


def _backend_problem(executable: Path | None, engine: Path | None, *, need_engine: bool) -> dict | None:
    python_ok = executable is not None and executable.is_file()
    engine_ok = engine is not None and engine.is_file()
    if python_ok and (engine_ok or not need_engine):
        return None
    return {"ok": False, "launched_solver": False, "stage": "backend", "error": _backend_message()}


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


def run(
    spec: dict,
    *,
    python: Path | None = None,
    src: Path | None = None,
    runner=subprocess.run,
    check_confirmation: bool = True,
    preflight: bool = True,
) -> dict:
    blocked = _protected_project(spec)
    if blocked:
        return blocked
    limited = _unsupported_request(spec)
    if limited:
        return limited
    solving = runner is subprocess.run and not spec.get("setup_only")
    if solving and check_confirmation:
        rejected = rejection(spec)
        if rejected:
            return rejected
    if solving and preflight:
        failed = checklist_rejection(spec, "hfss")
        if failed:
            return failed
    if preflight and runner is subprocess.run:
        license_message = license_error()
        if license_message:
            return {"ok": False, "launched_solver": False, "stage": "license", "error": license_message}
    checked = validate(spec, python=python, src=src, runner=runner)
    if not checked.get("ok"):
        checked["stage"] = "validate"
        return checked
    body = apply_assumptions(_engine("run", spec, python=python, src=src, runner=runner), assumption_lines(spec))
    return _reject_bad_numbers(body, spec.get("expect") if isinstance(spec, dict) else None)


def sweep(study: dict, *, python: Path | None = None, src: Path | None = None, runner=subprocess.run) -> dict:
    base = study.get("base") if isinstance(study, dict) else None
    blocked = _protected_project(base if isinstance(base, dict) else {})
    if blocked:
        return blocked
    limited = _unsupported_request(base if isinstance(base, dict) else {})
    if limited:
        return limited
    if isinstance(study, dict) and isinstance(study.get("sweep"), dict):
        return _sweep_many(study, python=python, src=src, runner=runner)
    if runner is subprocess.run:
        rejected = rejection(study if isinstance(study, dict) else {})
        if rejected:
            return rejected
        failed = checklist_rejection(study, "hfss")
        if failed:
            return failed
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
    return f"连不上 Ansys 许可证服务 {raw}。下一步：启动本机的 Ansys 许可证服务后再求解一次。"


def _runs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "runs"


_KNOWN_MATERIALS = {"vacuum", "air", "pec", "copper", "gold", "aluminum", "silver", "teflon"}


def _unsupported_request(spec: dict) -> dict | None:
    """Stop requests the current backend would answer with the wrong physics."""
    if not isinstance(spec, dict):
        return None
    if spec.get("project") and not str(spec.get("design") or "").strip():
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "spec",
            "error": "打开已有工程需要 spec.design，填写该工程里已经存在的设计名。留空时后端会新建名为 HFSS 的空设计。",
        }
    geometry = spec.get("geometry") if isinstance(spec.get("geometry"), dict) else {}
    kind = geometry.get("kind")
    if isinstance(kind, str) and kind != "rectangular_waveguide":
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "spec",
            "error": (
                f"当前 HFSS 后端只能建立矩形波导，不能建立 {kind}，也不返回端口 Neff 或 Z0。"
                "下一步：改用 rectangular_waveguide，或在工程里建好模型后用 project 和 design 打开。"
            ),
        }
    requested = [str(item) for item in spec.get("quantities") or []]
    missing = [item for item in requested if item.lower() in {"z0", "neff", "n_rf", "nrf"}]
    if missing:
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "spec",
            "error": "当前 HFSS 后端只返回 S 参数，不能返回 " + "、".join(missing) + "。下一步：从 quantities 里去掉这些量。",
        }
    material = geometry.get("material")
    if (
        isinstance(material, str)
        and material.strip()
        and material.strip().lower() not in _KNOWN_MATERIALS
        and spec.get("material_verified") is not True
    ):
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "spec",
            "error": (
                f"材料名 {material} 未经确认。未知名称会被后端换成 vacuum，结果仍可能显示成功。"
                "下一步：改用 vacuum、air、pec、copper、gold、aluminum、silver、teflon，"
                "或确认材料库里确有该名称后把 material_verified 设为 true。"
            ),
        }
    return None


def _reject_bad_numbers(body: dict, expect) -> dict:
    if not isinstance(body, dict) or not body.get("ok"):
        return body
    values = body.get("s_db") if isinstance(body.get("s_db"), dict) else {}
    found = result_problems(values, expect if isinstance(expect, dict) else None)
    if not found:
        return body
    failed = dict(body)
    failed["ok"] = False
    failed["stage"] = "result"
    failed["error"] = "结果未通过数值检查：" + " ".join(found)
    return failed


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
    source = Path(src) if src is not None else _backend_src()
    engine = _engine_path(source)
    problem = _backend_problem(executable, engine, need_engine=True)
    if problem:
        return problem
    if runner is subprocess.run:
        missing = _pyaedt_problem(executable)
        if missing:
            return missing
    inbox = _runs_root() / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    spec_path = inbox / f"{action}.json"
    spec_path.write_text(json.dumps(solver_payload(spec), ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
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
    source = Path(src) if src is not None else _backend_src()
    engine = _engine_path(source)
    problem = _backend_problem(executable, engine, need_engine=True)
    if problem:
        problem["solved"] = False
        return problem
    if runner is subprocess.run:
        missing = _pyaedt_problem(executable)
        if missing:
            missing["solved"] = False
            return missing
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
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
    problem = _backend_problem(executable, None, need_engine=False)
    if problem or source is None:
        return problem or {"ok": False, "launched_solver": False, "stage": "backend", "error": _backend_message()}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("HFSS_AEDT_RUNS", str(Path(__file__).resolve().parents[2] / "runs"))
    completed = runner(
        [str(executable), "-c", script],
        input=None if payload is None else json.dumps(solver_payload(payload)),
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


def _sweep_many(study: dict, *, python, src, runner) -> dict:
    combos, error = combinations(study.get("sweep"))
    if error:
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": error}
    if runner is subprocess.run:
        rejected = rejection(study)
        if rejected:
            return rejected
        failed = checklist_rejection(study, "hfss")
        if failed:
            return failed
        license_message = license_error()
        if license_message:
            return {"ok": False, "launched_solver": False, "stage": "license", "error": license_message}
    metric = study.get("metric") if isinstance(study.get("metric"), dict) else {}
    expression = metric.get("key") if isinstance(metric.get("key"), str) and metric["key"].strip() else "dB(S(P2,P1))"
    ranked = metric.get("goal") in ("min", "max")
    sense = metric.get("goal") if ranked else None
    rows = []
    launched = False
    for combo in combos:
        spec = copy.deepcopy(study.get("base") if isinstance(study.get("base"), dict) else {})
        for key, value in combo.items():
            _assign(spec, key, value)
        spec["name"] = _combo_name(study, combo)
        result = run(spec, python=python, src=src, runner=runner, check_confirmation=False, preflight=False)
        launched = launched or bool(result.get("launched_solver"))
        s_db = result.get("s_db") if isinstance(result.get("s_db"), dict) else {}
        results = {
            key: value
            for key, value in s_db.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        rows.append(
            {
                "parameters": combo,
                "ok": bool(result.get("ok")) and (not ranked or expression in results),
                "results": results,
                "work_dir": result.get("run_dir"),
                "error": result.get("error"),
            }
        )
    return _write_rows(study, rows, expression, sense, launched, "sweep")


def _assign(spec: dict, key: str, value) -> None:
    if "." not in key:
        spec[key] = value
        return
    node = spec
    parts = key.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _combo_name(study: dict, combo: dict) -> str:
    label = str(study.get("name") or "hfss")
    suffix = "_".join(f"{value:g}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value) for value in combo.values())
    return f"{label}_{suffix}"[:80]


def _write_rows(study: dict, rows: list[dict], expression: str, sense: str | None, launched: bool, kind: str) -> dict:
    ranked = sense in ("min", "max")
    best = _best_row(rows, expression, sense) if ranked else None
    label = study.get("name") or (study.get("base") or {}).get("name") or "hfss"
    folder = _runs_root() / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_name(str(label))}_{kind}"
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": bool(rows) and all(row["ok"] for row in rows) and (best is not None or not ranked),
        "stage": kind,
        "launched_solver": launched,
        "goal": {"expression": expression, "sense": sense} if ranked else None,
        "rows": rows,
        "best": best,
        "run_count": len(rows),
        "max_runs": 8,
        "work_dir": str(folder),
        "assumptions": assumption_lines(study),
        "note": (
            "best 是这次已计算各次里按目标选出的结果。它不是没有计算过的参数上的全局最优。"
            if ranked
            else "这是一次参数研究，未设目标。"
        ),
    }
    if ranked and best is None and rows and rows[-1].get("error"):
        report["error"] = rows[-1]["error"]
    elif ranked and best is None:
        report["error"] = f"结果里没有可用的数值 {expression}。"
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


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
        "assumptions": assumption_lines(study),
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
