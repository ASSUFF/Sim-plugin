"""Facts from an FDTD run or search report. Does not launch the solver."""

from __future__ import annotations

import json
from pathlib import Path


def advise(report_path: str | Path) -> dict:
    path = Path(report_path)
    if not path.is_file():
        return {"ok": False, "launched_solver": False, "error": f"找不到报告：{path}", "facts": []}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "launched_solver": False, "error": f"报告不是合法 JSON：{exc.lineno} 行。", "facts": []}
    if not isinstance(report, dict):
        return {"ok": False, "launched_solver": False, "error": "报告的顶层需要是 JSON 对象。", "facts": []}

    facts: list[dict] = []
    if report.get("rows"):
        facts.extend(_row_facts(report))
    elif report.get("exports") and not report.get("points"):
        facts.append({"name": "single_run", "detail": "这是一次求解。还没有参数扫描，不能把它当成最优解。"})
        facts.append({"name": "exports", "detail": _format_exports(report.get("exports"))})
    elif report.get("points"):
        facts.extend(_search_facts(report))
    assumed = report.get("assumptions")
    if isinstance(assumed, list) and assumed:
        facts.append({"name": "assumptions", "detail": "这次采用的假定：" + "；".join(str(line) for line in assumed)})
    if report.get("error"):
        facts.append({"name": "error", "detail": str(report["error"])})
    if not facts:
        facts.append({"name": "empty", "detail": "报告里没有监视器结果或搜索点，无法提出建议。"})
    return {"ok": True, "launched_solver": False, "report": str(path), "facts": facts}


def _row_facts(report: dict) -> list[dict]:
    rows = [row for row in report.get("rows") or [] if isinstance(row, dict)]
    goal = report.get("goal") if isinstance(report.get("goal"), dict) else {}
    expression = goal.get("expression", "T")
    sense = goal.get("sense", "max")
    facts = [
        {"name": "goal", "detail": f"目标是让 {expression} 取 {sense}。"},
        {"name": "samples", "detail": f"已经计算 {len(rows)} 次，上限是 {report.get('max_runs', 8)} 次。"},
    ]
    best = report.get("best") if isinstance(report.get("best"), dict) else {}
    results = best.get("results") if isinstance(best.get("results"), dict) else {}
    if isinstance(results.get(expression), (int, float)) and not isinstance(results.get(expression), bool):
        parameters = best.get("parameters") if isinstance(best.get("parameters"), dict) else {}
        shown = "，".join(f"{name}={value}" for name, value in parameters.items()) or "未记录"
        facts.append({"name": "best", "detail": f"已计算各次中，{expression}={results[expression]}，参数是 {shown}。"})
    values = []
    for row in rows:
        parameters = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
        for value in parameters.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
                break
    best_parameters = best.get("parameters") if isinstance(best.get("parameters"), dict) else {}
    best_value = next(
        (float(value) for value in best_parameters.values() if isinstance(value, (int, float)) and not isinstance(value, bool)),
        None,
    )
    if values and best_value is not None and best_value in (min(values), max(values)):
        facts.append(
            {
                "name": "boundary",
                "detail": "目前最好的取值落在已计算区间的端点。扩大搜索区间后，还可能有更好的点。",
            }
        )
    return facts


def _search_facts(report: dict) -> list[dict]:
    points = [point for point in report.get("points") or [] if isinstance(point, dict)]
    metric = report.get("metric") or {}
    parameter = report.get("parameter") or {}
    facts = [
        {
            "name": "goal",
            "detail": f"目标是让 {metric.get('export', '监视器分数')} 取 {metric.get('goal', 'max')}。",
        },
        {
            "name": "samples",
            "detail": (
                f"已经计算 {len(points)} 次，上限是 {report.get('max_runs', 8)} 次。"
                f"对象 {parameter.get('object', '未记录')} 的属性 {parameter.get('property', '未记录')}。"
            ),
        },
    ]
    best = report.get("best") if isinstance(report.get("best"), dict) else None
    if best and isinstance(best.get("score"), (int, float)):
        facts.append(
            {
                "name": "best",
                "detail": f"已计算各次中，分数 {best['score']} 出现在取值 {best.get('value')}。",
            }
        )
    values = sorted(float(point["value"]) for point in points if isinstance(point.get("value"), (int, float)))
    if best and values and float(best.get("value")) in (values[0], values[-1]):
        facts.append(
            {
                "name": "boundary",
                "detail": "目前最好的取值落在已计算区间的端点。扩大搜索区间后，还可能有更好的点。",
            }
        )
    return facts


def _format_exports(exports) -> str:
    if not isinstance(exports, list) or not exports:
        return "报告里没有监视器导出。"
    names = [str(item.get("name")) for item in exports if isinstance(item, dict) and item.get("name")]
    return "导出：" + "，".join(names) if names else "报告里没有监视器名称。"
