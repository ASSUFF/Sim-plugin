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
from comsol_plugin.project import inspect_mph, set_mph
from comsol_plugin.study import run_optimize, run_sweep
from comsol_plugin.validate import validate_job
from hfss_plugin.advise import advise as hfss_advise
from hfss_plugin.backend import doctor as hfss_doctor
from hfss_plugin.backend import prepare as hfss_prepare
from hfss_plugin.backend import inspect as hfss_inspect
from hfss_plugin.backend import run as hfss_run
from hfss_plugin.backend import set_project as hfss_set
from hfss_plugin.backend import sweep as hfss_sweep
from hfss_plugin.backend import validate as hfss_validate
from hfss_plugin.optimize import optimize as hfss_optimize
from fdtd_plugin.advise import advise as fdtd_advise
from fdtd_plugin.backend import doctor as fdtd_doctor
from fdtd_plugin.backend import prepare as fdtd_prepare
from fdtd_plugin.backend import inspect as fdtd_inspect
from fdtd_plugin.backend import run as fdtd_run
from fdtd_plugin.backend import set_project as fdtd_set
from fdtd_plugin.backend import sweep as fdtd_sweep
from fdtd_plugin.backend import validate as fdtd_validate
from fdtd_plugin.optimize import optimize as fdtd_optimize
from sim_plugin.confirm import confirm, rejection
from sim_plugin.paper import add_paper, compare, create_case, set_spec, set_targets, status as paper_status


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


def _paper(args) -> int:
    if args.command == "new":
        return _print(create_case(args.folder, args.request, args.case_solver))
    if args.command == "status":
        return _print(paper_status(args.folder))
    if args.command == "add":
        citation = _read_json(args.citation)
        if citation.get("ok") is False and "title" not in citation:
            return _print(citation)
        return _print(add_paper(args.folder, citation, args.pdf))
    if args.command == "targets":
        targets = _read_json(args.targets)
        if targets.get("ok") is False and "metrics" not in targets:
            return _print(targets)
        return _print(set_targets(args.folder, targets))
    if args.command == "spec":
        spec = _read_json(args.spec)
        if spec.get("ok") is False and "stage" not in spec and "name" not in spec and "parameters" not in spec:
            return _print(spec)
        return _print(set_spec(args.folder, spec))
    simulated = _read_json(args.result) if args.result else {}
    if args.result and simulated.get("ok") is False and "metrics" not in simulated:
        return _print(simulated)
    mapping = None
    if args.map:
        mapping = _read_json(args.map)
        if mapping.get("ok") is False:
            return _print(mapping)
    return _print(compare(args.folder, simulated, report=args.report, mapping=mapping))


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

    owned = commands.add_parser("inspect", help="List parameters in an existing .mph without solving")
    owned.add_argument("--project", required=True)
    owned_set = commands.add_parser("set", help="Change parameters in a copy of an existing .mph")
    owned_set.add_argument("--project", required=True)
    owned_set.add_argument("--spec", required=True)
    run = commands.add_parser("run", help="Compile a Java model, or solve a copy of an existing .mph")
    run.add_argument("--java")
    run.add_argument("--project")
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
    confirm_cmd = commands.add_parser("confirm", help="Stamp a spec after its checklist is complete. Does not launch COMSOL")
    confirm_cmd.add_argument("--spec", required=True)

    hfss = solvers.add_parser("hfss")
    hfss_commands = hfss.add_subparsers(dest="command", required=True)
    hfss_commands.add_parser("doctor", help="Report the HFSS install without launching it")
    hfss_inspect_cmd = hfss_commands.add_parser("inspect", help="List objects in a copy of an existing .aedt")
    hfss_inspect_cmd.add_argument("--project", required=True)
    hfss_set_cmd = hfss_commands.add_parser("set", help="Write variables into a copy of an existing .aedt")
    hfss_set_cmd.add_argument("--project", required=True)
    hfss_set_cmd.add_argument("--spec", required=True)
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
    hfss_confirm = hfss_commands.add_parser("confirm", help="Stamp an HFSS spec. Does not launch Electronics Desktop")
    hfss_confirm.add_argument("--spec", required=True)

    fdtd = solvers.add_parser("fdtd")
    fdtd_commands = fdtd.add_subparsers(dest="command", required=True)
    fdtd_commands.add_parser("doctor", help="Report whether Lumerical FDTD is installed")
    fdtd_inspect_cmd = fdtd_commands.add_parser("inspect", help="List objects in a copy of an existing .fsp")
    fdtd_inspect_cmd.add_argument("--project", required=True)
    fdtd_set_cmd = fdtd_commands.add_parser("set", help="Apply overrides to a copy of an existing .fsp")
    fdtd_set_cmd.add_argument("--project", required=True)
    fdtd_set_cmd.add_argument("--spec", required=True)
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
    fdtd_confirm = fdtd_commands.add_parser("confirm", help="Stamp an FDTD spec. Does not launch Lumerical")
    fdtd_confirm.add_argument("--spec", required=True)

    paper = solvers.add_parser("paper")
    paper_commands = paper.add_subparsers(dest="command", required=True)
    paper_new = paper_commands.add_parser("new", help="Create a folder for one paper reproduction. Does not search or solve")
    paper_new.add_argument("--folder", required=True)
    paper_new.add_argument("--solver", required=True, choices=["comsol", "hfss", "fdtd"], dest="case_solver")
    paper_new.add_argument("--request", required=True)
    paper_add = paper_commands.add_parser("add", help="Save a citation and an optional PDF into the case folder")
    paper_add.add_argument("--folder", required=True)
    paper_add.add_argument("--citation", required=True)
    paper_add.add_argument("--pdf")
    paper_targets = paper_commands.add_parser("targets", help="Save the numerical results stated by the paper")
    paper_targets.add_argument("--folder", required=True)
    paper_targets.add_argument("--json", required=True, dest="targets")
    paper_spec = paper_commands.add_parser("spec", help="Save the solver spec extracted from the paper")
    paper_spec.add_argument("--folder", required=True)
    paper_spec.add_argument("--spec", required=True)
    paper_state = paper_commands.add_parser("status", help="List which reproduction steps are still missing")
    paper_state.add_argument("--folder", required=True)
    paper_compare = paper_commands.add_parser("compare", help="Compare local results with the paper. Does not launch a solver")
    paper_compare.add_argument("--folder", required=True)
    paper_compare.add_argument("--result")
    paper_compare.add_argument("--report")
    paper_compare.add_argument("--map")

    args = parser.parse_args(argv)
    if args.solver == "paper":
        return _paper(args)
    if args.solver == "hfss":
        if args.command == "doctor":
            return _print(hfss_doctor())
        if args.command == "advise":
            return _print(hfss_advise(args.report))
        if args.command == "confirm":
            spec = _read_json(args.spec)
            if spec.get("ok") is False and "error" in spec and "stage" not in spec:
                return _print(spec)
            return _print(confirm(spec))
        if args.command == "inspect":
            return _print(hfss_inspect(args.project))
        if args.command == "set":
            spec = _read_json(args.spec)
            if spec.get("ok") is False and "error" in spec:
                return _print(spec)
            spec["project"] = args.project
            return _print(hfss_set(spec))
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
        if args.command == "confirm":
            spec = _read_json(args.spec)
            if spec.get("ok") is False and "error" in spec and "stage" not in spec:
                return _print(spec)
            return _print(confirm(spec))
        if args.command == "inspect":
            return _print(fdtd_inspect(args.project))
        if args.command == "set":
            spec = _read_json(args.spec)
            if spec.get("ok") is False and "error" in spec:
                return _print(spec)
            spec["project"] = args.project
            return _print(fdtd_set(spec))
        spec = _read_json(args.spec)
        if isinstance(spec, dict) and spec.get("ok") is False:
            return _print(spec)
        if args.command == "validate":
            return _print(fdtd_validate(spec))
        if args.command == "prepare":
            return _print(fdtd_prepare(spec))
        if args.command == "run":
            return _print(fdtd_run(spec, spec_dir=Path(args.spec).parent))
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
    if args.command == "inspect":
        return _print(inspect_mph(args.project))
    if args.command == "set":
        spec = _read_json(args.spec)
        if spec.get("ok") is False and "error" in spec:
            return _print(spec)
        return _print(set_mph(args.project, spec.get("parameters") or {}, study=spec.get("study"), solve=False))
    if args.command == "validate":
        return _print(validate_job(args.java, args.spec))
    if args.command == "run" and args.project:
        spec = _read_json(args.spec) if args.spec else {}
        if spec.get("ok") is False and "error" in spec:
            return _print(spec)
        rejected = rejection(spec)
        if rejected:
            return _print(rejected)
        return _print(
            set_mph(
                args.project,
                spec.get("parameters") or {},
                study=spec.get("study"),
                solve=True,
                runs_root=None,
            )
        )
    if args.command == "run":
        if not args.java:
            return _print({"ok": False, "launched_solver": False, "error": "run 需要 --java，或用 --project 指定已有的 .mph。"})
        return _print(run_java(args.java, args.spec, stoptime_s=args.stoptime, check_confirmation=True))
    if args.command == "sweep":
        return _print(run_sweep(args.java, args.spec, stoptime_s=args.stoptime))
    if args.command == "optimize":
        return _print(run_optimize(args.java, args.spec, stoptime_s=args.stoptime))
    if args.command == "advise":
        return _print(advise(args.report))
    if args.command == "confirm":
        spec = _read_json(args.spec)
        if spec.get("ok") is False and "error" in spec and "stage" not in spec:
            return _print(spec)
        return _print(confirm(spec))
    return _print({"ok": False, "error": "未知命令。"})
