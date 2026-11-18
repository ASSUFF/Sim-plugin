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
    if report.get("exports") and not report.get("points"):
        facts.append({"name": "single_run", "detail": "这是一次求解。还没有参数扫描，不能把它当成最优解。"})
        facts.append({"name": "exports", "detail": _format_exports(report.get("exports"))})
    if report.get("points"):
        facts.extend(_search_facts(report))
    if report.get("error"):
        facts.append({"name": "error", "detail": str(report["error"])})
    if not facts:
        facts.append({"name": "empty", "detail": "报告里没有监视器结果或搜索点，无法提出建议。"})
    return {"ok": True, "launched_solver": False, "report": str(path), "facts": facts}


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
