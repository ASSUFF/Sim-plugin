"""Stamp a spec after its checklist is complete. Solving commands require that stamp.

confirm does not launch a solver. The spec it returns is the object run, sweep,
and optimize accept. A later edit changes the token, so the solver stays off
until confirm is called again.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

CORE_ITEMS = ("frequency", "region", "geometry", "material", "accuracy", "stop", "outputs")
STUDY_ITEMS = ("goal", "range", "limit")


def confirm(spec: object) -> dict:
    """Check the checklist and return the spec a solver command can accept."""
    if not isinstance(spec, dict):
        return _error("规格的顶层需要是 JSON 对象。")
    missing = _missing(spec)
    if missing:
        return _error(
            "确认清单还缺：" + "、".join(missing) + "。每一项需要 name、source（specified 或 assumed）和 value。",
            missing,
        )
    stamped = copy.deepcopy(spec)
    confirmation = dict(stamped.get("confirmation") or {})
    confirmation.pop("token", None)
    stamped["confirmation"] = confirmation
    confirmation["token"] = _token(stamped)
    return {"ok": True, "launched_solver": False, "stage": "confirm", "spec": stamped}


def assumption_lines(spec: object) -> list[str]:
    """Return the checklist items the user accepted as assumptions."""
    if not isinstance(spec, dict):
        return []
    confirmation = spec.get("confirmation")
    items = confirmation.get("items") if isinstance(confirmation, dict) else None
    lines: list[str] = []
    if not isinstance(items, list):
        return lines
    for item in items:
        if not isinstance(item, dict) or item.get("source") != "assumed":
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str) and value.strip():
            lines.append(f"{name}: {value.strip()}")
    return lines


def apply_assumptions(payload: dict, lines: list[str]) -> dict:
    """Store assumptions on a result and on a report file that already exists."""
    payload["assumptions"] = list(lines)
    for key in ("summary_path", "report"):
        raw = payload.get(key)
        if not isinstance(raw, str):
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["assumptions"] = list(lines)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def solver_payload(spec: object) -> object:
    """Drop the checklist before a solver backend sees the spec."""
    if not isinstance(spec, dict) or "confirmation" not in spec:
        return spec
    return {key: value for key, value in spec.items() if key != "confirmation"}


def rejection(spec: object) -> dict | None:
    """Return an error when spec was not returned by confirm, otherwise None."""
    if not isinstance(spec, dict):
        return _error("规格的顶层需要是 JSON 对象。")
    confirmation = spec.get("confirmation")
    if not isinstance(confirmation, dict) or not isinstance(confirmation.get("token"), str):
        return _error("求解前需要先确认规格。请先执行 confirm，把返回的 spec 原样交给求解命令。")
    if confirmation["token"] != _token(spec):
        return _error("规格在确认之后又被改过。请重新执行 confirm。")
    missing = _missing(spec)
    if missing:
        return _error("确认清单还缺：" + "、".join(missing) + "。", missing)
    return None


def _missing(spec: dict) -> list[str]:
    required = list(CORE_ITEMS)
    if any(key in spec for key in ("sweep", "optimize", "values")):
        required.extend(STUDY_ITEMS)
    found: set[str] = set()
    confirmation = spec.get("confirmation")
    items = confirmation.get("items") if isinstance(confirmation, dict) else None
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            source = item.get("source")
            value = item.get("value")
            if (
                isinstance(name, str)
                and source in ("specified", "assumed")
                and isinstance(value, str)
                and value.strip()
            ):
                found.add(name)
    return [name for name in required if name not in found]


def _token(spec: dict) -> str:
    confirmation = spec.get("confirmation") if isinstance(spec.get("confirmation"), dict) else {}
    body = {key: value for key, value in spec.items() if key != "confirmation"}
    payload = {"items": confirmation.get("items"), "spec": body}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _error(message: str, missing: list[str] | None = None) -> dict:
    body = {"ok": False, "launched_solver": False, "stage": "confirm", "error": message}
    if missing:
        body["missing"] = missing
    return body
