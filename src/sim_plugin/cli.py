"""Command line used by Cursor, Codex, Claude, and DeepSeek Harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from comsol_plugin.advise import advise
from comsol_plugin.batch import run_java
from comsol_plugin.discover import doctor
from comsol_plugin.search import search_features
from comsol_plugin.study import run_optimize, run_sweep
from comsol_plugin.validate import validate_job
from hfss_plugin.advise import advise as hfss_advise
from hfss_plugin.backend import doctor as hfss_doctor
from hfss_plugin.backend import prepare as hfss_prepare
from hfss_plugin.backend import run as hfss_run
from hfss_plugin.backend import sweep as hfss_sweep
from hfss_plugin.backend import validate as hfss_validate
from hfss_plugin.optimize import optimize as hfss_optimize
from fdtd_plugin.advise import advise as fdtd_advise
from fdtd_plugin.backend import doctor as fdtd_doctor
from fdtd_plugin.backend import prepare as fdtd_prepare
from fdtd_plugin.backend import run as fdtd_run
from fdtd_plugin.backend import sweep as fdtd_sweep
from fdtd_plugin.backend import validate as fdtd_validate
from fdtd_plugin.optimize import optimize as fdtd_optimize


def _read_json(path: str) -> dict:
    file = Path(path)
    if not file.is_file():
        return {"ok": False, "launched_solver": False, "error": f"找不到规格文件：{file}"}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "launched_solver": False, "error": f"规格不是合法 JSON：{exc.lineno} 行。"}
    if not isinstance(data, dict):
        return {"ok": False, "launched_solver": False, "error": "规格的顶层需要是 JSON 对象。"}
    return data


def _print(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sim-plugin")
    solvers = parser.add_subparsers(dest="solver", required=True)

    comsol = solvers.add_parser("comsol")
    commands = comsol.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="Report the COMSOL install without launching it")

    search = commands.add_parser("search", help="Look up Java API feature names")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=20)

    validate = commands.add_parser("validate", help="Check a Java model and optional JSON spec")
    validate.add_argument("--java", required=True)
    validate.add_argument("--spec")

    run = commands.add_parser("run", help="Validate, compile, and batch-run a Java model")
    run.add_argument("--java", required=True)
    run.add_argument("--spec")
    run.add_argument("--stoptime", type=int, default=600)

    sweep = commands.add_parser("sweep", help="Run every combination in spec.sweep, at most 8")
    sweep.add_argument("--java", required=True)
    sweep.add_argument("--spec", required=True)
    sweep.add_argument("--stoptime", type=int, default=600)

    optimize = commands.add_parser("optimize", help="Coarse-to-fine search, at most 8 runs")
    optimize.add_argument("--java", required=True)
    optimize.add_argument("--spec", required=True)
    optimize.add_argument("--stoptime", type=int, default=600)

    advice = commands.add_parser("advise", help="Read a report and list facts for the AI to explain")
    advice.add_argument("--report", required=True)

    hfss = solvers.add_parser("hfss")
    hfss_commands = hfss.add_subparsers(dest="command", required=True)
    hfss_commands.add_parser("doctor", help="Report the HFSS install without launching it")
    hfss_validate_cmd = hfss_commands.add_parser("validate", help="Check an HFSS spec without a license")
    hfss_validate_cmd.add_argument("--spec", required=True)
    hfss_prepare_cmd = hfss_commands.add_parser("prepare", help="Fill missing HFSS settings without launching it")
    hfss_prepare_cmd.add_argument("--spec", required=True)
    hfss_run_cmd = hfss_commands.add_parser("run", help="Solve an HFSS spec with the existing backend")
    hfss_run_cmd.add_argument("--spec", required=True)
    hfss_sweep_cmd = hfss_commands.add_parser("sweep", help="Compare 2 to 8 values of one HFSS parameter")
    hfss_sweep_cmd.add_argument("--spec", required=True)
    hfss_optimize_cmd = hfss_commands.add_parser("optimize", help="Coarse-to-fine search of one HFSS parameter, at most 8 runs")
    hfss_optimize_cmd.add_argument("--spec", required=True)
    hfss_advice = hfss_commands.add_parser("advise", help="Read an HFSS report and list facts")
    hfss_advice.add_argument("--report", required=True)

    fdtd = solvers.add_parser("fdtd")
    fdtd_commands = fdtd.add_subparsers(dest="command", required=True)
    fdtd_commands.add_parser("doctor", help="Report whether Lumerical FDTD is installed")
    for _name, _help in (
        ("validate", "Check an FDTD spec without the solver"),
        ("prepare", "Fill missing FDTD settings without the solver"),
        ("run", "Run an FDTD spec when Lumerical is installed"),
        ("sweep", "Compare 2 to 8 values of one object property"),
        ("optimize", "Coarse-to-fine search of one object property, at most 8 runs"),
    ):
        _cmd = fdtd_commands.add_parser(_name, help=_help)
        _cmd.add_argument("--spec", required=True)
    fdtd_advice = fdtd_commands.add_parser("advise", help="Read an FDTD report and list facts")
    fdtd_advice.add_argument("--report", required=True)

    args = parser.parse_args(argv)
    if args.solver == "hfss":
        if args.command == "doctor":
            return _print(hfss_doctor())
        if args.command == "advise":
            return _print(hfss_advise(args.report))
        spec = _read_json(args.spec)
        if isinstance(spec, dict) and spec.get("ok") is False:
            return _print(spec)
        if args.command == "validate":
            return _print(hfss_validate(spec))
        if args.command == "prepare":
            return _print(hfss_prepare(spec))
        if args.command == "run":
            return _print(hfss_run(spec))
        if args.command == "sweep":
            return _print(hfss_sweep(spec))
        if args.command == "optimize":
            return _print(hfss_optimize(spec))
        return _print({"ok": False, "error": "未知命令。"})
    if args.solver == "fdtd":
        if args.command == "doctor":
            return _print(fdtd_doctor())
        if args.command == "advise":
            return _print(fdtd_advise(args.report))
        spec = _read_json(args.spec)
        if isinstance(spec, dict) and spec.get("ok") is False:
            return _print(spec)
        if args.command == "validate":
            return _print(fdtd_validate(spec))
        if args.command == "prepare":
            return _print(fdtd_prepare(spec))
        if args.command == "run":
            return _print(fdtd_run(spec))
        if args.command == "sweep":
            return _print(fdtd_sweep(spec))
        if args.command == "optimize":
            return _print(fdtd_optimize(spec))
        return _print({"ok": False, "error": "未知命令。"})
    if args.solver != "comsol":
        return _print({"ok": False, "error": "这个软件的命令还没有实现。"})
    if args.command == "doctor":
        return _print(doctor())
    if args.command == "search":
        return _print(search_features(args.keyword, limit=args.limit))
    if args.command == "validate":
        return _print(validate_job(args.java, args.spec))
    if args.command == "run":
        return _print(run_java(args.java, args.spec, stoptime_s=args.stoptime))
    if args.command == "sweep":
        return _print(run_sweep(args.java, args.spec, stoptime_s=args.stoptime))
    if args.command == "optimize":
        return _print(run_optimize(args.java, args.spec, stoptime_s=args.stoptime))
    if args.command == "advise":
        return _print(advise(args.report))
    return _print({"ok": False, "error": "未知命令。"})
