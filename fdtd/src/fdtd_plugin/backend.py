"""Drive the bundled Lumerical backend. Discovery does not import lumapi."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from lumerical_fdtd.discover import find_install, runs_dir
from lumerical_fdtd.study import prepare_spec, validate_study
from lumerical_fdtd.validate import validate_spec
from sim_plugin.checklist import rejection as checklist_rejection
from sim_plugin.confirm import apply_assumptions, assumption_lines, rejection, solver_payload
from sim_plugin.sweep import combinations

ENGINE = Path(__file__).resolve().parents[1] / "lumerical_fdtd" / "engine.py"


def _timeout_s(spec: dict) -> int:
    raw = spec.get("timeout_s") if isinstance(spec, dict) else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 3600
    return max(1, int(raw))


def _prepare_env() -> None:
    os.environ.setdefault("LUMERICAL_FDTD_RUNS", str(Path(__file__).resolve().parents[2] / "runs"))


def doctor(*, runner=subprocess.run) -> dict:
    _prepare_env()
    try:
        install = find_install()
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "launched_solver": False,
            "software": "Ansys Lumerical FDTD",
            "installed": False,
            "error": str(exc),
        }
    payload = install.as_dict()
    python, source = _engine_python(install)
    payload.update(
        {
            "ok": True,
            "launched_solver": False,
            "software": "Ansys Lumerical FDTD",
            "installed": True,
            "runs_dir": str(runs_dir()),
            "python_source": source,
        }
    )
    if not _imports_numpy(python, runner):
        payload["ok"] = False
        payload["stage"] = "install"
        payload["error"] = _numpy_error(python, source)
    return payload


def _engine_python(install) -> tuple[str, str]:
    override = os.environ.get("LUMERICAL_PYTHON")
    if override:
        return override, "LUMERICAL_PYTHON"
    if getattr(install, "python", None):
        return str(install.python), "lumerical"
    return sys.executable, "plugin"


def _imports_numpy(python: str, runner) -> bool:
    completed = runner(
        [python, "-c", "import numpy"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode == 0


def _numpy_error(python: str, source: str) -> str:
    if source == "lumerical":
        where = "Lumerical 自带 Python"
    elif source == "LUMERICAL_PYTHON":
        where = "LUMERICAL_PYTHON 指定的 Python"
    else:
        where = "插件虚拟环境的 Python。没有找到 Lumerical 自带解释器，所以退回了这里"
    return (
        "用来跑 FDTD 引擎的解释器不能 import numpy。当前是%s：%s。"
        "下一步：把 LUMERICAL_PYTHON 设为该安装目录里能 import numpy 的 python.exe。"
        % (where, python)
    )


def validate(spec: dict) -> dict:
    errors, warnings = validate_spec(spec)
    return {"ok": not errors, "launched_solver": False, "errors": errors, "warnings": warnings}


def prepare(spec: dict) -> dict:
    completed, assumptions = prepare_spec(spec)
    errors, warnings = validate_spec(completed)
    return {
        "ok": not errors,
        "launched_solver": False,
        "spec": completed,
        "assumptions": assumptions,
        "errors": errors,
        "warnings": warnings,
    }


def inspect(project: str, *, runner=subprocess.run) -> dict:
    """Open a copy of an existing .fsp and list its objects. Does not solve."""
    path = Path(project)
    if not path.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"找不到工程：{path}"}
    if path.suffix.lower() != ".fsp":
        return {"ok": False, "launched_solver": False, "solved": False, "error": "FDTD 已有工程需要是 .fsp 文件。"}
    missing = _require_install()
    if missing:
        missing["solved"] = False
        return missing
    _prepare_env()
    folder = Path(os.environ["LUMERICAL_FDTD_RUNS"]) / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_inspect"
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / path.name
    shutil.copy2(path, copy)
    body = _call(["inspect", "--project", str(copy)], runner=runner)
    body["solved"] = False
    body["source"] = str(path.resolve())
    body["project_copy"] = str(copy)
    body["source_preserved"] = True
    return body


def set_project(spec: dict, *, runner=subprocess.run) -> dict:
    """Copy an existing .fsp, apply overrides, and save the copy. Does not solve."""
    if not isinstance(spec, dict) or not isinstance(spec.get("project"), str):
        return {"ok": False, "launched_solver": False, "solved": False, "stage": "spec", "error": "set 需要 project，指向已有的 .fsp。"}
    path = Path(spec["project"])
    if not path.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"找不到工程：{path}"}
    updated = dict(spec)
    updated["setup_only"] = True
    updated.setdefault("name", path.stem)
    result = run(updated, runner=runner)
    result["solved"] = False
    result["source_preserved"] = True
    return result


def run(
    spec: dict,
    *,
    runner=subprocess.run,
    check_confirmation: bool = True,
    preflight: bool = True,
    spec_dir: str | Path | None = None,
) -> dict:
    missing = _require_install()
    if missing:
        return missing
    checked = validate(spec)
    if not checked["ok"]:
        checked["stage"] = "validate"
        return checked
    solving = runner is subprocess.run and not spec.get("setup_only")
    if solving and check_confirmation:
        rejected = rejection(spec)
        if rejected:
            return rejected
    if solving and preflight:
        failed = checklist_rejection(spec, "fdtd")
        if failed:
            return failed
    ready = _resolve_script(spec, spec_dir)
    return apply_assumptions(_engine("run", ready, runner=runner), assumption_lines(spec))


def sweep(study: dict, *, runner=subprocess.run) -> dict:
    if isinstance(study, dict) and isinstance(study.get("sweep"), dict):
        return _sweep_many(study, runner=runner)
    errors = validate_study(study)
    if errors:
        return {"ok": False, "launched_solver": False, "stage": "spec", "errors": errors}
    missing = _require_install()
    if missing:
        return missing
    if runner is subprocess.run:
        rejected = rejection(study)
        if rejected:
            return rejected
        failed = checklist_rejection(study, "fdtd")
        if failed:
            return failed
    raw = _engine("study", study, runner=runner)
    if not isinstance(raw, dict) or not isinstance(raw.get("points"), list):
        return raw
    return _publish_rows(study, raw, kind="sweep")


def _resolve_script(spec: dict, spec_dir: str | Path | None) -> dict:
    """Point a relative script_file at the directory of the original spec."""
    if spec_dir is None or not isinstance(spec, dict):
        return spec
    name = spec.get("script_file")
    if not isinstance(name, str) or Path(name).is_file():
        return spec
    found = (Path(spec_dir) / name).resolve()
    if not found.is_file():
        return spec
    copied = dict(spec)
    copied["script_file"] = str(found)
    return copied


def _require_install() -> dict | None:
    status = doctor()
    if status.get("installed") and status.get("ok") is not False:
        return None
    return {
        "ok": False,
        "launched_solver": False,
        "stage": status.get("stage") or "install",
        "error": status.get("error") or "本机没有找到 Lumerical FDTD。",
    }


def _interpreter() -> str:
    override = os.environ.get("LUMERICAL_PYTHON")
    if override:
        return override
    try:
        install = find_install()
    except FileNotFoundError:
        return sys.executable
    if install.python:
        return str(install.python)
    return sys.executable


def _call(args: list[str], *, runner) -> dict:
    _prepare_env()
    if not ENGINE.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"没有找到 FDTD 引擎：{ENGINE}"}
    env = os.environ.copy()
    src = str(ENGINE.parents[1])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = runner(
        [_interpreter(), str(ENGINE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    stdout = completed.stdout or ""
    marker = "FDTD_RESULT "
    index = stdout.rfind(marker)
    if index < 0:
        return {
            "ok": False,
            "launched_solver": False,
            "solved": False,
            "returncode": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": (completed.stderr or "")[-2000:],
            "error": "FDTD 后端没有返回 FDTD_RESULT。",
        }
    try:
        body = json.loads(stdout[index + len(marker) :].strip().splitlines()[0])
    except json.JSONDecodeError:
        return {"ok": False, "launched_solver": False, "solved": False, "error": "FDTD_RESULT 不是合法 JSON。"}
    if not isinstance(body, dict):
        body = {"ok": False, "raw": body}
    body["launched_solver"] = bool(body.get("ok") or body.get("run_dir") or body.get("objects") or body.get("points"))
    return body


def _engine(action: str, spec: dict, *, runner) -> dict:
    _prepare_env()
    if not ENGINE.is_file():
        return {"ok": False, "launched_solver": False, "error": f"没有找到 FDTD 引擎：{ENGINE}"}
    inbox = Path(os.environ["LUMERICAL_FDTD_RUNS"]) / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    spec_path = inbox / f"{action}.json"
    spec_path.write_text(json.dumps(solver_payload(spec), ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    src = str(ENGINE.parents[1])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    command = [_interpreter(), str(ENGINE), action, "--spec", str(spec_path)]
    options = dict(
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if runner is subprocess.run:
        options["timeout"] = _timeout_s(spec)
    try:
        completed = runner(command, **options)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "launched_solver": True,
            "stage": "timeout",
            "error": "求解超过 %d 秒仍未返回。下一步：增大规格里的 timeout_s，或先修正材料名和脚本。" % _timeout_s(spec),
        }
    stdout = completed.stdout or ""
    marker = "FDTD_RESULT "
    index = stdout.rfind(marker)
    if index < 0:
        return {
            "ok": False,
            "launched_solver": False,
            "returncode": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": (completed.stderr or "")[-2000:],
            "error": "FDTD 后端没有返回 FDTD_RESULT。",
        }
    try:
        body = json.loads(stdout[index + len(marker) :].strip().splitlines()[0])
    except json.JSONDecodeError:
        return {"ok": False, "launched_solver": False, "error": "FDTD_RESULT 不是合法 JSON。"}
    if not isinstance(body, dict):
        body = {"ok": False, "raw": body}
    body["launched_solver"] = bool(body.get("run_dir") or body.get("points"))
    return body


def _sweep_many(study: dict, *, runner) -> dict:
    combos, error = combinations(study.get("sweep"))
    if error:
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": error}
    if not isinstance(study.get("base"), dict):
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": "base 需要是一次 FDTD 规格。"}
    if runner is subprocess.run:
        rejected = rejection(study)
        if rejected:
            return rejected
    missing = _require_install()
    if missing:
        return missing
    if runner is subprocess.run:
        failed = checklist_rejection(study, "fdtd")
        if failed:
            return failed
    metric = study.get("metric") if isinstance(study.get("metric"), dict) else {}
    expression = metric.get("export") if isinstance(metric.get("export"), str) and metric["export"].strip() else "T"
    sense = metric.get("goal") if metric.get("goal") in ("min", "max") else None
    points = []
    launched = False
    for combo in combos:
        spec = dict(study["base"])
        spec["overrides"] = list(spec.get("overrides") or [])
        for key, value in combo.items():
            if key.startswith("script:") or key.startswith("script."):
                name = key.split(":", 1)[1] if key.startswith("script:") else key.split(".", 1)[1]
                spec.setdefault("script_assignments", {})[name] = value
                continue
            object_name, _, prop = key.partition(".")
            spec["overrides"].append({"object": object_name, "property": prop or key, "value": value})
        spec["name"] = str(study.get("name") or "fdtd")
        result = run(spec, runner=runner, check_confirmation=False, preflight=False)
        launched = launched or bool(result.get("launched_solver"))
        from lumerical_fdtd.study import score_fdtd_payload

        points.append(
            {
                "value": combo,
                "ok": bool(result.get("ok")),
                "score": score_fdtd_payload(result, metric),
                "run_dir": result.get("run_dir"),
                "error": result.get("error"),
            }
        )
    raw = {"launched_solver": launched, "points": points, "goal": sense}
    published = _publish_rows({**study, "parameter": {"object": "sweep", "property": "values"}}, raw, kind="sweep")
    for row, combo in zip(published.get("rows") or [], combos):
        row["parameters"] = combo
    if isinstance(published.get("best"), dict):
        index = next((i for i, row in enumerate(published["rows"]) if row is published["best"]), None)
        if index is not None:
            published["best"] = published["rows"][index]
    report_path = published.get("report")
    if isinstance(report_path, str):
        Path(report_path).write_text(json.dumps(published, ensure_ascii=False, indent=2), encoding="utf-8")
    return published


def rows_from_points(points: list, parameter_name: str, expression: str) -> list[dict]:
    rows = []
    for point in points:
        if not isinstance(point, dict):
            continue
        score = point.get("score")
        results = {}
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            results[expression] = score
        rows.append(
            {
                "parameters": {parameter_name: point.get("value")},
                "ok": bool(point.get("ok")),
                "results": results,
                "work_dir": point.get("run_dir"),
                "error": point.get("error"),
            }
        )
    return rows


def best_row(rows: list[dict], expression: str, sense: str) -> dict | None:
    ranked = []
    for row in rows:
        value = row.get("results", {}).get(expression) if isinstance(row.get("results"), dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            ranked.append(row)
    if not ranked:
        return None
    return min(ranked, key=lambda row: row["results"][expression]) if sense == "min" else max(
        ranked, key=lambda row: row["results"][expression]
    )


def _publish_rows(study: dict, raw: dict, *, kind: str) -> dict:
    parameter = study.get("parameter") if isinstance(study.get("parameter"), dict) else {}
    obj = parameter.get("object") if isinstance(parameter.get("object"), str) else "object"
    prop = parameter.get("property") if isinstance(parameter.get("property"), str) else "property"
    metric = study.get("metric") if isinstance(study.get("metric"), dict) else {}
    expression = metric.get("export") if isinstance(metric.get("export"), str) and metric["export"].strip() else "T"
    if metric.get("goal") in ("min", "max"):
        sense = metric["goal"]
    elif kind == "optimize" and raw.get("goal") in ("min", "max"):
        sense = raw["goal"]
    elif kind == "optimize":
        sense = "max"
    else:
        sense = None
    rows = rows_from_points(raw.get("points") or [], f"{obj}.{prop}", expression)
    best = best_row(rows, expression, sense) if sense in ("min", "max") else None
    lines = assumption_lines(study)
    _stamp_point_reports(raw.get("points") or [], lines)
    _prepare_env()
    label = study.get("name") or (study.get("base") or {}).get("name") or "fdtd"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(label)).strip("_") or "fdtd"
    folder = Path(os.environ["LUMERICAL_FDTD_RUNS"]) / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}_{kind}"
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": bool(rows) and all(row["ok"] for row in rows) and (best is not None or sense not in ("min", "max")),
        "stage": kind,
        "launched_solver": bool(raw.get("launched_solver")),
        "goal": {"expression": expression, "sense": sense} if sense in ("min", "max") else None,
        "rows": rows,
        "best": best,
        "run_count": len(rows),
        "max_runs": 8,
        "work_dir": str(folder),
        "assumptions": lines,
        "note": (
            "best 是这次已计算各次里按目标选出的结果。它不是没有计算过的参数上的全局最优。"
            if sense in ("min", "max")
            else "这是一次参数研究，未设目标。"
        ),
    }
    if sense in ("min", "max") and best is None and rows and rows[-1].get("error"):
        report["error"] = rows[-1]["error"]
    elif sense in ("min", "max") and best is None:
        report["error"] = f"结果里没有可用的数值 {expression}。"
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _stamp_point_reports(points: list, lines: list[str]) -> None:
    for point in points:
        if not isinstance(point, dict) or not isinstance(point.get("run_dir"), str):
            continue
        summary = Path(point["run_dir"]) / "summary.json"
        if summary.is_file():
            apply_assumptions({"summary_path": str(summary)}, lines)
