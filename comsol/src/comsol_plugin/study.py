"""Parameter sweeps and a bounded coarse-to-fine search.

Each evaluated point is one comsolbatch run. The total is capped at 8 runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from comsol_plugin.batch import run_java
from comsol_plugin.validate import validate_job
from sim_plugin.confirm import rejection

MAX_RUNS = 8


def run_sweep(
    java: str | Path,
    spec: str | Path,
    *,
    stoptime_s: int = 600,
    runs_root: str | Path | None = None,
    install_root: str | Path | None = None,
    runner=None,
) -> dict:
    return _evaluate(
        java,
        spec,
        kind="sweep",
        stoptime_s=stoptime_s,
        runs_root=runs_root,
        install_root=install_root,
        runner=runner,
    )


def run_optimize(
    java: str | Path,
    spec: str | Path,
    *,
    stoptime_s: int = 600,
    runs_root: str | Path | None = None,
    install_root: str | Path | None = None,
    runner=None,
) -> dict:
    return _evaluate(
        java,
        spec,
        kind="optimize",
        stoptime_s=stoptime_s,
        runs_root=runs_root,
        install_root=install_root,
        runner=runner,
    )


def _evaluate(java, spec, *, kind, stoptime_s, runs_root, install_root, runner) -> dict:
    spec_path = Path(spec)
    checked = validate_job(java, spec_path)
    if not checked["ok"]:
        checked["stage"] = "validate"
        return checked
    try:
        spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _spec_error(f"规格不是合法 JSON：{exc.lineno} 行。")
    if not isinstance(spec_data, dict):
        return _spec_error("规格的顶层需要是 JSON 对象。")
    if runner is None:
        rejected = rejection(spec_data)
        if rejected:
            return rejected
    goal = spec_data.get("goal")
    if not isinstance(goal, dict) or goal.get("sense") not in ("min", "max"):
        return _spec_error("扫描和寻优都需要 goal.sense 为 min 或 max。")
    expression = goal.get("expression")
    if not isinstance(expression, str):
        return _spec_error("goal.expression 需要是结果名。")

    try:
        plan = _plan(spec_data, kind)
    except ValueError as exc:
        return _spec_error(str(exc))

    source = Path(java).resolve()
    root = Path(runs_root) if runs_root is not None else source.parents[1] / "runs"
    folder = root / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{source.stem}_{kind}"
    folder.mkdir(parents=True, exist_ok=True)
    run_kwargs = {"runs_root": folder, "stoptime_s": stoptime_s, "install_root": install_root}
    if runner is not None:
        run_kwargs["runner"] = runner

    rows: list[dict] = []

    def evaluate(updates: dict[str, str], x: float | None = None) -> bool:
        point_spec = _point_spec(spec_data, updates)
        point_path = folder / f"point_{len(rows) + 1}.json"
        point_path.write_text(json.dumps(point_spec, ensure_ascii=False, indent=2), encoding="utf-8")
        result = run_java(java, point_path, **run_kwargs)
        row = {
            "parameters": updates,
            "ok": bool(result.get("ok")),
            "results": result.get("results", {}),
            "work_dir": result.get("work_dir"),
            "error": result.get("error"),
        }
        if x is not None:
            row["x"] = x
        rows.append(row)
        return row["ok"]

    if kind == "sweep":
        for updates in plan:
            if not evaluate(updates):
                break
    else:
        name, low, high, unit, max_runs = plan
        xs = _linspace(low, high, min(3, max_runs))
        for x in xs:
            if not evaluate({name: _format(x, unit)}, x):
                break
        while len(rows) < max_runs and rows[-1]["ok"]:
            nxt = _next_x(rows, expression, goal["sense"], high - low)
            if nxt is None:
                break
            if not evaluate({name: _format(nxt, unit)}, nxt):
                break

    successful = [row for row in rows if row["ok"] and _numeric(row["results"].get(expression)) is not None]
    best = _best(successful, expression, goal["sense"])
    report = {
        "ok": bool(rows) and all(row["ok"] for row in rows) and best is not None,
        "stage": kind,
        "launched_solver": bool(rows),
        "goal": {"expression": expression, "sense": goal["sense"]},
        "rows": rows,
        "best": best,
        "run_count": len(rows),
        "max_runs": MAX_RUNS,
        "work_dir": str(folder),
        "note": "best 是这次已计算各次里按目标选出的结果。它不是没有计算过的参数上的全局最优。",
    }
    if best is None and rows and rows[-1].get("error"):
        report["error"] = rows[-1]["error"]
    elif best is None:
        report["error"] = f"结果里没有可用的数值 {expression}。"
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _plan(spec: dict, kind: str):
    if kind == "sweep":
        grid = spec.get("sweep")
        if not isinstance(grid, dict) or not grid:
            raise ValueError("sweep 需要是非空对象，键是参数名，值是待计算的取值数组。")
        names = list(grid)
        columns: list[list[str]] = []
        for name, values in grid.items():
            if not isinstance(values, list) or not 2 <= len(values) <= MAX_RUNS:
                raise ValueError(f"参数 {name} 的扫描取值需要 2 到 {MAX_RUNS} 个。")
            column = []
            for value in values:
                if not isinstance(value, str) or not value.strip() or '"' in value:
                    raise ValueError(f"参数 {name} 的每个扫描取值都需要是不含双引号的非空字符串。")
                column.append(value)
            columns.append(column)
        points = _product(names, columns)
        if len(points) > MAX_RUNS:
            raise ValueError(f"扫描组合有 {len(points)} 个，超过上限 {MAX_RUNS}。请减少取值。")
        return points

    opt = spec.get("optimize")
    if not isinstance(opt, dict):
        raise ValueError("optimize 需要是对象。")
    name = opt.get("parameter")
    parameters = spec.get("parameters") or {}
    if not isinstance(name, str) or name not in parameters:
        raise ValueError("optimize.parameter 需要是 parameters 里的一个参数名。")
    try:
        low = float(opt["min"])
        high = float(opt["max"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("optimize.min 和 optimize.max 需要是数字。") from exc
    if high <= low:
        raise ValueError("optimize.max 需要大于 optimize.min。")
    unit = opt.get("unit")
    if not isinstance(unit, str) or not unit.strip() or '"' in unit:
        raise ValueError("optimize.unit 需要是不含双引号的单位，例如 K。")
    max_runs = int(opt.get("max_runs", MAX_RUNS))
    if not 2 <= max_runs <= MAX_RUNS:
        raise ValueError(f"optimize.max_runs 需要在 2 到 {MAX_RUNS} 之间。")
    return name, low, high, unit.strip(), max_runs


def _next_x(rows: list[dict], expression: str, sense: str, span: float) -> float | None:
    ranked = [row for row in rows if "x" in row and _numeric(row["results"].get(expression)) is not None]
    if not ranked:
        return None
    best = min(ranked, key=lambda row: _numeric(row["results"][expression]))
    if sense == "max":
        best = max(ranked, key=lambda row: _numeric(row["results"][expression]))
    xs = sorted(float(row["x"]) for row in rows if "x" in row)
    best_x = float(best["x"])
    lower = [x for x in xs if x < best_x - span * 1e-9]
    upper = [x for x in xs if x > best_x + span * 1e-9]
    candidates = []
    if lower:
        candidates.append((best_x + lower[-1]) / 2)
    if upper:
        candidates.append((best_x + upper[0]) / 2)
    for candidate in candidates:
        if all(abs(candidate - x) > span * 1e-6 for x in xs):
            return candidate
    return None


def _best(rows: list[dict], expression: str, sense: str) -> dict | None:
    usable = [row for row in rows if _numeric(row["results"].get(expression)) is not None]
    if not usable:
        return None

    def score(row: dict) -> float:
        return _numeric(row["results"][expression])

    chosen = min(usable, key=score) if sense == "min" else max(usable, key=score)
    published = {key: value for key, value in chosen.items() if key != "x"}
    return published


def _point_spec(spec: dict, updates: dict[str, str]) -> dict:
    point = json.loads(json.dumps(spec))
    point.pop("sweep", None)
    point.pop("optimize", None)
    parameters = point.setdefault("parameters", {})
    for name, value in updates.items():
        current = parameters.get(name)
        if isinstance(current, dict):
            current["value"] = value
        else:
            parameters[name] = {"value": value}
    return point


def _product(names: list[str], columns: list[list[str]]) -> list[dict[str, str]]:
    points = [{}]
    for name, column in zip(names, columns):
        points = [{**point, name: value} for point in points for value in column]
    return points


def _linspace(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [low]
    return [low + (high - low) * index / (count - 1) for index in range(count)]


def _format(value: float, unit: str) -> str:
    return f"{value:.8g}[{unit}]"


def _numeric(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spec_error(message: str) -> dict:
    return {"ok": False, "stage": "spec", "launched_solver": False, "error": message}
