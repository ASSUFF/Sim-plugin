"""Facts from an HFSS run, sweep, or optimize report. Does not launch HFSS."""

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
    s_db = report.get("s_db") if isinstance(report.get("s_db"), dict) else None
    if report.get("rows"):
        facts.extend(_row_facts(report))
    elif s_db:
        facts.append({"name": "single_run", "detail": "这是一次求解。还没有参数扫描，不能把它当成最优解。"})
        facts.append({"name": "s_parameters", "detail": _format_s(s_db)})
    elif report.get("points"):
        facts.extend(_optimize_facts(report))
    assumed = report.get("assumptions")
    if isinstance(assumed, list) and assumed:
        facts.append({"name": "assumptions", "detail": "这次采用的假定：" + "；".join(str(line) for line in assumed)})
    if report.get("error"):
        facts.append({"name": "error", "detail": str(report["error"])})
    if not facts:
        facts.append({"name": "empty", "detail": "报告里没有 S 参数或搜索点，无法提出建议。"})
    return {"ok": True, "launched_solver": False, "report": str(path), "facts": facts}


def _row_facts(report: dict) -> list[dict]:
    rows = [row for row in report.get("rows") or [] if isinstance(row, dict)]
    goal = report.get("goal") if isinstance(report.get("goal"), dict) else {}
    expression = goal.get("expression", "分数")
    sense = goal.get("sense", "max")
    facts = [
        {"name": "goal", "detail": f"目标是让 {expression} 取 {sense}。"},
        {
            "name": "samples",
            "detail": f"已经计算 {len(rows)} 次，上限是 {report.get('max_runs', 8)} 次。",
        },
    ]
    best = report.get("best") if isinstance(report.get("best"), dict) else {}
    results = best.get("results") if isinstance(best.get("results"), dict) else {}
    if isinstance(results.get(expression), (int, float)) and not isinstance(results.get(expression), bool):
        facts.append(
            {
                "name": "best",
                "detail": (
                    f"已计算各次中，{expression}={results[expression]}，"
                    f"参数是 {_format_parameters(best.get('parameters'))}。"
                ),
            }
        )
    if "dB(S(P2,P1))" in results or "dB(S(P1,P1))" in results:
        facts.append({"name": "best_s", "detail": _format_s(results)})
    values = _parameter_values(rows)
    best_value = _first_number(best.get("parameters"))
    if values and best_value is not None and best_value in (min(values), max(values)):
        facts.append(
            {
                "name": "boundary",
                "detail": "目前最好的取值落在已计算区间的端点。扩大搜索区间后，还可能有更好的点。",
            }
        )
    failed = [row for row in rows if not row.get("ok")]
    if failed:
        facts.append({"name": "failed_runs", "detail": f"有 {len(failed)} 次没有得到可用结果。"})
    return facts


def _parameter_values(rows: list[dict]) -> list[float]:
    values = []
    for row in rows:
        number = _first_number(row.get("parameters"))
        if number is not None:
            values.append(number)
    return values


def _first_number(parameters) -> float | None:
    if not isinstance(parameters, dict):
        return None
    for value in parameters.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _format_parameters(parameters) -> str:
    if not isinstance(parameters, dict) or not parameters:
        return "未记录"
    return "，".join(f"{name}={value}" for name, value in parameters.items())


def _optimize_facts(report: dict) -> list[dict]:
    points = [point for point in report.get("points") or [] if isinstance(point, dict)]
    metric = report.get("metric") or {}
    facts = [
        {
            "name": "goal",
            "detail": f"目标是让 {metric.get('key', '分数')} 取 {metric.get('goal', 'max')}。",
        },
        {
            "name": "samples",
            "detail": f"已经计算 {len(points)} 次，上限是 {report.get('max_runs', 8)} 次。参数是 {report.get('parameter', '未记录')}。",
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
        if isinstance(best.get("s_db"), dict):
            facts.append({"name": "best_s", "detail": _format_s(best["s_db"])})
    values = sorted(float(point["value"]) for point in points if isinstance(point.get("value"), (int, float)))
    if best and values and float(best.get("value")) in (values[0], values[-1]):
        facts.append(
            {
                "name": "boundary",
                "detail": "目前最好的取值落在已计算区间的端点。扩大搜索区间后，还可能有更好的点。",
            }
        )
    failed = [point for point in points if not point.get("ok")]
    if failed:
        facts.append({"name": "failed_runs", "detail": f"有 {len(failed)} 次没有得到可用分数。"})
    return facts


def _format_s(s_db: dict) -> str:
    parts = []
    if "frequency_ghz" in s_db:
        parts.append(f"频率 {s_db['frequency_ghz']} GHz")
    if "dB(S(P2,P1))" in s_db:
        parts.append(f"S21 {s_db['dB(S(P2,P1))']} dB")
    if "dB(S(P1,P1))" in s_db:
        parts.append(f"S11 {s_db['dB(S(P1,P1))']} dB")
    return "，".join(parts) if parts else "报告里没有 S21 或 S11。"
