"""Find-and-reproduce case folder. Does not launch a solver and does not download papers."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

SOLVERS = ("comsol", "hfss", "fdtd")


def create_case(folder: str | Path, request: str, solver: str) -> dict:
    if solver not in SOLVERS:
        return _error(f"solver 需要是 {', '.join(SOLVERS)} 之一。")
    text = request.strip()
    if not text:
        return _error("需要写下要寻找的论文范围。")
    root = Path(folder)
    if (root / "request.json").is_file():
        return _error(f"这个文件夹已经有复现记录：{root}")
    root.mkdir(parents=True, exist_ok=True)
    body = {
        "request": text,
        "solver": solver,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    _write(root / "request.json", body)
    return {"ok": True, "launched_solver": False, "folder": str(root), "request": body}


def add_paper(folder: str | Path, citation: dict, pdf: str | Path | None = None) -> dict:
    root = _case(folder)
    if isinstance(root, dict):
        return root
    if not isinstance(citation, dict) or not str(citation.get("title") or "").strip():
        return _error("文献记录需要 title。")
    record = {
        "title": str(citation["title"]).strip(),
        "authors": citation.get("authors") or "",
        "year": citation.get("year"),
        "venue": citation.get("venue") or "",
        "doi": citation.get("doi") or "",
        "url": citation.get("url") or "",
    }
    saved_pdf = None
    if pdf:
        source = Path(pdf)
        if not source.is_file():
            return _error(f"找不到论文文件：{source}")
        target = root / "paper.pdf"
        shutil.copy2(source, target)
        saved_pdf = str(target)
        record["file"] = "paper.pdf"
    _write(root / "citation.json", record)
    return {"ok": True, "launched_solver": False, "folder": str(root), "citation": record, "pdf": saved_pdf}


def set_targets(folder: str | Path, targets: dict) -> dict:
    root = _case(folder)
    if isinstance(root, dict):
        return root
    metrics, error = _metrics(targets)
    if error:
        return _error(error)
    body = {"metrics": metrics}
    _write(root / "targets.json", body)
    return {"ok": True, "launched_solver": False, "folder": str(root), "targets": body}


def set_spec(folder: str | Path, spec: dict) -> dict:
    root = _case(folder)
    if isinstance(root, dict):
        return root
    if not isinstance(spec, dict):
        return _error("仿真规格的顶层需要是 JSON 对象。")
    _write(root / "spec.json", spec)
    return {"ok": True, "launched_solver": False, "folder": str(root), "spec": str(root / "spec.json")}


def status(folder: str | Path) -> dict:
    root = _case(folder)
    if isinstance(root, dict):
        return root
    request = _read(root / "request.json")
    missing = []
    if not (root / "citation.json").is_file():
        missing.append("paper")
    if not (root / "targets.json").is_file():
        missing.append("targets")
    if not (root / "spec.json").is_file():
        missing.append("spec")
    if not (root / "result.json").is_file():
        missing.append("result")
    if not (root / "comparison.json").is_file():
        missing.append("comparison")
    return {
        "ok": True,
        "launched_solver": False,
        "folder": str(root),
        "request": request,
        "missing": missing,
        "ready_to_solve": not {"paper", "targets", "spec"} & set(missing),
        "ready_to_compare": "targets" not in missing,
    }


def compare(folder: str | Path, simulated: dict, report: str | Path | None = None, mapping: dict | None = None) -> dict:
    root = _case(folder)
    if isinstance(root, dict):
        return root
    targets = _read(root / "targets.json")
    if not isinstance(targets, dict):
        return _error("比对前需要先保存论文中的目标值。")
    metrics, error = _metrics(targets)
    if error:
        return _error(error)
    numbers = _simulated_numbers(simulated, report, mapping)
    if isinstance(numbers, dict) and numbers.get("ok") is False:
        return numbers
    rows = [_row(item, numbers) for item in metrics]
    matched = [row for row in rows if row["within"] is True]
    mismatched = [row for row in rows if row["within"] is False]
    unknown = [row for row in rows if row["within"] is None]
    body = {
        "ok": not mismatched and not any(row["simulated"] is None for row in rows),
        "launched_solver": False,
        "folder": str(root),
        "rows": rows,
        "matched": len(matched),
        "mismatched": len(mismatched),
        "unchecked": len(unknown),
        "note": "比对只针对论文里记下的量和这次本地算出的量。它不是论文未给出的参数上的全局最优。",
    }
    _write(root / "result.json", {"metrics": [{"name": row["name"], "simulated": row["simulated"]} for row in rows]})
    _write(root / "comparison.json", body)
    report_path = root / "汇报.md"
    report_path.write_text(_markdown(root, body), encoding="utf-8")
    body["report"] = str(report_path)
    return body


def _simulated_numbers(simulated: dict, report: str | Path | None, mapping: dict | None) -> dict:
    if report is not None:
        loaded = _read(Path(report))
        if not isinstance(loaded, dict):
            return _error(f"找不到仿真报告：{report}")
        if not isinstance(mapping, dict) or not mapping:
            return _error("从仿真报告取值时需要 mapping，把指标名对应到报告里的路径。")
        found = {}
        for name, path in mapping.items():
            if not isinstance(path, str):
                return _error(f"{name} 的报告路径需要是字符串。")
            found[name] = _dig(loaded, path)
        return found
    if not isinstance(simulated, dict):
        return _error("本地结果需要是 JSON 对象。")
    if isinstance(simulated.get("metrics"), list):
        found = {}
        for item in simulated["metrics"]:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                found[item["name"]] = item.get("simulated")
        return found
    return {key: value for key, value in simulated.items() if key != "ok"}


def _row(target: dict, numbers: dict) -> dict:
    name = target["name"]
    paper = target["paper"]
    simulated = numbers.get(name)
    number = _number(simulated)
    tolerance = target.get("tolerance")
    kind = target.get("tolerance_kind") or "abs"
    within = None
    error = None
    if number is None:
        detail = "本地结果里没有这个量。"
    elif isinstance(paper, dict):
        low = float(paper["min"])
        high = float(paper["max"])
        if isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool) and kind == "abs":
            low -= float(tolerance)
            high += float(tolerance)
        within = low <= number <= high
        error = None if within else min(abs(number - low), abs(number - high))
        detail = "落在论文给出的区间内。" if within else "落在论文给出的区间外。"
    else:
        error = number - float(paper)
        if isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool):
            limit = abs(float(paper)) * float(tolerance) if kind == "rel" else abs(float(tolerance))
            within = abs(error) <= limit
            detail = "差值在容差内。" if within else "差值超出容差。"
        else:
            detail = "论文目标没有容差，只记录差值。"
    return {
        "name": name,
        "unit": target.get("unit") or "",
        "paper": paper,
        "simulated": number,
        "error": error,
        "tolerance": tolerance,
        "within": within,
        "detail": detail,
        "note": target.get("note") or "",
    }


def _markdown(root: Path, body: dict) -> str:
    request = _read(root / "request.json") or {}
    citation = _read(root / "citation.json") or {}
    lines = [
        "# 仿真复现汇报",
        "",
        f"需求：{request.get('request', '')}",
        f"求解器：{request.get('solver', '')}",
        f"论文：{citation.get('title', '未记录')}",
    ]
    if citation.get("year"):
        lines.append(f"年份：{citation['year']}")
    if citation.get("doi"):
        lines.append(f"DOI：{citation['doi']}")
    if citation.get("url"):
        lines.append(f"链接：{citation['url']}")
    lines.extend(["", "| 指标 | 论文 | 本地 | 差 | 判断 |", "|---|---|---|---|---|"])
    for row in body["rows"]:
        lines.append(
            "| %s | %s | %s | %s | %s |"
            % (row["name"], _cell(row["paper"]), _cell(row["simulated"]), _cell(row["error"]), row["detail"])
        )
    lines.extend(["", body["note"], ""])
    return "\n".join(lines)


def _metrics(targets: dict) -> tuple[list[dict], str | None]:
    raw = targets.get("metrics") if isinstance(targets, dict) else None
    if not isinstance(raw, list) or not raw:
        return [], "targets.metrics 需要是非空数组。"
    metrics = []
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            return [], "每个论文目标都需要 name。"
        paper = item.get("paper")
        if isinstance(paper, dict):
            try:
                low = float(paper["min"])
                high = float(paper["max"])
            except (KeyError, TypeError, ValueError):
                return [], f"{item['name']} 的区间需要 paper.min 和 paper.max。"
            if high < low:
                return [], f"{item['name']} 的区间上限需要不小于下限。"
            paper = {"min": low, "max": high}
        elif isinstance(paper, bool) or not isinstance(paper, (int, float)):
            return [], f"{item['name']} 的论文值需要是数字或区间。"
        metrics.append(
            {
                "name": str(item["name"]).strip(),
                "paper": paper,
                "unit": item.get("unit") or "",
                "tolerance": item.get("tolerance"),
                "tolerance_kind": item.get("tolerance_kind") or "abs",
                "note": item.get("note") or "",
            }
        )
    return metrics, None


def _dig(value, path: str):
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _plain(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _cell(value):
    if value is None:
        return "—"
    if isinstance(value, dict) and "min" in value and "max" in value:
        return "%s–%s" % (_plain(value["min"]), _plain(value["max"]))
    return _plain(value)


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _case(folder: str | Path) -> Path | dict:
    root = Path(folder)
    if not (root / "request.json").is_file():
        return _error(f"还没有复现文件夹：{root}")
    return root


def _read(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _error(message: str) -> dict:
    return {"ok": False, "launched_solver": False, "stage": "paper", "error": message}
