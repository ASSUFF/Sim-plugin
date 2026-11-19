"""Collect checkable facts from a run, sweep, or optimize report.

The facts are input for the AI. This module does not write the advice paragraph.
"""

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
    goal = report.get("goal")
    if isinstance(goal, dict):
        facts.append(
            {
                "name": "goal",
                "detail": f"目标是让 {goal.get('expression')} 取 {goal.get('sense')}。",
            }
        )
    if report.get("rows"):
        facts.extend(_study_facts(report))
    elif report.get("results"):
        facts.append({"name": "single_run", "detail": "这是一次求解。还没有参数扫描，不能把它当成最优解。"})
        facts.append({"name": "results", "detail": _format_results(report.get("results"))})
    assumed = report.get("assumptions")
    if isinstance(assumed, list) and assumed:
        facts.append({"name": "assumptions", "detail": "这次采用的假定：" + "；".join(str(line) for line in assumed)})
    if report.get("error"):
        facts.append({"name": "error", "detail": str(report["error"])})
    log_path = _log_path(report)
    if log_path is not None:
        facts.extend(_log_facts(log_path))
    if not facts:
        facts.append({"name": "empty", "detail": "报告里没有结果、目标或日志，无法提出仿真建议。"})
    return {"ok": True, "launched_solver": False, "report": str(path), "facts": facts}


def _study_facts(report: dict) -> list[dict]:
    rows = report.get("rows") or []
    facts = [
        {
            "name": "samples",
            "detail": f"已经计算 {len(rows)} 次，上限是 {report.get('max_runs', 8)} 次。",
        }
    ]
    best = report.get("best") or {}
    expression = (report.get("goal") or {}).get("expression")
    if best.get("results") and expression in best["results"]:
        facts.append(
            {
                "name": "best",
                "detail": (
                    f"已计算各次中，{expression}={best['results'][expression]}，"
                    f"参数是 {_format_parameters(best.get('parameters'))}。"
                ),
            }
        )
    xs = sorted(row["x"] for row in rows if isinstance(row, dict) and isinstance(row.get("x"), (int, float)))
    best_x = None
    for row in rows:
        if row.get("work_dir") and best.get("work_dir") and row.get("work_dir") == best.get("work_dir"):
            best_x = row.get("x")
    if xs and isinstance(best_x, (int, float)) and (best_x == xs[0] or best_x == xs[-1]):
        facts.append(
            {
                "name": "boundary",
                "detail": "目前最好的取值落在已计算区间的端点。扩大搜索区间后，还可能有更好的点。",
            }
        )
    failed = [row for row in rows if isinstance(row, dict) and not row.get("ok")]
    if failed:
        facts.append({"name": "failed_runs", "detail": f"有 {len(failed)} 次没有得到完整结果。"})
    return facts


def _log_facts(path: Path) -> list[dict]:
    if not path.is_file():
        return [{"name": "log_missing", "detail": f"没有找到批处理日志 {path}。"}]
    text = path.read_text(encoding="utf-8", errors="replace")
    facts = []
    if "100 %" in text or "100%" in text:
        facts.append({"name": "progress", "detail": "批处理日志里有 100% 进度。"})
    error_lines = [
        line.strip()
        for line in text.splitlines()
        if any(token in line.lower() for token in ("error", "exception", "failed", "singular"))
    ]
    if error_lines:
        facts.append({"name": "log_errors", "detail": "日志里有这些异常行：" + " | ".join(error_lines[-5:])})
    else:
        facts.append({"name": "log_errors", "detail": "批处理日志里没有 error、exception、failed 或 singular。"})
    return facts


def _log_path(report: dict) -> Path | None:
    if report.get("batch_log"):
        return Path(report["batch_log"])
    work = report.get("best", {}).get("work_dir") if isinstance(report.get("best"), dict) else None
    if not work:
        work = report.get("work_dir")
    if not work:
        return None
    logs = sorted(Path(work).glob("*_batch.log"))
    return logs[0] if logs else None


def _format_results(results: dict) -> str:
    return "，".join(f"{name}={value}" for name, value in results.items())


def _format_parameters(parameters: dict | None) -> str:
    if not parameters:
        return "未记录"
    return "，".join(f"{name}={value}" for name, value in parameters.items())
