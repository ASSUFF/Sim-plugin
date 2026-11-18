"""Coarse-to-fine search of one Lumerical object property. At most 8 solves."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path

from lumerical_fdtd.study import score_fdtd_payload

from fdtd_plugin.backend import _prepare_env, doctor, run
from sim_plugin.confirm import rejection

MAX_RUNS = 8


def optimize(study: dict) -> dict:
    try:
        plan = _plan(study)
    except ValueError as exc:
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": str(exc)}
    rejected = rejection(study)
    if rejected:
        return rejected
    status = doctor()
    if not status.get("installed"):
        return {
            "ok": False,
            "launched_solver": False,
            "stage": "install",
            "error": status.get("error") or "本机没有找到 Lumerical FDTD。",
        }
    return _search(plan, lambda spec: run(spec, check_confirmation=False))


def optimize_with(study: dict, evaluate) -> dict:
    """Same search, with a caller-supplied evaluator. Used by tests."""
    try:
        plan = _plan(study)
    except ValueError as exc:
        return {"ok": False, "launched_solver": False, "stage": "spec", "error": str(exc)}
    return _search(plan, evaluate)


def _search(plan: dict, evaluate) -> dict:
    _prepare_env()
    folder = Path(os.environ["LUMERICAL_FDTD_RUNS"]) / (
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{plan['name']}_optimize"
    )
    folder.mkdir(parents=True, exist_ok=True)
    points: list[dict] = []
    launched = False

    def consider(value: float) -> bool:
        nonlocal launched
        spec = copy.deepcopy(plan["base"])
        spec["name"] = f"{plan['name']}_{value:.8g}"
        spec.setdefault("overrides", []).append(
            {"object": plan["object"], "property": plan["property"], "value": value}
        )
        result = evaluate(spec)
        launched = launched or bool(result.get("launched_solver"))
        score = score_fdtd_payload(result, plan["metric"])
        points.append(
            {
                "value": value,
                "ok": bool(result.get("ok")) and score is not None,
                "score": score,
                "exports": result.get("exports"),
                "run_dir": result.get("run_dir"),
                "error": result.get("error"),
            }
        )
        return points[-1]["ok"]

    for value in _linspace(plan["low"], plan["high"], min(3, plan["max_runs"])):
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
        "parameter": {"object": plan["object"], "property": plan["property"]},
        "metric": plan["metric"],
        "points": points,
        "best": best,
        "run_count": len(points),
        "max_runs": MAX_RUNS,
        "work_dir": str(folder),
        "note": "best 是这次已计算各次里按目标选出的结果。它不是没有计算过的取值上的全局最优。",
    }
    if best is None and points and points[-1].get("error"):
        report["error"] = points[-1]["error"]
    elif best is None:
        report["error"] = "结果里没有可用的监视器分数。"
    report_path = folder / "report.json"
    report["report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _plan(study: dict) -> dict:
    if not isinstance(study, dict):
        raise ValueError("规格的顶层需要是 JSON 对象。")
    base = study.get("base")
    if not isinstance(base, dict):
        raise ValueError("base 需要是一次 FDTD 规格。")
    parameter = study.get("parameter") or {}
    obj = parameter.get("object")
    prop = parameter.get("property")
    if not isinstance(obj, str) or not obj.strip() or not isinstance(prop, str) or not prop.strip():
        raise ValueError("parameter.object 和 parameter.property 都需要是非空字符串。")
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
    return {
        "base": base,
        "object": obj.strip(),
        "property": prop.strip(),
        "low": low,
        "high": high,
        "max_runs": max_runs,
        "goal": goal,
        "metric": metric,
        "name": str(study.get("name") or base.get("name") or "fdtd"),
    }


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
    lower = [value for value in xs if value < best_x - span * 1e-12]
    upper = [value for value in xs if value > best_x + span * 1e-12]
    candidates = []
    if lower:
        candidates.append((best_x + lower[-1]) / 2)
    if upper:
        candidates.append((best_x + upper[0]) / 2)
    for candidate in candidates:
        if all(abs(candidate - value) > span * 1e-9 for value in xs):
            return candidate
    return None


def _best(points: list[dict], goal: str) -> dict | None:
    ranked = [point for point in points if isinstance(point.get("score"), (int, float)) and not isinstance(point.get("score"), bool)]
    if not ranked:
        return None
    return min(ranked, key=lambda point: point["score"]) if goal == "min" else max(ranked, key=lambda point: point["score"])
