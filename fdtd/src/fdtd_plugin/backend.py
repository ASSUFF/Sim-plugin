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

ENGINE = Path(__file__).resolve().parents[1] / "lumerical_fdtd" / "engine.py"


def _prepare_env() -> None:
    os.environ.setdefault("LUMERICAL_FDTD_RUNS", str(Path(__file__).resolve().parents[2] / "runs"))


def doctor() -> dict:
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
    payload.update(
        {
            "ok": True,
            "launched_solver": False,
            "software": "Ansys Lumerical FDTD",
            "installed": True,
            "runs_dir": str(runs_dir()),
        }
    )
    return payload


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


def run(spec: dict, *, runner=subprocess.run) -> dict:
    missing = _require_install()
    if missing:
        return missing
    checked = validate(spec)
    if not checked["ok"]:
        checked["stage"] = "validate"
        return checked
    return _engine("run", spec, runner=runner)


def sweep(study: dict, *, runner=subprocess.run) -> dict:
    errors = validate_study(study)
    if errors:
        return {"ok": False, "launched_solver": False, "stage": "spec", "errors": errors}
    missing = _require_install()
    if missing:
        return missing
    return _engine("study", study, runner=runner)


def _require_install() -> dict | None:
    status = doctor()
    if status.get("installed"):
        return None
    return {
        "ok": False,
        "launched_solver": False,
        "stage": "install",
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
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = os.environ.copy()
    src = str(ENGINE.parents[1])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    completed = runner(
        [_interpreter(), str(ENGINE), action, "--spec", str(spec_path)],
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
