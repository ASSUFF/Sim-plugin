"""Compile a COMSOL Java model and run it with comsolbatch.

The Java file is copied into comsol/runs first. The caller's source file is
left unchanged.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from comsol_plugin.discover import find_install
from comsol_plugin.validate import validate_job
from sim_plugin.checklist import rejection as checklist_rejection
from sim_plugin.confirm import assumption_lines, rejection

_DEFAULT_STOPTIME_S = 600
_MAX_STOPTIME_S = 7200
_PARAM_SET = re.compile(r'(param\(\)\.set\(\s*")([^"]+)("\s*,\s*")([^"]*)(")')


def _spec_data(spec: str | Path | None) -> dict:
    if spec is None:
        return {}
    try:
        data = json.loads(Path(spec).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _assumptions(spec: str | Path | None) -> list[str]:
    return assumption_lines(_spec_data(spec))


def _confirmed(spec: str | Path | None) -> dict | None:
    if spec is None:
        return rejection({})
    try:
        data = json.loads(Path(spec).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rejection({})
    return rejection(data)


def parse_results(stdout: str) -> dict[str, str]:
    lines = stdout.splitlines()
    try:
        start = lines.index("===RESULT===")
    except ValueError:
        return {}
    results: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if line.startswith("==="):
            break
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            results[name] = value.strip()
    return results


def run_java(
    java: str | Path,
    spec: str | Path | None = None,
    *,
    runs_root: str | Path | None = None,
    stoptime_s: int = _DEFAULT_STOPTIME_S,
    install_root: str | Path | None = None,
    runner=subprocess.run,
    check_confirmation: bool = False,
) -> dict:
    if not 1 <= stoptime_s <= _MAX_STOPTIME_S:
        return {
            "ok": False,
            "stage": "arguments",
            "launched_solver": False,
            "error": f"stoptime_s 需要在 1 到 {_MAX_STOPTIME_S} 秒之间。",
        }

    checked = validate_job(java, spec)
    if not checked["ok"]:
        checked["stage"] = "validate"
        return checked
    if check_confirmation and runner is subprocess.run:
        rejected = _confirmed(spec)
        if rejected:
            return rejected
        failed = checklist_rejection(_spec_data(spec), "comsol")
        if failed:
            return failed

    install = find_install(install_root)
    if not install.ok or install.comsolcompile is None or install.comsolbatch is None:
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "install",
            "error": "没有找到 comsolcompile 或 comsolbatch。下一步：设置 COMSOL_HOME 为含有 bin/win64/comsolbatch.exe 的 Multiphysics 目录。",
            "install": install.as_dict(),
        }

    source = Path(java).resolve()
    try:
        overrides = _parameter_overrides(spec)
    except ValueError as exc:
        return {
            "ok": False,
            "stage": "spec",
            "launched_solver": False,
            "error": str(exc),
        }
    root = Path(runs_root) if runs_root is not None else source.parents[1] / "runs"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = root / f"{stamp}_{source.stem}"
    work.mkdir(parents=True, exist_ok=True)
    java_copy = work / source.name
    rewritten = apply_parameter_overrides(source.read_text(encoding="utf-8"), overrides)
    java_copy.write_text(rewritten, encoding="utf-8")

    compile_cmd = [str(install.comsolcompile), str(java_copy)]
    compiled = _run(runner, compile_cmd, work)
    class_file = java_copy.with_suffix(".class")
    if compiled["returncode"] != 0 or not class_file.is_file():
        return {
            "ok": False,
            "stage": "compile",
            "launched_solver": False,
            "work_dir": str(work),
            "command": compile_cmd,
            "returncode": compiled["returncode"],
            "stdout": compiled["stdout"],
            "stderr": compiled["stderr"],
            "error": "comsolcompile 没有生成 class 文件。",
        }

    log_file = work / f"{source.stem}_batch.log"
    output_file = work / f"{source.stem}.mph"
    batch_cmd = [
        str(install.comsolbatch),
        "-inputfile",
        str(class_file),
        "-outputfile",
        str(output_file),
        "-batchlog",
        str(log_file),
        "-stoptime",
        str(stoptime_s),
    ]
    batched = _run(runner, batch_cmd, work)
    results = parse_results(batched["stdout"])
    saved = sorted(str(path) for path in work.glob("*.mph"))
    missing = [name for name in checked["exports"] if name not in results]
    ok = batched["returncode"] == 0 and not missing and (not checked["exports"] or bool(results))
    payload = {
        "ok": ok,
        "stage": "batch",
        "launched_solver": True,
        "work_dir": str(work),
        "returncode": batched["returncode"],
        "results": results,
        "saved_models": saved,
        "batch_log": str(log_file),
        "stdout": batched["stdout"],
        "stderr": batched["stderr"],
        "class_name": checked["class_name"],
        "parameters": checked["parameters"],
        "exports": checked["exports"],
    }
    if batched["returncode"] != 0:
        payload["error"] = "comsolbatch 返回了非零退出码。日志在 batch_log。"
    elif missing:
        payload["error"] = "输出里缺少这些结果：" + ", ".join(missing)
    payload["assumptions"] = _assumptions(spec)
    report_path = work / "report.json"
    payload["report"] = str(report_path)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def apply_parameter_overrides(source: str, overrides: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(2)
        if name not in overrides:
            return match.group(0)
        return f"{match.group(1)}{name}{match.group(3)}{overrides[name]}{match.group(5)}"

    return _PARAM_SET.sub(replace, source)


def _parameter_overrides(spec: str | Path | None) -> dict[str, str]:
    if spec is None:
        return {}
    data = json.loads(Path(spec).read_text(encoding="utf-8"))
    raw = data.get("parameters") or {}
    if not isinstance(raw, dict):
        raise ValueError("parameters 需要是对象。")
    values: dict[str, str] = {}
    for name, value in raw.items():
        if isinstance(value, dict):
            if "value" not in value:
                raise ValueError(f"参数 {name} 需要包含 value。")
            text = str(value["value"])
        else:
            text = str(value)
        if '"' in text:
            raise ValueError(f"参数 {name} 的值不能包含双引号。")
        values[str(name)] = text
    return values


def _run(runner, command: list[str], work: Path) -> dict:
    completed = runner(
        command,
        cwd=str(work),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }
