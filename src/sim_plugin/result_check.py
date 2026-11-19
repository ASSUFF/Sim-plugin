"""Reject non-finite results and values outside an optional expect block."""

from __future__ import annotations

import math


def problems(results: dict, expect: dict | None = None) -> list[str]:
    found: list[str] = []
    numbers = {}
    for name, raw in results.items():
        number = _number(raw)
        numbers[name] = number
        if number is not None and not math.isfinite(number):
            found.append(f"{name} 不是有限数值（{raw}）。")
    if not isinstance(expect, dict):
        return found
    for name, rule in expect.items():
        if not isinstance(rule, dict):
            found.append(f"{name} 的 expect 需要是对象。")
            continue
        number = numbers.get(name)
        if number is None:
            found.append(f"结果里没有 {name}。")
            continue
        if not math.isfinite(number):
            continue
        if "min" in rule and number < float(rule["min"]):
            found.append(f"{name}={number:g}，低于 expect.min {rule['min']}。")
        if "max" in rule and number > float(rule["max"]):
            found.append(f"{name}={number:g}，高于 expect.max {rule['max']}。")
    return found


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
