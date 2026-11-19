"""Coarse-to-fine search for one numeric HFSS parameter.

Each candidate is one existing-engine solve. The total is capped at 8.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

from hfss_plugin.backend import _protected_project, _runs_root, license_error, run
from sim_plugin.checklist import rejection as checklist_rejection
from sim_plugin.confirm import apply_assumptions, assumption_lines

MAX_RUNS = 8


def optimize(study: dict, *, runner=None, python=None, src=None) -> dict:
    try:
        plan = _plan(study)
    except ValueError as exc:
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": str(exc)}
    blocked = _protected_project(plan["base"])
    if blocked:
        return blocked
    use_real_runner = runner is None
    assumed = assumption_lines(study)
    if use_real_runner:
        from sim_plugin.confirm import rejection

        rejected = rejection(study)
        if rejected:
            return rejected
        failed = checklist_rejection(study, "hfss")
        if failed:
            return failed
        message = license_error()
        if message:
            return {"ok": False, "launched_solver": False, "stage": "license", "error": message}

    def evaluate(spec: dict) -> dict:
        kwargs = {"check_confirmation": False, "preflight": False}
        if runner is not None:
            kwargs["runner"] = runner
        if python is not None:
            kwargs["python"] = python
        if src is not None:
            kwargs["src"] = src
        result = run(spec, **kwargs)
        if isinstance(result, dict):
            apply_assumptions(result, assumed)
        return result

    folder = _runs_root() / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{plan['name']}_optimize"
    folder.mkdir(parents=True, exist_ok=True)
    points: list[dict] = []
    xs = _linspace(plan["low"], plan["high"], min(3, plan["max_runs"]))
    launched = False

    def consider(value: float) -> bool:
        nonlocal launched
        spec = copy.deepcopy(plan["base"])
        spec["name"] = f"{plan['name']}_{value:.8g}"
        _assign(spec, plan["path"], value)
        result = evaluate(spec)
        launched = launched or bool(result.get("launched_solver"))
        score = None
        s_db = result.get("s_db") if isinstance(result.get("s_db"), dict) else {}
        raw = s_db.get(plan["key"])
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            score = float(raw)
        points.append(
            {
                "value": value,
                "ok": bool(result.get("ok")) and score is not None,
                "score": score,
                "s_db": s_db,
                "run_dir": result.get("run_dir"),
                "error": result.get("error"),
            }
        )
        return points[-1]["ok"]

    for value in xs:
        if not consider(value):
            break
    while len(points) < plan["max_runs"] and points and points[-1]["ok"]:
        nxt = _next_value(points, plan["goal"], plan["high"] - plan["low"])
        if nxt is None:
            break
        if not consider(nxt):
            break

    best = _best(points, plan["goal"])
    report = {
        "ok": bool(points) and all(point["ok"] for point in points) and best is not None,
        "stage": "optimize",
        "launched_solver": launched,
        "parameter": plan["path"],
        "metric": {"key": plan["key"], "goal": plan["goal"]},
        "points": points,
        "best": best,
        "run_count": len(points),
        "max_runs": MAX_RUNS,
        "work_dir": str(folder),
        "assumptions": assumed,
        "note": "best 是这次已计算长度里按目标选出的结果。它不是没有计算过的长度上的全局最优。",
    }
    if best is None and points and points[-1].get("error"):
        report["error"] = points[-1]["error"]
    elif best is None:
        report["error"] = f"结果里没有可用的 {plan['key']}。"
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _plan(study: dict) -> dict:
    if not isinstance(study, dict):
        raise ValueError("规格的顶层需要是 JSON 对象。")
    base = study.get("base")
    if not isinstance(base, dict):
        raise ValueError("base 需要是一次 HFSS 规格。")
    parameter = study.get("parameter") or {}
    path = parameter.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("parameter.path 需要是规格里的数值路径，例如 geometry.length_m。")
    opt = study.get("optimize")
    if not isinstance(opt, dict):
        raise ValueError("optimize 需要是对象。")
    try:
        low = float(opt["min"])
        high = float(opt["max"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("optimize.min 和 optimize.max 需要是数字。") from exc
    if high <= low:
        raise ValueError("optimize.max 需要大于 optimize.min。")
    max_runs = int(opt.get("max_runs", MAX_RUNS))
    if not 2 <= max_runs <= MAX_RUNS:
        raise ValueError(f"optimize.max_runs 需要在 2 到 {MAX_RUNS} 之间。")
    metric = study.get("metric") or {}
    goal = metric.get("goal", "max")
    if goal not in ("min", "max"):
        raise ValueError("metric.goal 只能是 min 或 max。")
    key = metric.get("key", "dB(S(P2,P1))")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("metric.key 需要是 S 参数字段名。")
    name = str(study.get("name") or base.get("name") or "hfss")
    return {
        "base": base,
        "path": path.strip(),
        "low": low,
        "high": high,
        "max_runs": max_runs,
        "goal": goal,
        "key": key,
        "name": name,
    }


def _assign(spec: dict, path: str, value: float) -> None:
    node = spec
    parts = [part for part in path.split(".") if part]
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _linspace(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [low]
    return [low + (high - low) * index / (count - 1) for index in range(count)]


def _next_value(points: list[dict], goal: str, span: float) -> float | None:
    ranked = [point for point in points if isinstance(point.get("score"), (int, float))]
    if not ranked:
        return None
    best = min(ranked, key=lambda point: point["score"]) if goal == "min" else max(ranked, key=lambda point: point["score"])
    xs = sorted(float(point["value"]) for point in points)
    best_x = float(best["value"])
    lower = [value for value in xs if value < best_x - span * 1e-9]
    upper = [value for value in xs if value > best_x + span * 1e-9]
    candidates = []
    if lower:
        candidates.append((best_x + lower[-1]) / 2)
    if upper:
        candidates.append((best_x + upper[0]) / 2)
    for candidate in candidates:
        if all(abs(candidate - value) > span * 1e-6 for value in xs):
            return candidate
    return None


def _best(points: list[dict], goal: str) -> dict | None:
    ranked = [point for point in points if isinstance(point.get("score"), (int, float)) and not isinstance(point.get("score"), bool)]
    if not ranked:
        return None
    return min(ranked, key=lambda point: point["score"]) if goal == "min" else max(ranked, key=lambda point: point["score"])
